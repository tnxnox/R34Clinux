#![allow(dead_code)]

use crate::models::Post;
use regex::Regex;
use reqwest::Client;
use serde_json::Value;
use std::process::Command;
use std::sync::{Arc, Mutex};
use std::time::Duration;

fn has_command(cmd: &str) -> bool {
    match Command::new(cmd)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
    {
        Ok(mut child) => {
            child.kill().ok();
            true
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => false,
        Err(_) => true,
    }
}

fn detect_container_cmd() -> Option<Vec<String>> {
    if has_command("podman") {
        return Some(vec!["podman".to_string()]);
    }
    if has_command("docker") {
        // Test docker info directly
        let res = Command::new("docker")
            .arg("info")
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status();
        if let Ok(status) = res {
            if status.success() {
                return Some(vec!["docker".to_string()]);
            }
        }
        // Test with sudo -n
        let res_sudo = Command::new("sudo")
            .args(["-n", "docker", "info"])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status();
        if let Ok(status) = res_sudo {
            if status.success() {
                return Some(vec![
                    "sudo".to_string(),
                    "-n".to_string(),
                    "docker".to_string(),
                ]);
            }
        }
    }
    None
}

fn is_url_local(url: &str) -> bool {
    if let Ok(parsed) = url::Url::parse(url) {
        if let Some(host) = parsed.host_str() {
            let host_lower = host.to_lowercase();
            return host_lower == "localhost" || host_lower == "127.0.0.1" || host_lower == "::1";
        }
    }
    false
}

async fn probe_flaresolverr(solver_url: &str, timeout_secs: u64) -> bool {
    let client = Client::builder()
        .timeout(Duration::from_secs(timeout_secs))
        .build()
        .unwrap_or_default();

    let base = solver_url.trim_end_matches('/');
    for path in ["/health", "/"] {
        let url = format!("{}{}", base, path);
        if let Ok(resp) = client.get(&url).send().await {
            if resp.status().is_success() {
                return true;
            }
        }
    }
    false
}

pub async fn start_flaresolverr_container(solver_url: &str) -> bool {
    if probe_flaresolverr(solver_url, 2).await {
        return true;
    }

    if !is_url_local(solver_url) {
        return false;
    }

    if let Ok(parsed) = url::Url::parse(solver_url) {
        if let Some(port) = parsed.port() {
            if port != 8191 {
                return false;
            }
        }
    }

    let cmd = match detect_container_cmd() {
        Some(c) => c,
        None => return false,
    };

    let container_name = "r34-flaresolverr";
    let image_name = "ghcr.io/flaresolverr/flaresolverr:latest";

    // Check if container exists (running or stopped)
    let mut check_cmd = Command::new(&cmd[0]);
    for arg in &cmd[1..] {
        check_cmd.arg(arg);
    }
    check_cmd.args(["ps", "-a", "--format", "{{.Names}}"]);

    let container_exists = if let Ok(output) = check_cmd.output() {
        let text = String::from_utf8_lossy(&output.stdout);
        text.lines().any(|l| l.trim() == container_name)
    } else {
        false
    };

    if container_exists {
        let mut start_cmd = Command::new(&cmd[0]);
        for arg in &cmd[1..] {
            start_cmd.arg(arg);
        }
        start_cmd.args(["start", container_name]);
        start_cmd.status().ok();
    } else {
        // Recreate it
        let mut run_cmd = Command::new(&cmd[0]);
        for arg in &cmd[1..] {
            run_cmd.arg(arg);
        }
        run_cmd.args([
            "run",
            "-d",
            "--name",
            container_name,
            "--restart",
            "no",
            "-p",
            "8191:8191",
            "-e",
            "LOG_LEVEL=info",
            image_name,
        ]);
        run_cmd.status().ok();
    }

    // Wait for flaresolverr to be ready
    for _ in 0..30 {
        if probe_flaresolverr(solver_url, 1).await {
            return true;
        }
        tokio::time::sleep(Duration::from_secs(1)).await;
    }

    false
}

pub struct FlareSolverrSession {
    session_name: String,
    solver_url: String,
    client: Client,
    session_ready: Arc<Mutex<bool>>,
}

impl FlareSolverrSession {
    pub fn new(session_name: String, solver_url: String) -> Self {
        Self {
            session_name,
            solver_url,
            client: Client::builder()
                .connect_timeout(Duration::from_secs(1))
                .timeout(Duration::from_secs(60))
                .build()
                .unwrap_or_default(),
            session_ready: Arc::new(Mutex::new(false)),
        }
    }

    fn solver_endpoint(&self) -> String {
        format!("{}/v1", self.solver_url.trim_end_matches('/'))
    }

    async fn ensure_session(&self, debug_logs: &mut String) -> Result<(), String> {
        {
            let ready = self.session_ready.lock().unwrap();
            if *ready {
                return Ok(());
            }
        }

        debug_logs.push_str(&format!(
            "\nCreating FlareSolverr session: {}",
            self.session_name
        ));

        let payload = serde_json::json!({
            "cmd": "sessions.create",
            "session": self.session_name,
        });

        let mut last_err = String::new();
        for attempt in 1..=3 {
            let res = self
                .client
                .post(self.solver_endpoint())
                .json(&payload)
                .send()
                .await;

            match res {
                Ok(resp) => {
                    if let Ok(body) = resp.json::<Value>().await {
                        let status = body
                            .get("status")
                            .and_then(|s| s.as_str())
                            .unwrap_or("")
                            .to_lowercase();
                        let msg = body.get("message").and_then(|m| m.as_str()).unwrap_or("");

                        if status == "ok" || msg.to_lowercase().contains("already exists") {
                            let mut ready = self.session_ready.lock().unwrap();
                            *ready = true;
                            debug_logs.push_str("\nSession created successfully.");
                            return Ok(());
                        } else {
                            last_err = msg.to_string();
                        }
                    }
                }
                Err(e) => {
                    last_err = e.to_string();
                    if attempt == 1 {
                        debug_logs.push_str("\nConnection failed, attempting to auto-start FlareSolverr container...");
                        let started = start_flaresolverr_container(&self.solver_url).await;
                        if !started {
                            break;
                        }
                    }
                    tokio::time::sleep(Duration::from_secs(attempt)).await;
                }
            }
        }

        Err(format!(
            "Failed to create FlareSolverr session: {}",
            last_err
        ))
    }

    pub async fn destroy_session(&self) {
        let payload = serde_json::json!({
            "cmd": "sessions.destroy",
            "session": self.session_name,
        });

        self.client
            .post(self.solver_endpoint())
            .json(&payload)
            .send()
            .await
            .ok();

        let mut ready = self.session_ready.lock().unwrap();
        *ready = false;
    }

    async fn request_via_solver(
        &self,
        url: &str,
        referer: Option<&str>,
        debug_logs: &mut String,
    ) -> Result<String, String> {
        let mut payload = serde_json::json!({
            "cmd": "request.get",
            "url": url,
            "maxTimeout": 60000,
            "session": self.session_name,
        });

        if let Some(ref_url) = referer {
            payload.as_object_mut().unwrap().insert(
                "headers".to_string(),
                serde_json::json!({ "Referer": ref_url }),
            );
        }

        for attempt in 1..=4 {
            self.ensure_session(debug_logs).await?;

            let res = self
                .client
                .post(self.solver_endpoint())
                .json(&payload)
                .send()
                .await;

            match res {
                Ok(resp) => {
                    if let Ok(body) = resp.json::<Value>().await {
                        let status = body
                            .get("status")
                            .and_then(|s| s.as_str())
                            .unwrap_or("")
                            .to_lowercase();
                        if status == "ok" {
                            let solution = body.get("solution").and_then(|s| s.as_object());
                            let response = solution
                                .and_then(|s| s.get("response"))
                                .and_then(|r| r.as_str());
                            if let Some(content) = response {
                                return Ok(content.to_string());
                            }
                        }

                        let message = body
                            .get("message")
                            .and_then(|m| m.as_str())
                            .unwrap_or("Unknown FlareSolverr error");
                        if message.to_lowercase().contains("session")
                            && (message.to_lowercase().contains("not found")
                                || message.to_lowercase().contains("does not exist"))
                        {
                            {
                                let mut ready = self.session_ready.lock().unwrap();
                                *ready = false;
                            }
                            tokio::time::sleep(Duration::from_millis(200)).await;
                            continue;
                        }
                        return Err(message.to_string());
                    }
                }
                Err(e) => {
                    {
                        let mut ready = self.session_ready.lock().unwrap();
                        *ready = false;
                    }
                    tokio::time::sleep(Duration::from_millis(500)).await;
                    if attempt == 4 {
                        return Err(format!("Solver connection error: {}", e));
                    }
                }
            }
        }

        Err("Solver request failed after retries.".to_string())
    }

    async fn post_via_solver(
        &self,
        url: &str,
        post_data: &str,
        referer: Option<&str>,
        debug_logs: &mut String,
    ) -> Result<String, String> {
        let mut headers = serde_json::Map::new();
        headers.insert(
            "Content-Type".to_string(),
            serde_json::json!("application/x-www-form-urlencoded"),
        );
        if let Some(ref_url) = referer {
            headers.insert("Referer".to_string(), serde_json::json!(ref_url));
        }

        let payload = serde_json::json!({
            "cmd": "request.post",
            "url": url,
            "postData": post_data,
            "headers": headers,
            "maxTimeout": 60000,
            "session": self.session_name,
        });

        for attempt in 1..=4 {
            self.ensure_session(debug_logs).await?;

            let res = self
                .client
                .post(self.solver_endpoint())
                .json(&payload)
                .send()
                .await;

            match res {
                Ok(resp) => {
                    if let Ok(body) = resp.json::<Value>().await {
                        let status = body
                            .get("status")
                            .and_then(|s| s.as_str())
                            .unwrap_or("")
                            .to_lowercase();
                        if status == "ok" {
                            let solution = body.get("solution").and_then(|s| s.as_object());
                            let response = solution
                                .and_then(|s| s.get("response"))
                                .and_then(|r| r.as_str());
                            if let Some(content) = response {
                                return Ok(content.to_string());
                            }
                        }

                        let message = body
                            .get("message")
                            .and_then(|m| m.as_str())
                            .unwrap_or("Unknown FlareSolverr error");
                        if message.to_lowercase().contains("session")
                            && (message.to_lowercase().contains("not found")
                                || message.to_lowercase().contains("does not exist"))
                        {
                            {
                                let mut ready = self.session_ready.lock().unwrap();
                                *ready = false;
                            }
                            tokio::time::sleep(Duration::from_millis(200)).await;
                            continue;
                        }
                        return Err(message.to_string());
                    }
                }
                Err(e) => {
                    {
                        let mut ready = self.session_ready.lock().unwrap();
                        *ready = false;
                    }
                    tokio::time::sleep(Duration::from_millis(500)).await;
                    if attempt == 4 {
                        return Err(format!("Solver connection error: {}", e));
                    }
                }
            }
        }

        Err("Solver POST request failed after retries.".to_string())
    }
}

pub struct FlareSolverrFavoritesClient {
    user_id: String,
    api_key: String,
    website_username: String,
    website_password: String,
    session: FlareSolverrSession,
    web_session_authenticated: Arc<Mutex<bool>>,
}

impl FlareSolverrFavoritesClient {
    pub fn new(
        user_id: String,
        api_key: String,
        website_username: String,
        website_password: String,
        solver_url: String,
    ) -> Self {
        let cleaned_user_id = Regex::new(r"[^a-zA-Z0-9_-]")
            .unwrap()
            .replace_all(&user_id, "")
            .to_string();
        let session_name = format!(
            "r34-{}",
            if cleaned_user_id.is_empty() {
                "default"
            } else {
                &cleaned_user_id
            }
        );
        Self {
            user_id,
            api_key,
            website_username,
            website_password,
            session: FlareSolverrSession::new(session_name, solver_url),
            web_session_authenticated: Arc::new(Mutex::new(false)),
        }
    }

    fn looks_rate_limited(&self, text: &str) -> bool {
        let lowered = text.to_lowercase();
        lowered.contains("too many requests")
            || lowered.contains("rate limit")
            || lowered.contains("rate-limit")
            || lowered.contains("rate limited")
            || lowered.contains("retry after")
            || lowered.contains("retry-after")
            || lowered.contains("429 too many")
    }

    fn looks_logged_in(&self, text: &str) -> bool {
        let lowered = text.to_lowercase();
        lowered.contains("page=account&s=logout")
            || lowered.contains("s=logout")
            || lowered.contains("page=account&s=login&code=01")
            || lowered.contains("logout of your account")
            || lowered.contains("page=account&s=change_password")
    }

    fn looks_favorites_view_authenticated(&self, text: &str) -> bool {
        let lowered = text.to_lowercase();
        if lowered.contains("page=account&s=login&code=00") {
            return false;
        }
        if lowered.contains("name=\"user\"") && lowered.contains("name=\"pass\"") {
            return false;
        }
        lowered.contains("page=favorites&s=view")
            || lowered.contains("id=\"post-list\"")
            || lowered.contains("id=\"p")
    }

    fn extract_favorite_tile_ids(&self, text: &str) -> Vec<i64> {
        let re = Regex::new(r#"(?i)<a[^>]+id=['"]p(\d+)['"][^>]*>"#).unwrap();
        let mut ids = Vec::new();
        let mut seen = std::collections::HashSet::new();
        for cap in re.captures_iter(text) {
            if let Ok(id) = cap[1].parse::<i64>() {
                if seen.insert(id) {
                    ids.push(id);
                }
            }
        }
        ids
    }

    fn extract_items(&self, text: &str) -> Vec<(i64, String)> {
        let tile_re =
            Regex::new(r#"(?i)<a[^>]+id=['"]p(\d+)['"][^>]*>\s*<img[^>]+src=['"]([^'"]+)['"]"#)
                .unwrap();
        let mut items = Vec::new();
        let mut seen = std::collections::HashSet::new();

        for cap in tile_re.captures_iter(text) {
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
        let id_re = Regex::new(r"(?i)page=post(?:&|\?)s=view(?:&|\?)id=(\d+)").unwrap();
        let preview_re = Regex::new(r#"(?i)<img[^>]+src="([^"]+)""#).unwrap();

        let mut ids = Vec::new();
        for cap in id_re.captures_iter(text) {
            if let Ok(id) = cap[1].parse::<i64>() {
                if seen.insert(id) {
                    ids.push(id);
                }
            }
        }

        let mut previews = Vec::new();
        for cap in preview_re.captures_iter(text) {
            let mut src = cap[1].to_string();
            if src.starts_with("//") {
                src = format!("https:{}", src);
            }
            previews.push(src);
        }

        for (i, &post_id) in ids.iter().enumerate() {
            let preview = if i < previews.len() {
                previews[i].clone()
            } else {
                "".to_string()
            };
            items.push((post_id, preview));
        }

        items
    }

    async fn ensure_web_login(&self, debug_logs: &mut String) -> Result<(), String> {
        {
            let auth = self.web_session_authenticated.lock().unwrap();
            if *auth {
                return Ok(());
            }
        }

        // Probe if already logged in
        let probe_urls = [
            "https://rule34.xxx/index.php?page=account&s=home".to_string(),
            format!(
                "https://rule34.xxx/index.php?page=favorites&s=view&id={}",
                self.user_id
            ),
        ];

        for url in &probe_urls {
            if let Ok(html) = self.session.request_via_solver(url, None, debug_logs).await {
                if self.looks_logged_in(&html) {
                    let mut auth = self.web_session_authenticated.lock().unwrap();
                    *auth = true;
                    debug_logs.push_str("\nAlready logged in.");
                    return Ok(());
                }
            }
        }

        let username = self.website_username.trim();
        let password = self.website_password.trim();
        if username.is_empty() || password.is_empty() {
            return Err(
                "Account sync requires website username and password in settings.".to_string(),
            );
        }

        debug_logs.push_str("\nLogging in to rule34.xxx...");
        let login_url = "https://rule34.xxx/index.php?page=account&s=login&code=00";

        let username_encoded =
            url::form_urlencoded::byte_serialize(username.as_bytes()).collect::<String>();
        let password_encoded =
            url::form_urlencoded::byte_serialize(password.as_bytes()).collect::<String>();
        let post_data = format!(
            "user={}&pass={}&submit=Log+in&login=Log+in",
            username_encoded, password_encoded
        );

        self.session
            .post_via_solver(login_url, &post_data, Some(login_url), debug_logs)
            .await?;

        // Verify login
        for attempt in 1..=3 {
            for url in &probe_urls {
                if let Ok(html) = self.session.request_via_solver(url, None, debug_logs).await {
                    if self.looks_logged_in(&html) {
                        let mut auth = self.web_session_authenticated.lock().unwrap();
                        *auth = true;
                        debug_logs.push_str("\nLogin verified.");
                        return Ok(());
                    }
                }
            }
            tokio::time::sleep(Duration::from_millis(400 * attempt)).await;
        }

        // If login check fails but request succeeded, proceed anyway as some sessions take time to propagate
        debug_logs.push_str("\nLogin check inconclusive. Proceeding with best-effort session.");
        Ok(())
    }

    pub async fn list_favorites(
        &self,
        limit: i32,
        debug_logs: &mut String,
    ) -> Result<(Vec<Post>, bool), String> {
        let dapi_posts = self.list_favorites_from_dapi(limit, debug_logs).await;
        match dapi_posts {
            Ok(posts) if !posts.is_empty() => {
                let is_complete = posts.len() < limit as usize;
                return Ok((posts, is_complete));
            }
            _ => {
                debug_logs.push_str(
                    "\nDAPI favorites returned empty or failed, falling back to HTML scraping...",
                );
            }
        }

        let html_posts = self.list_favorites_from_html(limit, debug_logs).await?;
        let is_complete = html_posts.len() < 50;
        Ok((html_posts, is_complete))
    }

    async fn list_favorites_from_dapi(
        &self,
        limit: i32,
        debug_logs: &mut String,
    ) -> Result<Vec<Post>, String> {
        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::SystemTime::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        let url = format!(
            "https://api.rule34.xxx/index.php?page=dapi&s=favorite&q=index&json=1&user_id={}&api_key={}&limit={}&_={}",
            self.user_id, self.api_key, limit, timestamp
        );

        let raw = self
            .session
            .request_via_solver(&url, None, debug_logs)
            .await?;
        let payload: Value = serde_json::from_str(&raw)
            .map_err(|e| format!("DAPI favorites invalid JSON: {}", e))?;

        let raw_posts = if let Some(arr) = payload.as_array() {
            arr
        } else if let Some(obj) = payload.as_object() {
            if obj.get("success") == Some(&Value::Bool(false)) {
                let msg = obj
                    .get("message")
                    .and_then(|m| m.as_str())
                    .unwrap_or("API error");
                return Err(msg.to_string());
            }
            if let Some(posts_val) = obj.get("post").or(obj.get("posts")).or(obj.get("result")) {
                posts_val
                    .as_array()
                    .ok_or_else(|| "Invalid posts array".to_string())?
            } else {
                return Ok(Vec::new());
            }
        } else {
            return Ok(Vec::new());
        };

        let mut posts = Vec::new();
        let client = crate::api::Rule34Client::new(self.user_id.clone(), self.api_key.clone());
        for val in raw_posts {
            if let Ok(p) = client.value_to_post(val) {
                posts.push(p);
            }
        }
        Ok(posts)
    }

    async fn list_favorites_from_html(
        &self,
        limit: i32,
        debug_logs: &mut String,
    ) -> Result<Vec<Post>, String> {
        self.ensure_web_login(debug_logs).await?;

        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::SystemTime::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        let candidates = [
            format!(
                "https://rule34.xxx/index.php?page=favorites&s=view&id={}&_={}",
                self.user_id, timestamp
            ),
            format!(
                "https://rule34.xxx/index.php?page=favorites&s=list&_={}",
                timestamp
            ),
        ];

        let mut seen = std::collections::HashSet::new();
        let mut posts = Vec::new();

        for url in &candidates {
            if let Ok(html) = self.session.request_via_solver(url, None, debug_logs).await {
                if self.looks_rate_limited(&html) {
                    return Err("Rate limited while fetching favorites HTML.".to_string());
                }

                let items = self.extract_items(&html);
                debug_logs.push_str(&format!(
                    "\nHTML Scrape url={}: extracted {} posts",
                    url,
                    items.len()
                ));

                for (post_id, preview_url) in items {
                    if seen.insert(post_id) {
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
                            preview_url: preview_url.clone(),
                            sample_url: preview_url,
                            file_url: "".to_string(),
                            created_at: "".to_string(),
                        });
                    }
                    if posts.len() >= limit as usize {
                        break;
                    }
                }
            }
            if !posts.is_empty() {
                break;
            }
        }

        if !posts.is_empty() {
            // Hydrate posts
            debug_logs.push_str(&format!(
                "\nHydrating {} HTML scraped posts via DAPI...",
                posts.len()
            ));
            self.hydrate_posts(&mut posts).await;
        }

        Ok(posts)
    }

    async fn hydrate_posts(&self, posts: &mut [Post]) {
        // Fetch detailed post data from DAPI for posts with only IDs
        let client = crate::api::Rule34Client::new(self.user_id.clone(), self.api_key.clone());
        let mut futures = Vec::new();

        for post in posts.iter() {
            let id = post.id;
            let tags = format!("id:{}", id);
            let client_ref = &client;
            futures.push(async move {
                if let Ok(details) = client_ref.search_posts(&tags, 0, 1).await {
                    if let Some(detail) = details.first() {
                        return Some(detail.clone());
                    }
                }
                None
            });
        }

        let results = futures_util::future::join_all(futures).await;
        for (i, opt_post) in results.into_iter().enumerate() {
            if let Some(detail) = opt_post {
                posts[i] = detail;
            }
        }
    }

    pub async fn add_favorite(&self, post_id: i64, debug_logs: &mut String) -> Result<(), String> {
        self.ensure_web_login(debug_logs).await?;
        let add_url = format!("https://rule34.xxx/public/addfav.php?id={}", post_id);

        let raw = self
            .session
            .request_via_solver(&add_url, None, debug_logs)
            .await?;
        let body = extract_body_text(&raw);

        if self.looks_rate_limited(&body) {
            return Err("Rule34 temporarily rate limited favorite add (HTTP 429).".to_string());
        }

        if body == "2" {
            // Re-login fallback
            debug_logs.push_str(
                "\nAdd endpoint reported not logged in. Destroying session and retrying...",
            );
            self.session.destroy_session().await;
            {
                let mut auth = self.web_session_authenticated.lock().unwrap();
                *auth = false;
            }
            self.ensure_web_login(debug_logs).await?;

            let alt_url = format!(
                "https://rule34.xxx/index.php?page=favorites&s=add&id={}",
                post_id
            );
            let referrer = format!(
                "https://rule34.xxx/index.php?page=favorites&s=view&id={}",
                self.user_id
            );

            let alt_raw = self
                .session
                .request_via_solver(&alt_url, Some(&referrer), debug_logs)
                .await?;
            let alt_body = extract_body_text(&alt_raw);
            if self.looks_rate_limited(&alt_body) {
                return Err("Rule34 temporarily rate limited favorite add (HTTP 429).".to_string());
            }
            if alt_body == "2" {
                return Err("Web session login expired or invalid.".to_string());
            }
        }

        // Verify it was added
        tokio::time::sleep(Duration::from_millis(500)).await;
        match self.favorite_exists_in_view(post_id, debug_logs).await {
            Ok(true) => Ok(()),
            Ok(false) => Err(format!(
                "Unable to confirm favorite #{} was added.",
                post_id
            )),
            Err(e) => Err(e),
        }
    }

    pub async fn remove_favorite(
        &self,
        post_id: i64,
        debug_logs: &mut String,
    ) -> Result<(), String> {
        self.ensure_web_login(debug_logs).await?;
        let referrer = format!(
            "https://rule34.xxx/index.php?page=favorites&s=view&id={}",
            self.user_id
        );
        let delete_url = format!(
            "https://rule34.xxx/index.php?page=favorites&s=delete&id={}&return_pid=0",
            post_id
        );

        let raw = self
            .session
            .request_via_solver(&delete_url, Some(&referrer), debug_logs)
            .await?;
        let body = extract_body_text(&raw);

        let final_body = if body == "2" {
            debug_logs.push_str(
                "\nDelete endpoint reported not logged in. Destroying session and retrying...",
            );
            self.session.destroy_session().await;
            {
                let mut auth = self.web_session_authenticated.lock().unwrap();
                *auth = false;
            }
            self.ensure_web_login(debug_logs).await?;

            let raw_retry = self
                .session
                .request_via_solver(&delete_url, Some(&referrer), debug_logs)
                .await?;
            let body_retry = extract_body_text(&raw_retry);
            if body_retry == "2" {
                return Err("Web session login expired or invalid.".to_string());
            }
            body_retry
        } else {
            body
        };

        if self.looks_rate_limited(&final_body) {
            return Err("Rate limited while deleting favorite.".to_string());
        }

        if !self.looks_favorites_view_authenticated(&final_body) {
            return Err("Session expired or not logged in while deleting favorite.".to_string());
        }

        let tile_ids = self.extract_favorite_tile_ids(&final_body);
        if tile_ids.contains(&post_id) {
            return Err(format!(
                "Unable to confirm favorite #{} was removed.",
                post_id
            ));
        }

        Ok(())
    }

    async fn favorite_exists_in_view(
        &self,
        post_id: i64,
        debug_logs: &mut String,
    ) -> Result<bool, String> {
        let timestamp = std::time::SystemTime::now()
            .duration_since(std::time::SystemTime::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        let url = format!(
            "https://rule34.xxx/index.php?page=favorites&s=view&id={}&_={}",
            self.user_id, timestamp
        );
        let html = self
            .session
            .request_via_solver(&url, None, debug_logs)
            .await?;

        if self.looks_rate_limited(&html) {
            return Err("Rate limited while checking favorites view.".to_string());
        }

        let tile_ids = self.extract_favorite_tile_ids(&html);
        Ok(tile_ids.contains(&post_id))
    }

    pub async fn close(&self) {
        self.session.destroy_session().await;
    }
}

fn extract_body_text(text: &str) -> String {
    let re = Regex::new(r"(?is)<body[^>]*>(.*?)</body>").unwrap();
    if let Some(cap) = re.captures(text) {
        cap[1].trim().to_string()
    } else {
        text.trim().to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::FlareSolverrFavoritesClient;

    #[test]
    fn test_looks_rate_limited() {
        let client = FlareSolverrFavoritesClient::new(
            "1234429".to_string(), // User ID containing 429
            "".to_string(),
            "".to_string(),
            "".to_string(),
            "".to_string(),
        );

        // A mock normal Rule34 page containing post with ID containing 429, and tag rating:questionable
        let normal_html = r#"
            <div class="post">
                <a href="index.php?page=post&s=view&id=4291234">
                    <img src="thumbs/429/thumbnail.jpg" />
                </a>
                <span class="rating">rating:questionable</span>
            </div>
            <a href="index.php?page=favorites&s=view&id=4291234&limit=50">Next Page</a>
        "#;
        assert!(
            !client.looks_rate_limited(normal_html),
            "Should not be rate limited on normal HTML with post ID 429 and rating"
        );

        // Rate limited cases
        assert!(client.looks_rate_limited("429 Too Many Requests"));
        assert!(client.looks_rate_limited("too many requests"));
        assert!(client.looks_rate_limited("rate limit exceeded"));
        assert!(client.looks_rate_limited("retry-after: 60"));
        assert!(client.looks_rate_limited("HTTP 429 Rate Limited"));
    }
}
