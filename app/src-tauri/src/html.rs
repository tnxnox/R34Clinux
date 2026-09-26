use crate::models::Post;
use regex::Regex;
use std::collections::HashSet;

pub static FAVORITE_TILE_RE: std::sync::LazyLock<Regex> =
    std::sync::LazyLock::new(|| Regex::new(r#"(?i)<a[^>]+id=['"]p(\d+)['"]"#).unwrap());

pub static TILE_RE: std::sync::LazyLock<Regex> = std::sync::LazyLock::new(|| {
    Regex::new(r#"(?i)<a[^>]+id=['"]p(\d+)['"][^>]*>\s*<img[^>]+src=['"]([^'"]+)['"]"#).unwrap()
});

pub static ID_RE: std::sync::LazyLock<Regex> = std::sync::LazyLock::new(|| {
    Regex::new(r"(?i)page=post(?:&|\?)s=view(?:&|\?)id=(\d+)").unwrap()
});

pub static PREVIEW_RE: std::sync::LazyLock<Regex> =
    std::sync::LazyLock::new(|| Regex::new(r#"(?i)<img[^>]+src="([^"]+)""#).unwrap());

pub static CDN_THUMB_RE: std::sync::LazyLock<Regex> = std::sync::LazyLock::new(|| {
    Regex::new(r#"(?i)(?:thumbnails|images)/(\d+)/(?:thumbnail_)?([a-f0-9]{32})\.(jpg|jpeg|png)"#)
        .unwrap()
});

/// Derives (dir_id, md5, sample_url, candidate_file_url) from a Rule34 thumbnail URL.
pub fn derive_cdn_urls(
    preview_url: &str,
) -> (
    Option<String>,
    Option<String>,
    Option<String>,
    Option<String>,
) {
    if let Some(cap) = CDN_THUMB_RE.captures(preview_url) {
        let dir_id = cap[1].to_string();
        let md5 = cap[2].to_string();
        let ext = cap[3].to_string();
        let sample_url = format!(
            "https://wimg.rule34.xxx/samples/{}/sample_{}.jpg",
            dir_id, md5
        );
        let candidate_file_url =
            format!("https://wimg.rule34.xxx//images/{}/{}.{}", dir_id, md5, ext);
        (
            Some(dir_id),
            Some(md5),
            Some(sample_url),
            Some(candidate_file_url),
        )
    } else {
        (None, None, None, None)
    }
}

/// Extracts (post_id, preview_url) tuples from HTML tiles, with fallback to parsing IDs and images.
pub fn extract_items(html: &str) -> Vec<(i64, String)> {
    let mut items = Vec::new();
    let mut seen = HashSet::new();

    for cap in TILE_RE.captures_iter(html) {
        if let Ok(post_id) = cap[1].parse::<i64>() {
            if seen.insert(post_id) {
                let mut preview = cap[2].to_string();
                if preview.starts_with("//") {
                    preview = format!("https:{}", preview);
                }
                items.push((post_id, preview));
            }
        }
    }

    if !items.is_empty() {
        return items;
    }

    // Fallback: extract IDs and images separately
    let mut ids = Vec::new();
    for cap in ID_RE.captures_iter(html) {
        if let Ok(id) = cap[1].parse::<i64>() {
            if seen.insert(id) {
                ids.push(id);
            }
        }
    }

    let mut previews = Vec::new();
    for cap in PREVIEW_RE.captures_iter(html) {
        let mut preview = cap[1].to_string();
        if preview.starts_with("//") {
            preview = format!("https:{}", preview);
        }
        previews.push(preview);
    }

    for (i, id) in ids.into_iter().enumerate() {
        let preview = previews.get(i).cloned().unwrap_or_else(|| "".to_string());
        items.push((id, preview));
    }

    items
}

/// Extracts unique post IDs matching `<a ... id="p<id>">`
pub fn extract_tile_ids(html: &str) -> Vec<i64> {
    let mut ids = Vec::new();
    let mut seen = HashSet::new();
    for cap in FAVORITE_TILE_RE.captures_iter(html) {
        if let Ok(id) = cap[1].parse::<i64>() {
            if seen.insert(id) {
                ids.push(id);
            }
        }
    }
    ids
}

/// Parses HTML into a list of Post models with deterministic CDN reconstruction
pub fn parse_scraped_posts(html: &str) -> Vec<Post> {
    extract_items(html)
        .into_iter()
        .map(|(post_id, preview)| {
            let (_dir_opt, md5_opt, sample_opt, file_opt) = derive_cdn_urls(&preview);
            let md5 = md5_opt.unwrap_or_default();
            let sample_url = sample_opt.unwrap_or_else(|| preview.clone());
            let file_url = file_opt.unwrap_or_default();

            Post {
                id: post_id,
                tags: Vec::new(),
                rating: "".to_string(),
                score: None,
                width: None,
                height: None,
                file_size: None,
                source: "".to_string(),
                md5,
                preview_url: preview,
                sample_url,
                file_url,
                created_at: "".to_string(),
            }
        })
        .collect()
}

const CANDIDATE_MEDIA_EXTS: &[&str] = &["jpg", "png", "jpeg", "mp4", "gif", "webm"];

/// Resolves exact full-resolution CDN media URL, format, and file size via unthrottled HEAD requests.
pub async fn resolve_cdn_post_media(client: &reqwest::Client, post: &mut Post) {
    if post.md5.is_empty() {
        return;
    }

    let dir_id = if let Some(cap) = CDN_THUMB_RE.captures(&post.preview_url) {
        cap[1].to_string()
    } else if let Some(cap) = CDN_THUMB_RE.captures(&post.sample_url) {
        cap[1].to_string()
    } else {
        return;
    };

    let md5 = post.md5.clone();

    // Check extensions concurrently
    let probe_futures = CANDIDATE_MEDIA_EXTS.iter().map(|&ext| {
        let url = format!("https://wimg.rule34.xxx//images/{}/{}.{}", dir_id, md5, ext);
        let client_ref = client.clone();
        async move {
            if let Ok(resp) = client_ref.head(&url).send().await {
                if resp.status().is_success() {
                    let len = resp.content_length();
                    return Some((url, len));
                }
            }
            None
        }
    });

    let probe_results = futures_util::future::join_all(probe_futures).await;
    if let Some((url, len)) = probe_results.into_iter().flatten().next() {
        post.file_url = url;
        if let Some(l) = len {
            post.file_size = Some(l as i64);
        }
    }

    // Verify sample_url existence. If Rule34 didn't generate sample_ (because image is small),
    // sample_url returns 404, so fallback to file_url or preview_url
    if !post.sample_url.is_empty() && post.sample_url != post.preview_url {
        if let Ok(resp) = client.head(&post.sample_url).send().await {
            if resp.status().as_u16() == 404 {
                if !post.file_url.is_empty() {
                    post.sample_url = post.file_url.clone();
                } else {
                    post.sample_url = post.preview_url.clone();
                }
            }
        }
    }
}

/// Resolves CDN media URLs across a slice of posts concurrently
pub async fn resolve_cdn_posts_media(client: &reqwest::Client, posts: &mut [Post]) {
    use futures_util::stream::{self, StreamExt};

    let mut indices: Vec<usize> = Vec::new();
    for (i, p) in posts.iter().enumerate() {
        if !p.md5.is_empty() && (p.file_size.is_none() || p.file_url.is_empty()) {
            indices.push(i);
        }
    }

    let mut stream = stream::iter(indices)
        .map(|idx| {
            let client_ref = client.clone();
            async move { (idx, client_ref) }
        })
        .buffer_unordered(8);

    while let Some((idx, client_ref)) = stream.next().await {
        resolve_cdn_post_media(&client_ref, &mut posts[idx]).await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_extract_items_standard() {
        let html = r#"
            <div class="thumb">
                <a id="p12345" href="index.php?page=post&s=view&id=12345">
                    <img src="//cdn.rule34.xxx/thumbnails/12345/thumb.jpg" />
                </a>
            </div>
            <div class="thumb">
                <a id="p67890" href="index.php?page=post&s=view&id=67890">
                    <img src="https://cdn.rule34.xxx/thumbnails/67890/thumb.jpg" />
                </a>
            </div>
        "#;
        let items = extract_items(html);
        assert_eq!(items.len(), 2);
        assert_eq!(items[0].0, 12345);
        assert_eq!(
            items[0].1,
            "https://cdn.rule34.xxx/thumbnails/12345/thumb.jpg"
        );
        assert_eq!(items[1].0, 67890);
        assert_eq!(
            items[1].1,
            "https://cdn.rule34.xxx/thumbnails/67890/thumb.jpg"
        );
    }

    #[test]
    fn test_extract_tile_ids() {
        let html = r#"<a id="p111"></a><a id="p222"></a><a id="p111"></a>"#;
        let ids = extract_tile_ids(html);
        assert_eq!(ids, vec![111, 222]);
    }

    #[test]
    fn test_derive_cdn_urls() {
        let thumb_url = "https://wimg.rule34.xxx/thumbnails/819/thumbnail_5be30947f5c4d29d251959d62721d7df.jpg?18856131";
        let (dir_opt, md5_opt, sample_opt, file_opt) = derive_cdn_urls(thumb_url);

        assert_eq!(dir_opt.as_deref(), Some("819"));
        assert_eq!(md5_opt.as_deref(), Some("5be30947f5c4d29d251959d62721d7df"));
        assert_eq!(
            sample_opt.as_deref(),
            Some("https://wimg.rule34.xxx/samples/819/sample_5be30947f5c4d29d251959d62721d7df.jpg")
        );
        assert_eq!(
            file_opt.as_deref(),
            Some("https://wimg.rule34.xxx//images/819/5be30947f5c4d29d251959d62721d7df.jpg")
        );
    }

    #[test]
    fn test_parse_scraped_posts_with_cdn() {
        let html = r#"
            <a id="p18856131" href="index.php?page=post&s=view&id=18856131">
                <img src="https://rule34.xxx/thumbnails/819/thumbnail_5be30947f5c4d29d251959d62721d7df.jpg?18856131" />
            </a>
        "#;
        let posts = parse_scraped_posts(html);
        assert_eq!(posts.len(), 1);
        assert_eq!(posts[0].id, 18856131);
        assert_eq!(posts[0].md5, "5be30947f5c4d29d251959d62721d7df");
        assert_eq!(
            posts[0].sample_url,
            "https://wimg.rule34.xxx/samples/819/sample_5be30947f5c4d29d251959d62721d7df.jpg"
        );
        assert!(
            posts[0]
                .file_url
                .contains("5be30947f5c4d29d251959d62721d7df")
        );
    }
}
