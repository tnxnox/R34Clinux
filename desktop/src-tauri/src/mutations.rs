use crate::flaresolverr::FlareSolverrFavoritesClient;
use crate::models::MutationProgress;
use crate::settings::AppSettings;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::time::SystemTime;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PendingMutation {
    pub id: i64,
    pub attempts: i32,
    pub first_queued_at: f64,
    pub next_attempt_at: f64,
    pub last_error: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct PendingMutationsFile {
    pub add: Vec<PendingMutation>,
    pub remove: Vec<PendingMutation>,
}

pub fn pending_mutations_path() -> PathBuf {
    if cfg!(test) {
        return std::env::temp_dir().join("pending-mutations-test.json");
    }
    let root = if let Ok(xdg_config) = std::env::var("XDG_CONFIG_HOME") {
        PathBuf::from(xdg_config).join("R34LinuxClient")
    } else {
        let home = std::env::var("HOME").unwrap_or_else(|_| "/".to_string());
        PathBuf::from(home).join(".config").join("R34LinuxClient")
    };
    root.join("pending-mutations.json")
}

pub fn load_pending_mutations() -> Result<PendingMutationsFile, String> {
    let path = pending_mutations_path();
    if !path.exists() {
        return Ok(PendingMutationsFile::default());
    }
    let content = fs::read_to_string(&path)
        .map_err(|e| format!("Failed to read pending mutations file: {}", e))?;
    serde_json::from_str(&content)
        .map_err(|e| format!("Failed to parse pending mutations JSON: {}", e))
}

pub fn save_pending_mutations(data: &PendingMutationsFile) -> Result<(), String> {
    let path = pending_mutations_path();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).ok();
    }
    let content = serde_json::to_string_pretty(data)
        .map_err(|e| format!("Failed to serialize pending mutations: {}", e))?;
    fs::write(&path, content).map_err(|e| format!("Failed to write pending mutations file: {}", e))
}

pub fn count_active_mutations(file: &PendingMutationsFile) -> usize {
    let now_ts = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64();
    let mut count = 0;
    for m in &file.add {
        if m.next_attempt_at <= now_ts {
            count += 1;
        }
    }
    for m in &file.remove {
        if m.next_attempt_at <= now_ts {
            count += 1;
        }
    }
    count
}

pub fn queue_pending_add(post_id: i64, reason: &str) -> Result<(), String> {
    let mut file = load_pending_mutations()?;

    // Remove from opposite queue
    file.remove.retain(|m| m.id != post_id);

    let now = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64();

    if let Some(existing) = file.add.iter_mut().find(|m| m.id == post_id) {
        existing.last_error = reason.to_string();
    } else {
        file.add.push(PendingMutation {
            id: post_id,
            attempts: 0,
            first_queued_at: now,
            next_attempt_at: 0.0,
            last_error: reason.to_string(),
        });
    }

    save_pending_mutations(&file)
}

pub fn queue_pending_remove(post_id: i64, reason: &str) -> Result<(), String> {
    let mut file = load_pending_mutations()?;

    // Remove from opposite queue
    file.add.retain(|m| m.id != post_id);

    let now = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64();

    if let Some(existing) = file.remove.iter_mut().find(|m| m.id == post_id) {
        existing.last_error = reason.to_string();
    } else {
        file.remove.push(PendingMutation {
            id: post_id,
            attempts: 0,
            first_queued_at: now,
            next_attempt_at: 0.0,
            last_error: reason.to_string(),
        });
    }

    save_pending_mutations(&file)
}

#[allow(dead_code)]
pub fn clear_pending_add(post_id: i64) -> Result<(), String> {
    let mut file = load_pending_mutations()?;
    file.add.retain(|m| m.id != post_id);
    save_pending_mutations(&file)
}

#[allow(dead_code)]
pub fn clear_pending_remove(post_id: i64) -> Result<(), String> {
    let mut file = load_pending_mutations()?;
    file.remove.retain(|m| m.id != post_id);
    save_pending_mutations(&file)
}

fn extract_retry_after_seconds(message: &str) -> Option<f64> {
    let re = regex::Regex::new(r"(?i)retry[-_ ]?after[^0-9]*(\d+)").unwrap();
    if let Some(cap) = re.captures(message) {
        if let Ok(val) = cap[1].parse::<f64>() {
            return Some(val.abs());
        }
    }
    None
}

