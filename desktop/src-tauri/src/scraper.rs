use crate::models::Post;
use reqwest::Client;
use std::time::Duration;
use regex::Regex;
use serde_json::Value;

pub async fn fetch_page(url: &str, flare_solver_url: &str) -> Option<String> {
    if flare_solver_url.is_empty() {
        let client = Client::builder()
            .timeout(Duration::from_secs(15))
            .user_agent("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
            .build()
            .unwrap_or_default();

        if let Ok(resp) = client.get(url).send().await {
            if resp.status().is_success() {
                return resp.text().await.ok();
            }
        }
        return None;
    }

    // Fetch via FlareSolverr
    let client = Client::builder()
        .timeout(Duration::from_secs(35))
        .build()
        .unwrap_or_default();

    let payload = serde_json::json!({
        "cmd": "request.get",
        "url": url,
        "maxTimeout": 30000,
    });

    let endpoint = format!("{}/v1", flare_solver_url.trim_end_matches('/'));
    if let Ok(resp) = client.post(&endpoint).json(&payload).send().await {
        if let Ok(body) = resp.json::<Value>().await {
            let solution = body.get("solution").and_then(|s| s.as_object());
            if let Some(content) = solution.and_then(|s| s.get("response")).and_then(|r| r.as_str()) {
                return Some(content.to_string());
            }
        }
    }
    None
}

pub fn parse_scraped_favorites(html: &str) -> Vec<Post> {
    let tile_re = Regex::new(r#"(?i)<a[^>]+id=['"]p(\d+)['"][^>]*>\s*<img[^>]+src=['"]([^'"]+)['"]"#).unwrap();
    let mut posts = Vec::new();
    let mut seen = std::collections::HashSet::new();

    for cap in tile_re.captures_iter(html) {
        if let Ok(post_id) = cap[1].parse::<i64>() {
            if seen.insert(post_id) {
                let mut preview = cap[2].to_string();
                if preview.starts_with("//") {
                    preview = format!("https:{}", preview);
                }
                posts.push(Post {
                    id: post_id,
                    tags: Vec::new(),
                    rating: "".to_string(),
                    score: None,
                    width: None,
                    height: None,
                    file_size: None,
                    source: "".to_string(),
                    md5: "".to_string(),
                    preview_url: preview.clone(),
                    sample_url: preview,
                    file_url: "".to_string(),
                    created_at: "".to_string(),
                });
            }
        }
    }

    if !posts.is_empty() {
        return posts;
    }

    // Fallback: extract IDs and images separately
    let id_re = Regex::new(r"(?i)page=post(?:&|\?)s=view(?:&|\?)id=(\d+)").unwrap();
    let preview_re = Regex::new(r#"(?i)<img[^>]+src="([^"]+)""#).unwrap();

    let mut ids = Vec::new();
    for cap in id_re.captures_iter(html) {
        if let Ok(id) = cap[1].parse::<i64>() {
            if seen.insert(id) {
                ids.push(id);
            }
        }
    }

    let mut previews = Vec::new();
    for cap in preview_re.captures_iter(html) {
        let mut src = cap[1].to_string();
        if src.starts_with("//") {
            src = format!("https:{}", src);
        }
        previews.push(src);
    }

    for (i, &post_id) in ids.iter().enumerate() {
        let preview = if i < previews.len() { previews[i].clone() } else { "".to_string() };
        posts.push(Post {
            id: post_id,
            tags: Vec::new(),
            rating: "".to_string(),
            score: None,
            width: None,
            height: None,
            file_size: None,
            source: "".to_string(),
            md5: "".to_string(),
            preview_url: preview.clone(),
            sample_url: preview,
            file_url: "".to_string(),
            created_at: "".to_string(),
        });
    }

    posts
}

pub async fn fetch_friend_favorites(
    user_id: &str,
    flare_solver_url: &str,
    page: i32,
) -> Result<Vec<Post>, String> {
    let api_page = page / 5;
    let pid = api_page * 50;
    
    let user_id_encoded = url::form_urlencoded::byte_serialize(user_id.trim().as_bytes()).collect::<String>();
    let url = format!(
        "https://rule34.xxx/index.php?page=favorites&s=view&id={}&pid={}",
        user_id_encoded, pid
    );

    let html = fetch_page(&url, flare_solver_url).await
        .ok_or_else(|| format!("Failed to fetch favorites for user {} (page {})", user_id, page))?;

    Ok(parse_scraped_favorites(&html))
}
