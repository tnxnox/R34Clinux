#![allow(dead_code)]

use crate::models::Post;
use regex::Regex;
use reqwest::Client;
use serde_json::Value;
use std::process::Command;
use std::sync::{Arc, Mutex};
use std::time::Duration;

static CLEAN_USER_ID_RE: std::sync::LazyLock<Regex> =
    std::sync::LazyLock::new(|| Regex::new(r"[^a-zA-Z0-9_-]").unwrap());

static BODY_RE: std::sync::LazyLock<Regex> =
    std::sync::LazyLock::new(|| Regex::new(r"(?is)<body[^>]*>(.*?)</body>").unwrap());

fn has_command(cmd: &str) -> bool {
    Command::new(cmd)
        .arg("--version")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
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
            let trimmed_host = host_lower.trim_matches(|c| c == '[' || c == ']');
            return trimmed_host == "localhost"
                || trimmed_host == "127.0.0.1"
                || trimmed_host == "::1";
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
        let cleaned_user_id = CLEAN_USER_ID_RE.replace_all(&user_id, "").to_string();
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
        crate::html::extract_tile_ids(text)
    }

    fn extract_items(&self, text: &str) -> Vec<(i64, String)> {
        crate::html::extract_items(text)
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
            Ok(posts)
                if self.website_username.trim().is_empty()
                    || self.website_password.trim().is_empty() =>
            {
                debug_logs.push_str(
                    "\nDAPI favorites returned empty and website credentials not set for HTML scrape fallback.",
                );
                return Ok((posts, true));
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
                        let (_dir_opt, md5_opt, sample_opt, file_opt) =
                            crate::html::derive_cdn_urls(&preview_url);
                        let md5 = md5_opt.unwrap_or_default();
                        let sample_url = sample_opt.unwrap_or_else(|| preview_url.clone());
                        let file_url = file_opt.unwrap_or_default();

                        posts.push(Post {
                            id: post_id,
                            tags: Vec::new(),
                            rating: "".to_string(),
                            score: None,
                            width: None,
                            height: None,
                            file_size: None,
                            source: "".to_string(),
                            md5,
                            preview_url: preview_url.clone(),
                            sample_url,
                            file_url,
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
            // Hydrate posts via local cache and unthrottled CDN HEAD resolution
            debug_logs.push_str(&format!(
                "\nHydrating {} HTML scraped posts via local DB & CDN...",
                posts.len()
            ));
            self.hydrate_posts(&mut posts).await;
        }

        Ok(posts)
    }

    async fn hydrate_posts(&self, posts: &mut [Post]) {
        // 1. Check local SQLite DB first - zero network requests for cached posts!
        if let Ok(store) = std::panic::catch_unwind(|| crate::db::LocalFavoritesStore::new(None)) {
            if let Ok(local_posts) = store.list_favorites(None, None) {
                let mut local_map = std::collections::HashMap::new();
                for lp in local_posts {
                    local_map.insert(lp.id, lp);
                }
                for post in posts.iter_mut() {
                    if let Some(cached) = local_map.get(&post.id) {
                        *post = cached.clone();
                    }
                }
            }
        }

        // 2. For posts needing media resolution, resolve exact extensions & sizes via unthrottled CDN HEAD requests
        let client = Client::builder()
            .timeout(Duration::from_secs(10))
            .user_agent("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
            .build()
            .unwrap_or_default();
        crate::html::resolve_cdn_posts_media(&client, posts).await;
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

        // Succeeded without redundant full-page verification scrape
        Ok(())
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
    if let Some(cap) = BODY_RE.captures(text) {
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

    #[test]
    fn test_is_url_local() {
        assert!(super::is_url_local("http://127.0.0.1:8191"));
        assert!(super::is_url_local("http://localhost:8191/v1"));
        assert!(super::is_url_local("http://[::1]:8191"));
        assert!(!super::is_url_local("http://192.168.1.100:8191"));
        assert!(!super::is_url_local("https://example.com/v1"));
        assert!(!super::is_url_local("not a url"));
    }

    #[test]
    fn test_extract_items_and_tile_ids() {
        let client = FlareSolverrFavoritesClient::new(
            "user1".to_string(),
            "".to_string(),
            "".to_string(),
            "".to_string(),
            "".to_string(),
        );

        let html = r#"
            <span class="thumb">
                <a id="p111" href="index.php?page=post&s=view&id=111">
                    <img src="//img.rule34.xxx/thumbnails/111.jpg" />
                </a>
            </span>
            <span class="thumb">
                <a id="p222" href="index.php?page=post&s=view&id=222">
                    <img src="https://img.rule34.xxx/thumbnails/222.jpg" />
                </a>
            </span>
        "#;

        let tile_ids = client.extract_favorite_tile_ids(html);
        assert_eq!(tile_ids, vec![111, 222]);

        let items = client.extract_items(html);
        assert_eq!(items.len(), 2);
        assert_eq!(
            items[0],
            (111, "https://img.rule34.xxx/thumbnails/111.jpg".to_string())
        );
        assert_eq!(
            items[1],
            (222, "https://img.rule34.xxx/thumbnails/222.jpg".to_string())
        );
    }

    #[test]
    fn test_extract_body_text() {
        let html = "<html><head><title>Test</title></head><body><h1>Hello</h1> <p>World  Test</p></body></html>";
        let body = super::extract_body_text(html);
        assert_eq!(body, "<h1>Hello</h1> <p>World  Test</p>");

        let plain = "No body tag here";
        assert_eq!(super::extract_body_text(plain), "No body tag here");
    }

    #[test]
    fn test_looks_logged_in_and_authenticated() {
        let client = FlareSolverrFavoritesClient::new(
            "user1".to_string(),
            "".to_string(),
            "".to_string(),
            "".to_string(),
            "".to_string(),
        );

        let logged_in_html = r#"<div><a href="index.php?page=account&s=logout">Logout</a></div>"#;
        let logged_out_html = r#"<div><a href="index.php?page=account&s=login">Login</a></div>"#;
        assert!(client.looks_logged_in(logged_in_html));
        assert!(!client.looks_logged_in(logged_out_html));

        let auth_fav_html = r#"<div id="post-list"><a id="p123"></a></div>"#;
        let login_required_html = r#"<form><input name="user"/><input name="pass"/></form>"#;
        assert!(client.looks_favorites_view_authenticated(auth_fav_html));
        assert!(!client.looks_favorites_view_authenticated(login_required_html));
    }

    #[test]
    fn test_hydrate_posts_local_db_cache() {
        let temp_dir = std::env::temp_dir().join(format!(
            "r34-hydrate-test-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&temp_dir).ok();
        let db_path = temp_dir.join("favorites.db");
        let store = crate::db::LocalFavoritesStore::new(Some(db_path));

        let cached_post = crate::models::Post {
            id: 999999,
            tags: vec!["tag1".to_string(), "tag2".to_string()],
            rating: "safe".to_string(),
            score: Some(42),
            width: Some(1920),
            height: Some(1080),
            file_size: Some(123456),
            source: "".to_string(),
            md5: "0123456789abcdef0123456789abcdef".to_string(),
            preview_url: "https://wimg.rule34.xxx/thumbnails/100/thumbnail_0123456789abcdef0123456789abcdef.jpg".to_string(),
            sample_url: "https://wimg.rule34.xxx/samples/100/sample_0123456789abcdef0123456789abcdef.jpg".to_string(),
            file_url: "https://wimg.rule34.xxx//images/100/0123456789abcdef0123456789abcdef.jpg".to_string(),
            created_at: "".to_string(),
        };
        store.add_favorite(&cached_post).unwrap();

        let mut posts = [crate::models::Post {
            id: 999999,
            tags: Vec::new(),
            rating: "".to_string(),
            score: None,
            width: None,
            height: None,
            file_size: None,
            source: "".to_string(),
            md5: "".to_string(),
            preview_url: "".to_string(),
            sample_url: "".to_string(),
            file_url: "".to_string(),
            created_at: "".to_string(),
        }];

        if let Ok(local_posts) = store.list_favorites(None, None) {
            let mut local_map = std::collections::HashMap::new();
            for lp in local_posts {
                local_map.insert(lp.id, lp);
            }
            for post in posts.iter_mut() {
                if let Some(cached) = local_map.get(&post.id) {
                    *post = cached.clone();
                }
            }
        }

        assert_eq!(posts[0].tags, vec!["tag1", "tag2"]);
        assert_eq!(posts[0].score, Some(42));
        assert_eq!(posts[0].rating, "safe");
        std::fs::remove_dir_all(&temp_dir).ok();
    }
}
