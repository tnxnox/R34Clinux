use crate::db::LocalFavoritesStore;
use crate::models::Post;
use crate::settings::AppSettings;
use futures_util::StreamExt;
use reqwest::Client;
use std::fs::{self, File};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

const MAX_DOWNLOAD_BYTES: u64 = 500 * 1024 * 1024; // 500 MB

pub struct DownloadManager {
    db: LocalFavoritesStore,
    client: Client,
}

impl DownloadManager {
    pub fn new(db: LocalFavoritesStore) -> Self {
        Self {
            db,
            client: Client::builder()
                .timeout(Duration::from_secs(60))
                .user_agent("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
                .build()
                .unwrap_or_default(),
        }
    }

    fn sanitize_path_segment(&self, segment: &str) -> String {
        let cleaned: String = segment
            .chars()
            .filter(|&c| c.is_alphanumeric() || c == ' ' || c == '.' || c == '_' || c == '-')
            .collect();
        cleaned.trim_matches(|c| c == '.' || c == ' ').to_string()
    }

    fn format_template(&self, template: &str, post: &Post, is_path: bool) -> String {
        let score_str = post.score.unwrap_or(0).to_string();
        let rating_str = if post.rating.is_empty() {
            "unknown"
        } else {
            &post.rating
        };
        let md5_str = if post.md5.is_empty() {
            "unknown"
        } else {
            &post.md5
        };
        let id_str = post.id.to_string();

        let formatted = template
            .replace("{id}", &id_str)
            .replace("{md5}", md5_str)
            .replace("{score}", &score_str)
            .replace("{rating}", rating_str);

        if is_path {
            let normalized = formatted.replace('\\', "/");
            let segments: Vec<&str> = normalized.split('/').collect();
            let mut sanitized_segments = Vec::new();
            for s in segments {
                let trimmed = s.trim();
                if !trimmed.is_empty() {
                    let sanitized = self.sanitize_path_segment(trimmed);
                    if !sanitized.is_empty()
                        && sanitized != "."
                        && sanitized != ".."
                        && sanitized != "~"
                    {
                        sanitized_segments.push(sanitized);
                    }
                }
            }
            if sanitized_segments.is_empty() {
                "".to_string()
            } else {
                sanitized_segments.join("/")
            }
        } else {
            // Keep alphanumeric, spaces, dots, underscores, dashes
            formatted
                .chars()
                .filter(|&c| c.is_alphanumeric() || c == ' ' || c == '.' || c == '_' || c == '-')
                .collect::<String>()
                .trim()
                .to_string()
        }
    }

    fn validate_path_within_base(&self, full_path: &Path, base_dir: &Path) -> Result<(), String> {
        let resolved_full = full_path
            .canonicalize()
            .unwrap_or_else(|_| full_path.to_path_buf());
        let resolved_base = base_dir
            .canonicalize()
            .map_err(|e| format!("Failed to canonicalize base directory: {}", e))?;

        if !resolved_full.starts_with(&resolved_base) {
            return Err(format!(
                "Path traversal detected: {:?} is outside {:?}",
                resolved_full, resolved_base
            ));
        }
        Ok(())
    }

    pub fn format_filename(&self, post: &Post, template: &str, use_sample: bool) -> String {
        let url = if use_sample && !post.sample_url.is_empty() {
            &post.sample_url
        } else if !post.file_url.is_empty() {
            &post.file_url
        } else {
            &post.preview_url
        };

        let ext = if !url.is_empty() {
            if let Ok(parsed) = url::Url::parse(url) {
                let path_str = parsed.path();
                Path::new(path_str)
                    .extension()
                    .and_then(|e| e.to_str())
                    .map(|s| format!(".{}", s))
                    .unwrap_or_else(|| ".jpg".to_string())
            } else {
                ".jpg".to_string()
            }
        } else {
            ".jpg".to_string()
        };

        let mut name = self.format_template(template, post, false);
        if name.is_empty() {
            name = post.id.to_string();
        }
        format!("{}{}", name, ext)
    }

    #[cfg(unix)]
    fn check_disk_space(&self, dest_dir: &Path, required_bytes: u64) -> Result<(), String> {
        use std::ffi::CString;
        use std::os::unix::ffi::OsStrExt;

        let path_c = CString::new(dest_dir.as_os_str().as_bytes())
            .map_err(|_| "Invalid destination path encoding")?;

        let mut stats = std::mem::MaybeUninit::<libc::statvfs>::uninit();

        unsafe {
            if libc::statvfs(path_c.as_ptr(), stats.as_mut_ptr()) == 0 {
                let stats = stats.assume_init();
                #[allow(clippy::unnecessary_cast)]
                let free_space = stats.f_bavail as u64 * stats.f_frsize as u64;
                if free_space < required_bytes {
                    return Err(format!(
                        "Insufficient disk space: need {:.1} MB, have {:.1} MB",
                        required_bytes as f64 / (1024.0 * 1024.0),
                        free_space as f64 / (1024.0 * 1024.0)
                    ));
                }
            }
        }
        Ok(())
    }

    #[cfg(not(unix))]
    fn check_disk_space(&self, _dest_dir: &Path, _required_bytes: u64) -> Result<(), String> {
        Ok(())
    }

    pub async fn download_post(
        &self,
        post: &Post,
        settings: &AppSettings,
    ) -> Result<Option<PathBuf>, String> {
        if post.file_url.is_empty() && post.sample_url.is_empty() {
            return Err("Post has no downloadable content.".to_string());
        }

        if self.db.is_downloaded(post.id, &post.md5).unwrap_or(false) {
            return Ok(None);
        }

        let base_dir_str = if settings.download_directory.is_empty() {
            crate::settings::SettingsStore::default_download_directory()
        } else {
            settings.download_directory.clone()
        };
        let base_dir = Path::new(&base_dir_str);

        let template = if settings.download_naming_template.is_empty() {
            "{id}"
        } else {
            &settings.download_naming_template
        };

        let filename = self.format_filename(post, template, settings.download_use_sample);
        let mut dest = base_dir.join(&filename);

        // Make sure parent folder exists
        if let Some(parent) = dest.parent() {
            fs::create_dir_all(parent)
                .map_err(|e| format!("Cannot create download subdirectory {:?}: {}", parent, e))?;
        }

        // Validate path traversal
        self.validate_path_within_base(&dest, base_dir)?;

        // Handle collision
        if dest.exists() {
            let stem = dest.file_stem().and_then(|s| s.to_str()).unwrap_or("");
            let ext = dest.extension().and_then(|e| e.to_str()).unwrap_or("");
            let new_name = format!("{}_{}.{}", stem, post.id, ext);
            dest = dest.with_file_name(new_name);
        }

        let url = if settings.download_use_sample && !post.sample_url.is_empty() {
            &post.sample_url
        } else if !post.file_url.is_empty() {
            &post.file_url
        } else {
            &post.preview_url
        };

        let max_retries = std::cmp::max(0, settings.download_max_retries);
        let mut download_error = String::new();

        for attempt in 0..=max_retries {
            let res = self
                .client
                .get(url)
                .header("Referer", post.page_url())
                .send()
                .await;

            match res {
                Ok(resp) => {
                    let status = resp.status();
                    if status == reqwest::StatusCode::NOT_FOUND
                        || status == reqwest::StatusCode::GONE
                    {
                        return Err(format!(
                            "Post #{} no longer available on server (HTTP {}) - content may have been deleted.",
                            post.id, status
                        ));
                    }
                    if !status.is_success() {
                        download_error = format!("HTTP error: {}", status);
                        tokio::time::sleep(Duration::from_secs(2u64.pow(attempt as u32))).await;
                        continue;
                    }

                    // Check Content-Length limit
                    if let Some(content_length) = resp.content_length() {
                        if content_length > MAX_DOWNLOAD_BYTES {
                            return Err(format!(
                                "Download too large: {:.1} MB (max {:.0} MB)",
                                content_length as f64 / (1024.0 * 1024.0),
                                MAX_DOWNLOAD_BYTES as f64 / (1024.0 * 1024.0)
                            ));
                        }
                        if let Some(parent) = dest.parent() {
                            self.check_disk_space(parent, content_length * 2).ok();
                        }
                    } else if let Some(parent) = dest.parent() {
                        self.check_disk_space(parent, MAX_DOWNLOAD_BYTES).ok();
                    }

                    // Stream download
                    let mut file = File::create(&dest).map_err(|e| {
                        format!("Failed to create destination file {:?}: {}", dest, e)
                    })?;

                    let mut stream = resp.bytes_stream();
                    let mut bytes_downloaded = 0;
                    let read_start = Instant::now();
                    let max_read_duration = Duration::from_secs(120);

                    let mut stream_success = true;
                    while let Some(chunk_result) = stream.next().await {
                        match chunk_result {
                            Ok(chunk) => {
                                bytes_downloaded += chunk.len() as u64;
                                if bytes_downloaded > MAX_DOWNLOAD_BYTES {
                                    download_error = format!(
                                        "Download exceeded maximum size of {} MB",
                                        MAX_DOWNLOAD_BYTES / (1024 * 1024)
                                    );
                                    stream_success = false;
                                    break;
                                }
                                if read_start.elapsed() > max_read_duration {
                                    download_error = format!(
                                        "Download timed out after {}s",
                                        max_read_duration.as_secs()
                                    );
                                    stream_success = false;
                                    break;
                                }
                                if let Err(e) = file.write_all(&chunk) {
                                    download_error = format!("File write error: {}", e);
                                    stream_success = false;
                                    break;
                                }
                            }
                            Err(e) => {
                                download_error = format!("Stream read error: {}", e);
                                stream_success = false;
                                break;
                            }
                        }
                    }

                    if stream_success {
                        if settings.download_sidecar_enabled {
                            self.write_sidecar(&dest, post, &settings.download_sidecar_format);
                        }
                        self.db
                            .record_download(post.id, &post.md5, dest.to_str().unwrap_or(""))
                            .ok();
                        return Ok(Some(dest));
                    }
                }
                Err(e) => {
                    download_error = e.to_string();
                }
            }

            if attempt < max_retries {
                tokio::time::sleep(Duration::from_secs(2u64.pow(attempt as u32))).await;
            }
        }

        if dest.exists() {
            fs::remove_file(&dest).ok(); // cleanup partial download
        }

        Err(format!(
            "Failed to download post {} after {} retries: {}",
            post.id, max_retries, download_error
        ))
    }

    fn write_sidecar(&self, media_path: &Path, post: &Post, format: &str) {
        let fmt = format.to_lowercase();
        if fmt == "json" || fmt == "both" {
            let sidecar = media_path.with_extension("json");
            let data = serde_json::json!({
                "id": post.id,
                "tags": post.tags,
                "score": post.score,
                "rating": post.rating,
                "md5": post.md5,
                "source": post.source,
                "created_at": post.created_at,
            });
            if let Ok(serialized) = serde_json::to_string_pretty(&data) {
                fs::write(sidecar, serialized).ok();
            }
        }
        if fmt == "txt" || fmt == "both" {
            let sidecar = media_path.with_extension("txt");
            fs::write(sidecar, post.tags_text()).ok();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::models::Post;

    fn temp_db() -> (LocalFavoritesStore, PathBuf) {
        let mut path = std::env::temp_dir();
        let name = format!(
            "r34_test_dm_{}.db",
            std::time::SystemTime::now()
                .duration_since(std::time::SystemTime::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        );
        path.push(name);
        let store = LocalFavoritesStore::new(Some(path.clone()));
        (store, path)
    }

    #[test]
    fn test_sanitize_path_segment() {
        let (db, path) = temp_db();
        let manager = DownloadManager::new(db);

        assert_eq!(manager.sanitize_path_segment("simple"), "simple");
        assert_eq!(
            manager.sanitize_path_segment("invalid/char?*"),
            "invalidchar"
        );
        assert_eq!(manager.sanitize_path_segment("  spaces  "), "spaces");
        assert_eq!(manager.sanitize_path_segment("...dots..."), "dots");
        assert_eq!(manager.sanitize_path_segment("a_b-c.d"), "a_b-c.d");

        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn test_format_template() {
        let (db, path) = temp_db();
        let manager = DownloadManager::new(db);

        let post = Post {
            id: 12345,
            tags: vec![],
            rating: "q".to_string(),
            score: Some(99),
            width: None,
            height: None,
            file_size: None,
            source: "".to_string(),
            md5: "abcdef1234567890".to_string(),
            preview_url: "".to_string(),
            sample_url: "".to_string(),
            file_url: "".to_string(),
            created_at: "".to_string(),
        };

        // Format templates for filename (is_path = false)
        assert_eq!(
            manager.format_template("{id}_{md5}_{score}_{rating}", &post, false),
            "12345_abcdef1234567890_99_q"
        );
        assert_eq!(
            manager.format_template("score_{score}", &post, false),
            "score_99"
        );

        // Format templates for paths (is_path = true)
        assert_eq!(
            manager.format_template("rating_{rating}/score_{score}", &post, true),
            "rating_q/score_99"
        );
        assert_eq!(
            manager.format_template("sub/../~/.dir/post_{id}", &post, true),
            "sub/dir/post_12345"
        );

        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn test_format_filename() {
        let (db, path) = temp_db();
        let manager = DownloadManager::new(db);

        let mut post = Post {
            id: 12345,
            tags: vec![],
            rating: "s".to_string(),
            score: None,
            width: None,
            height: None,
            file_size: None,
            source: "".to_string(),
            md5: "md5hash".to_string(),
            preview_url: "https://example.com/thumbnails/12345.jpg?somequery=1".to_string(),
            sample_url: "https://example.com/samples/sample_12345.png".to_string(),
            file_url: "https://example.com/files/file_12345.webm".to_string(),
            created_at: "".to_string(),
        };

        // Test file_url format
        assert_eq!(
            manager.format_filename(&post, "post_{id}_{md5}", false),
            "post_12345_md5hash.webm"
        );

        // Test sample_url format
        assert_eq!(
            manager.format_filename(&post, "sample_{id}", true),
            "sample_12345.png"
        );

        // Test fallback to preview_url extension if file_url and sample_url are empty
        post.file_url = "".to_string();
        post.sample_url = "".to_string();
        assert_eq!(manager.format_filename(&post, "{id}", false), "12345.jpg");

        // Test empty name fallback to ID
        assert_eq!(manager.format_filename(&post, "", false), "12345.jpg");

        let _ = std::fs::remove_file(&path);
    }
}