fn random_range(min: f64, max: f64) -> f64 {
    use std::collections::hash_map::DefaultHasher;
    use std::hash::{Hash, Hasher};
    let mut hasher = DefaultHasher::new();
    SystemTime::now().hash(&mut hasher);
    let val = hasher.finish();
    let fraction = (val % 100_000) as f64 / 100_000.0;
    min + fraction * (max - min)
}

pub fn compute_backoff_seconds(_attempts: i32, message: &str, streak: i32) -> f64 {
    let retry_after = extract_retry_after_seconds(message);
    let current_streak = streak + 1;

    let min_streak = std::cmp::min(current_streak, 6);
    let mut base_delay = 1.25 * 2.0f64.powi(min_streak);
    if base_delay > 120.0 {
        base_delay = 120.0;
    }
    if let Some(ra) = retry_after {
        if ra > base_delay {
            base_delay = ra;
        }
    }

    let max_jitter = if base_delay * 0.35 > 0.4 {
        base_delay * 0.35
    } else {
        0.4
    };
    let jitter = random_range(0.2, max_jitter);
    base_delay + jitter
}

pub fn is_rate_limited_error(message: &str) -> bool {
    let lowered = message.to_lowercase();
    lowered.contains("429")
        || lowered.contains("rate limit")
        || lowered.contains("rate-limit")
        || lowered.contains("rate limited")
        || lowered.contains("too many requests")
}

