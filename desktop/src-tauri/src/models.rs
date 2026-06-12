use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Post {
    pub id: i64,
    pub tags: Vec<String>,
    pub rating: String,
    pub score: Option<i32>,
    pub width: Option<i32>,
    pub height: Option<i32>,
    pub file_size: Option<i64>,
    pub source: String,
    pub md5: String,
    pub preview_url: String,
    pub sample_url: String,
    pub file_url: String,
    pub created_at: String,
}

impl Post {
    pub fn page_url(&self) -> String {
        format!("https://rule34.xxx/index.php?page=post&s=view&id={}", self.id)
    }

    pub fn best_preview_url(&self) -> &str {
        if !self.sample_url.is_empty() {
            &self.sample_url
        } else if !self.preview_url.is_empty() {
            &self.preview_url
        } else {
            &self.file_url
        }
    }

    pub fn download_url(&self) -> &str {
        if !self.file_url.is_empty() {
            &self.file_url
        } else if !self.sample_url.is_empty() {
            &self.sample_url
        } else {
            &self.preview_url
        }
    }

    pub fn dimensions(&self) -> String {
        match (self.width, self.height) {
            (Some(w), Some(h)) => format!("{} x {}", w, h),
            _ => "Unknown size".to_string(),
        }
    }

    pub fn file_name(&self) -> String {
        let url = self.download_url();
        if url.is_empty() {
            return format!("post-{}", self.id);
        }
        if let Ok(parsed) = url::Url::parse(url) {
            if let Some(last_segment) = parsed.path_segments().and_then(|s| s.last()) {
                if !last_segment.is_empty() {
                    return last_segment.to_string();
                }
            }
        }
        format!("post-{}", self.id)
    }

    pub fn tags_text(&self) -> String {
        self.tags.join(" ")
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SerializedPost {
    pub id: i64,
    pub tags: Vec<String>,
    pub rating: String,
    pub score: Option<i32>,
    pub width: Option<i32>,
    pub height: Option<i32>,
    pub file_size: Option<i64>,
    pub source: String,
    pub md5: String,
    pub preview_url: String,
    pub sample_url: String,
    pub file_url: String,
    pub created_at: String,
    pub page_url: String,
    pub best_preview_url: String,
    pub download_url: String,
    pub dimensions: String,
    pub file_name: String,
    pub tags_text: String,
}

impl From<Post> for SerializedPost {
    fn from(p: Post) -> Self {
        Self {
            page_url: p.page_url(),
            best_preview_url: p.best_preview_url().to_string(),
            download_url: p.download_url().to_string(),
            dimensions: p.dimensions(),
            file_name: p.file_name(),
            tags_text: p.tags_text(),
            id: p.id,
            tags: p.tags,
            rating: p.rating,
            score: p.score,
            width: p.width,
            height: p.height,
            file_size: p.file_size,
            source: p.source,
            md5: p.md5,
            preview_url: p.preview_url,
            sample_url: p.sample_url,
            file_url: p.file_url,
            created_at: p.created_at,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TagSuggestion {
    pub value: String,
    pub label: String,
    pub count: Option<i32>,
    pub display_text: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Friend {
    pub user_id: String,
    pub display_name: String,
    pub notes: String,
    pub added_at: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncStatus {
    pub is_running: bool,
    pub debug: String,
    pub error: String,
    pub success: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct MutationProgress {
    pub total_mutations: usize,
    pub completed_mutations: usize,
    pub current_pending: usize,
}

