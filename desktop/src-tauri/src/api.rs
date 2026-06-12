use crate::models::{Post, TagSuggestion};
use regex::Regex;
use reqwest::Client;
use serde_json::Value;
use std::time::Duration;

pub struct Rule34Client {
    client: Client,
    user_id: String,
    api_key: String,
}

impl Rule34Client {
    pub fn new(user_id: String, api_key: String) -> Self {
        Self {
            client: Client::builder()
                .timeout(Duration::from_secs(30))
                .user_agent("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
                .build()
                .unwrap_or_default(),
            user_id: user_id.trim().to_string(),
            api_key: api_key.trim().to_string(),
        }
    }

    fn auth_params(&self) -> Vec<(&str, &str)> {
        vec![("user_id", &self.user_id), ("api_key", &self.api_key)]
    }

    pub async fn search_posts(
        &self,
        tags: &str,
        page: i32,
        limit: i32,
    ) -> Result<Vec<Post>, String> {
        let mut query_params = self.auth_params();
        let limit_str = limit.to_string();
        let page_str = page.to_string();

        query_params.extend([
            ("page", "dapi"),
            ("s", "post"),
            ("q", "index"),
            (
                "tags",
                if tags.trim().is_empty() {
                    "all"
                } else {
                    tags.trim()
                },
            ),
            ("pid", &page_str),
            ("limit", &limit_str),
            ("json", "1"),
        ]);

        let response = self
            .client
            .get("https://api.rule34.xxx/index.php")
            .query(&query_params)
            .send()
            .await
            .map_err(|e| format!("Network request failed: {}", e))?;

        let status = response.status();
        if status.is_client_error() || status.is_server_error() {
            return Err(format!("Rule34 API returned HTTP status {}", status));
        }

        let text = response
            .text()
            .await
            .map_err(|e| format!("Failed to read response body: {}", e))?;

        let trimmed = text.trim();
        if trimmed.is_empty() {
            return Ok(Vec::new());
        }

        if trimmed.starts_with('<') {
            // It's XML!
            self.parse_xml_posts(trimmed)
        } else {
            // It's JSON!
            self.parse_json_posts(trimmed)
        }
    }

    fn parse_json_posts(&self, text: &str) -> Result<Vec<Post>, String> {
        let val: Value = serde_json::from_str(text)
            .map_err(|e| format!("Failed to parse JSON response: {}", e))?;

        let raw_posts = if let Some(arr) = val.as_array() {
            arr
        } else if let Some(obj) = val.as_object() {
            if obj.get("success") == Some(&Value::Bool(false)) {
                let msg = obj
                    .get("message")
                    .and_then(|m| m.as_str())
                    .unwrap_or("API returned error status");
                return Err(msg.to_string());
            }
            if let Some(posts_val) = obj.get("post").or(obj.get("posts")).or(obj.get("result")) {
                if let Some(arr) = posts_val.as_array() {
                    arr
                } else if posts_val.is_object() {
                    return Ok(vec![self.value_to_post(posts_val)?]);
                } else {
                    return Ok(Vec::new());
                }
            } else {
                return Ok(Vec::new());
            }
        } else {
            return Ok(Vec::new());
        };

        let mut posts = Vec::new();
        for val in raw_posts {
            if let Ok(post) = self.value_to_post(val) {
                posts.push(post);
            }
        }
        Ok(posts)
    }

    pub fn value_to_post(&self, val: &Value) -> Result<Post, String> {
        let id = val
            .get("id")
            .and_then(|v| {
                v.as_i64()
                    .or_else(|| v.as_str().and_then(|s| s.parse::<i64>().ok()))
            })
            .unwrap_or(0);

        let tags_str = val.get("tags").and_then(|v| v.as_str()).unwrap_or("");
        let tags: Vec<String> = tags_str.split_whitespace().map(|s| s.to_string()).collect();

        let rating = val
            .get("rating")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let score = val.get("score").and_then(|v| v.as_i64().map(|s| s as i32));
        let width = val.get("width").and_then(|v| v.as_i64().map(|w| w as i32));
        let height = val.get("height").and_then(|v| v.as_i64().map(|h| h as i32));
        let file_size = val.get("file_size").and_then(|v| v.as_i64());
        let source = val
            .get("source")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let md5 = val
            .get("md5")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let preview_url = val
            .get("preview_url")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let sample_url = val
            .get("sample_url")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let file_url = val
            .get("file_url")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        let created_at = val
            .get("change")
            .or(val.get("created_at"))
            .or(val.get("date"))
            .and_then(|v| v.as_str().map(|s| s.to_string()))
            .unwrap_or_default();

        Ok(Post {
            id,
            tags,
            rating,
            score,
            width,
            height,
            file_size,
            source,
            md5,
            preview_url,
            sample_url,
            file_url,
            created_at,
        })
    }

    fn parse_xml_posts(&self, text: &str) -> Result<Vec<Post>, String> {
        let post_regex = Regex::new(r"<post\s+([^>]+)/>").unwrap();
        let attr_regex = Regex::new(r#"(\w+)\s*=\s*"([^"]*)""#).unwrap();

        let mut posts = Vec::new();
        for cap in post_regex.captures_iter(text) {
            let attrs_str = &cap[1];
            let mut id = 0;
            let mut tags = Vec::new();
            let mut rating = String::new();
            let mut score = None;
            let mut width = None;
            let mut height = None;
            let mut file_size = None;
            let mut source = String::new();
            let mut md5 = String::new();
            let mut preview_url = String::new();
            let mut sample_url = String::new();
            let mut file_url = String::new();
            let mut created_at = String::new();

            for attr_cap in attr_regex.captures_iter(attrs_str) {
                let key = &attr_cap[1];
                let val = html_escape::decode_html_entities(&attr_cap[2]).into_owned();

                match key {
                    "id" => id = val.parse().unwrap_or(0),
                    "tags" => tags = val.split_whitespace().map(|s| s.to_string()).collect(),
                    "rating" => rating = val,
                    "score" => score = val.parse().ok(),
                    "width" => width = val.parse().ok(),
                    "height" => height = val.parse().ok(),
                    "file_size" => file_size = val.parse().ok(),
                    "source" => source = val,
                    "md5" => md5 = val,
                    "preview_url" => preview_url = val,
                    "sample_url" => sample_url = val,
                    "file_url" => file_url = val,
                    "change" | "created_at" | "date" => created_at = val,
                    _ => {}
                }
            }

            posts.push(Post {
                id,
                tags,
                rating,
                score,
                width,
                height,
                file_size,
                source,
                md5,
                preview_url,
                sample_url,
                file_url,
                created_at,
            });
        }

        Ok(posts)
    }

    pub async fn autocomplete_tags(&self, prefix: &str) -> Result<Vec<TagSuggestion>, String> {
        let query = prefix.trim();
        if query.is_empty() {
            return Ok(Vec::new());
        }

        let response = self
            .client
            .get("https://api.rule34.xxx/autocomplete.php")
            .query(&[("q", query)])
            .send()
            .await
            .map_err(|e| format!("Autocomplete request failed: {}", e))?;

        if response.status().is_client_error() || response.status().is_server_error() {
            return Err(format!(
                "Autocomplete returned status {}",
                response.status()
            ));
        }

        let text = response
            .text()
            .await
            .map_err(|e| format!("Failed to read autocomplete response: {}", e))?;

        if text.trim().is_empty() {
            return Ok(Vec::new());
        }

        let payload: Value = serde_json::from_str(&text)
            .map_err(|e| format!("Autocomplete response invalid JSON: {}", e))?;

        let arr = payload
            .as_array()
            .ok_or_else(|| "Autocomplete response is not a list".to_string())?;

        let mut suggestions = Vec::new();
        let mut seen = std::collections::HashSet::new();

        let label_count_regex = Regex::new(r"\s*\((\d+)\)\s*$").unwrap();

        for item in arr {
            if let Some(obj) = item.as_object() {
                let raw_val = obj.get("value").and_then(|v| v.as_str()).unwrap_or("");
                let decoded_val = html_escape::decode_html_entities(raw_val).into_owned();
                let sanitized_val = self.sanitize_autocomplete_val(&decoded_val);

                if sanitized_val.is_empty() || seen.contains(&sanitized_val) {
                    continue;
                }

                let raw_label = obj.get("label").and_then(|v| v.as_str()).unwrap_or("");
                let decoded_label = html_escape::decode_html_entities(raw_label).into_owned();
                let normalized_label = decoded_label
                    .split_whitespace()
                    .collect::<Vec<_>>()
                    .join(" ");

                let count = label_count_regex
                    .captures(&normalized_label)
                    .and_then(|cap| cap[1].parse::<i32>().ok());

                suggestions.push(TagSuggestion {
                    value: sanitized_val.clone(),
                    label: normalized_label.clone(),
                    count,
                    display_text: normalized_label,
                });
                seen.insert(sanitized_val);
            }
        }

        Ok(suggestions)
    }

    fn sanitize_autocomplete_val(&self, val: &str) -> String {
        let normalized = val.split_whitespace().collect::<Vec<_>>().join(" ");
        if normalized.is_empty() {
            return "".to_string();
        }
        if normalized.contains(';')
            || normalized.contains('&')
            || normalized.contains('?')
            || normalized.contains(' ')
        {
            return "".to_string();
        }
        normalized
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_value_to_post_json() {
        let client = Rule34Client::new("".to_string(), "".to_string());
        let json_str = r#"{
            "id": 123,
            "tags": "tag1 tag2 tag3",
            "rating": "s",
            "score": 15,
            "width": 1920,
            "height": 1080,
            "file_size": 5000,
            "source": "pixiv",
            "md5": "abc",
            "preview_url": "p_url",
            "sample_url": "s_url",
            "file_url": "f_url",
            "change": "2026-06-12"
        }"#;
        let val: Value = serde_json::from_str(json_str).unwrap();
        let post = client.value_to_post(&val).unwrap();

        assert_eq!(post.id, 123);
        assert_eq!(post.tags, vec!["tag1", "tag2", "tag3"]);
        assert_eq!(post.rating, "s");
        assert_eq!(post.score, Some(15));
        assert_eq!(post.width, Some(1920));
        assert_eq!(post.height, Some(1080));
        assert_eq!(post.file_size, Some(5000));
        assert_eq!(post.source, "pixiv");
        assert_eq!(post.md5, "abc");
        assert_eq!(post.preview_url, "p_url");
        assert_eq!(post.sample_url, "s_url");
        assert_eq!(post.file_url, "f_url");
        assert_eq!(post.created_at, "2026-06-12");
    }

    #[test]
    fn test_parse_xml_posts() {
        let client = Rule34Client::new("".to_string(), "".to_string());
        let xml_str = r#"<?xml version="1.0" encoding="UTF-8"?>
        <posts count="1" offset="0">
            <post id="999" tags="xmltag1 xmltag2" rating="e" score="42" width="640" height="480" file_size="1000" source="somewhere" md5="xyz" preview_url="p" sample_url="s" file_url="f" change="12345678"/>
        </posts>"#;
        let posts = client.parse_xml_posts(xml_str).unwrap();
        assert_eq!(posts.len(), 1);
        let post = &posts[0];
        assert_eq!(post.id, 999);
        assert_eq!(post.tags, vec!["xmltag1", "xmltag2"]);
        assert_eq!(post.rating, "e");
        assert_eq!(post.score, Some(42));
        assert_eq!(post.width, Some(640));
        assert_eq!(post.height, Some(480));
        assert_eq!(post.file_size, Some(1000));
        assert_eq!(post.source, "somewhere");
        assert_eq!(post.md5, "xyz");
        assert_eq!(post.preview_url, "p");
        assert_eq!(post.sample_url, "s");
        assert_eq!(post.file_url, "f");
        assert_eq!(post.created_at, "12345678");
    }

    #[test]
    fn test_sanitize_autocomplete_val() {
        let client = Rule34Client::new("".to_string(), "".to_string());
        assert_eq!(
            client.sanitize_autocomplete_val("  hello_world  "),
            "hello_world"
        );
        assert_eq!(client.sanitize_autocomplete_val("hello world"), "");
        assert_eq!(client.sanitize_autocomplete_val("hello;world"), "");
        assert_eq!(client.sanitize_autocomplete_val("hello&world"), "");
        assert_eq!(client.sanitize_autocomplete_val("hello?world"), "");
    }
}