pub async fn process_pending_mutations_impl(
    settings: &AppSettings,
    progress_mutex: &std::sync::Mutex<MutationProgress>,
    streaks_mutex: &std::sync::Mutex<HashMap<String, i32>>,
) -> Result<Option<f64>, String> {
    let file = load_pending_mutations()?;

    let now_ts = SystemTime::now()
        .duration_since(SystemTime::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64();

    let queue_len = file.add.len() + file.remove.len();
    if queue_len == 0 {
        let mut prog = progress_mutex.lock().unwrap();
        prog.total_mutations = 0;
        prog.completed_mutations = 0;
        prog.current_pending = 0;
        return Ok(None);
    }

    // Check backoffs
    let mut next_retry_remaining: Option<f64> = None;
    let mut to_process_add = Vec::new();
    let mut to_process_remove = Vec::new();

    for m in &file.remove {
        if m.next_attempt_at > now_ts {
            let rem = m.next_attempt_at - now_ts;
            next_retry_remaining = Some(next_retry_remaining.map_or(rem, |r| r.min(rem)));
        } else {
            to_process_remove.push(m.clone());
        }
    }

    for m in &file.add {
        if m.next_attempt_at > now_ts {
            let rem = m.next_attempt_at - now_ts;
            next_retry_remaining = Some(next_retry_remaining.map_or(rem, |r| r.min(rem)));
        } else {
            to_process_add.push(m.clone());
        }
    }

    if to_process_add.is_empty() && to_process_remove.is_empty() {
        return Ok(next_retry_remaining);
    }

    // We have active work to process!
    let solver_client = FlareSolverrFavoritesClient::new(
        settings.user_id.clone(),
        settings.api_key.clone(),
        settings.website_username.clone(),
        settings.website_password.clone(),
        settings.flaresolverr_url.clone(),
    );

    let mut debug_logs = String::new();

    // Removals
    for m in to_process_remove {
        debug_logs.clear();
        match solver_client.remove_favorite(m.id, &mut debug_logs).await {
            Ok(_) => {
                let mut current_file = load_pending_mutations()?;
                if let Some(item) = current_file.remove.iter_mut().find(|item| item.id == m.id) {
                    item.attempts = 0;
                    item.next_attempt_at = now_ts + 600.0;
                }
                save_pending_mutations(&current_file)?;

                {
                    let mut streaks = streaks_mutex.lock().unwrap();
                    streaks.insert("remove".to_string(), 0);
                }

                {
                    let mut prog = progress_mutex.lock().unwrap();
                    prog.completed_mutations += 1;
                    prog.current_pending = count_active_mutations(&current_file);
                }
            }
            Err(err_msg) => {
                let mut current_file = load_pending_mutations()?;
                let mut discarded = false;
                if let Some(item) = current_file.remove.iter_mut().find(|item| item.id == m.id) {
                    item.attempts += 1;
                    if item.attempts >= 5 {
                        discarded = true;
                    } else {
                        let streak = {
                            let mut streaks = streaks_mutex.lock().unwrap();
                            let s = streaks.entry("remove".to_string()).or_insert(0);
                            *s += 1;
                            *s
                        };

                        let delay = compute_backoff_seconds(item.attempts, &err_msg, streak);
                        let next_attempt = now_ts + delay;
                        item.next_attempt_at = next_attempt;
                        item.last_error = err_msg.clone();
                        next_retry_remaining =
                            Some(next_retry_remaining.map_or(delay, |r| r.min(delay)));
                    }
                }

                if discarded {
                    current_file.remove.retain(|item| item.id != m.id);
                    {
                        let mut prog = progress_mutex.lock().unwrap();
                        prog.completed_mutations += 1;
                        prog.current_pending = count_active_mutations(&current_file);
                    }
                }
                save_pending_mutations(&current_file)?;

                if is_rate_limited_error(&err_msg) && !discarded {
                    break;
                }
            }
        }
    }

    // Additions
    let file_after_removals = load_pending_mutations()?;
    let to_process_add_still_pending: Vec<PendingMutation> = to_process_add
        .into_iter()
        .filter(|m| file_after_removals.add.iter().any(|item| item.id == m.id))
        .collect();

    for m in to_process_add_still_pending {
        debug_logs.clear();
        match solver_client.add_favorite(m.id, &mut debug_logs).await {
            Ok(_) => {
                let mut current_file = load_pending_mutations()?;
                if let Some(item) = current_file.add.iter_mut().find(|item| item.id == m.id) {
                    item.attempts = 0;
                    item.next_attempt_at = now_ts + 600.0;
                }
                save_pending_mutations(&current_file)?;

                {
                    let mut streaks = streaks_mutex.lock().unwrap();
                    streaks.insert("add".to_string(), 0);
                }

                {
                    let mut prog = progress_mutex.lock().unwrap();
                    prog.completed_mutations += 1;
                    prog.current_pending = count_active_mutations(&current_file);
                }
            }
            Err(err_msg) => {
                let mut current_file = load_pending_mutations()?;
                let mut discarded = false;
                if let Some(item) = current_file.add.iter_mut().find(|item| item.id == m.id) {
                    item.attempts += 1;
                    if item.attempts >= 5 {
                        discarded = true;
                    } else {
                        let streak = {
                            let mut streaks = streaks_mutex.lock().unwrap();
                            let s = streaks.entry("add".to_string()).or_insert(0);
                            *s += 1;
                            *s
                        };

                        let delay = compute_backoff_seconds(item.attempts, &err_msg, streak);
                        let next_attempt = now_ts + delay;
                        item.next_attempt_at = next_attempt;
                        item.last_error = err_msg.clone();
                        next_retry_remaining =
                            Some(next_retry_remaining.map_or(delay, |r| r.min(delay)));
                    }
                }

                if discarded {
                    current_file.add.retain(|item| item.id != m.id);
                    {
                        let mut prog = progress_mutex.lock().unwrap();
                        prog.completed_mutations += 1;
                        prog.current_pending = count_active_mutations(&current_file);
                    }
                }
                save_pending_mutations(&current_file)?;

                if is_rate_limited_error(&err_msg) && !discarded {
                    break;
                }
            }
        }
    }

    solver_client.close().await;
    Ok(next_retry_remaining)
}

#[cfg(test)]
mod tests {
    use super::*;

    static TEST_MUTEX: std::sync::Mutex<()> = std::sync::Mutex::new(());

    #[test]
    fn test_is_rate_limited_error() {
        assert!(is_rate_limited_error("HTTP 429 Rate Limited"));
        assert!(is_rate_limited_error("too many requests"));
        assert!(is_rate_limited_error(
            "Rate limited while checking favorites view."
        ));
        assert!(is_rate_limited_error("rate limit exceeded"));
        assert!(is_rate_limited_error("rate-limited"));
        assert!(!is_rate_limited_error("some normal error"));
    }

    #[test]
    fn test_compute_backoff_seconds() {
        // Streak 0 (current_streak = 1, base_delay = 2.5, jitter max = 0.875)
        let backoff = compute_backoff_seconds(1, "error", 0);
        assert!((2.7..=3.38).contains(&backoff));

        // Streak 5 (current_streak = 6, base_delay = 80.0, jitter max = 28.0)
        let backoff_large = compute_backoff_seconds(1, "error", 5);
        assert!((80.2..=108.0).contains(&backoff_large));

        // Retry after header in message
        let backoff_retry_after = compute_backoff_seconds(1, "retry after 60", 0);
        assert!(backoff_retry_after >= 60.0);
    }

    #[test]
    fn test_queue_and_persistence() {
        let _guard = TEST_MUTEX.lock().unwrap();
        let test_path = pending_mutations_path();
        if test_path.exists() {
            fs::remove_file(&test_path).ok();
        }

        // Initially empty
        let initial = load_pending_mutations().unwrap();
        assert_eq!(initial.add.len(), 0);
        assert_eq!(initial.remove.len(), 0);

        // Add pending favorite
        queue_pending_add(1001, "test add").unwrap();
        let after_add = load_pending_mutations().unwrap();
        assert_eq!(after_add.add.len(), 1);
        assert_eq!(after_add.add[0].id, 1001);
        assert_eq!(after_add.add[0].last_error, "test add");
        assert_eq!(after_add.remove.len(), 0);

        // Add pending remove for the same ID (should cancel the pending add!)
        queue_pending_remove(1001, "test remove").unwrap();
        let after_remove = load_pending_mutations().unwrap();
        assert_eq!(after_remove.add.len(), 0);
        assert_eq!(after_remove.remove.len(), 1);
        assert_eq!(after_remove.remove[0].id, 1001);
        assert_eq!(after_remove.remove[0].last_error, "test remove");

        // Clear it
        clear_pending_remove(1001).unwrap();
        let cleared = load_pending_mutations().unwrap();
        assert_eq!(cleared.add.len(), 0);
        assert_eq!(cleared.remove.len(), 0);

        if test_path.exists() {
            fs::remove_file(&test_path).ok();
        }
    }

    #[tokio::test]
    #[allow(clippy::await_holding_lock)]
    async fn test_discard_failing_mutation() {
        let _guard = TEST_MUTEX.lock().unwrap();
        let test_path = pending_mutations_path();
        if test_path.exists() {
            fs::remove_file(&test_path).ok();
        }

        // Set up dummy app settings with empty website login details so ensure_web_login fails immediately
        let settings = AppSettings {
            user_id: "dummy_user".to_string(),
            api_key: "dummy_key".to_string(),
            website_username: "".to_string(),
            website_password: "".to_string(),
            flaresolverr_url: "http://nonexistent.invalid".to_string(),
            ..Default::default()
        };

        // Queue a pending add
        queue_pending_add(99999, "should fail").unwrap();

        let progress = std::sync::Mutex::new(MutationProgress::default());
        let streaks = std::sync::Mutex::new(HashMap::new());

        // Process once - should fail and attempts becomes 1
        let res1 = process_pending_mutations_impl(&settings, &progress, &streaks).await;
        println!("DEBUG: First process result: {:?}", res1);
        let file = load_pending_mutations().unwrap();
        println!("DEBUG: File after first process: {:?}", file);
        assert_eq!(file.add.len(), 1);
        assert_eq!(file.add[0].attempts, 1);

        // Modify attempt count manually to 4 so next failure discards it
        {
            let mut file = load_pending_mutations().unwrap();
            file.add[0].attempts = 4;
            // Clear backoff to allow immediate retry
            file.add[0].next_attempt_at = 0.0;
            save_pending_mutations(&file).unwrap();
        }
        println!(
            "DEBUG: File after manual update: {:?}",
            load_pending_mutations().unwrap()
        );

        // Process again - should fail and attempts becomes 5, discarding the mutation
        let res2 = process_pending_mutations_impl(&settings, &progress, &streaks).await;
        println!("DEBUG: Second process result: {:?}", res2);
        let file_after = load_pending_mutations().unwrap();
        println!("DEBUG: File after second process: {:?}", file_after);
        assert_eq!(file_after.add.len(), 0);

        if test_path.exists() {
            fs::remove_file(&test_path).ok();
        }
    }
}
