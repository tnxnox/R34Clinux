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

/// Parses HTML into a list of Post models
pub fn parse_scraped_posts(html: &str) -> Vec<Post> {
    extract_items(html)
        .into_iter()
        .map(|(post_id, preview)| Post {
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
        })
        .collect()
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
    fn test_parse_scraped_posts() {
        let html = r#"<a id="p999"><img src="https://cdn.rule34.xxx/thumb.jpg"/></a>"#;
        let posts = parse_scraped_posts(html);
        assert_eq!(posts.len(), 1);
        assert_eq!(posts[0].id, 999);
        assert_eq!(posts[0].preview_url, "https://cdn.rule34.xxx/thumb.jpg");
    }
}
