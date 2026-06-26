use crate::db::LocalFavoritesStore;
use crate::flaresolverr::FlareSolverrFavoritesClient;
use crate::models::Post;
use crate::settings::AppSettings;
use std::collections::HashMap;

pub async fn sync_remote_favorites(
    settings: &AppSettings,
    local_store: &LocalFavoritesStore,
    debug_logs: &mut String,
    error_logs: &mut String,
    progress_opt: Option<&std::sync::Mutex<crate::models::MutationProgress>>,
    streaks_opt: Option<&std::sync::Mutex<std::collections::HashMap<String, i32>>>,
    has_synced_once_opt: Option<&std::sync::atomic::AtomicBool>,
) -> Result<Vec<Post>, String> {
    let solver_client = FlareSolverrFavoritesClient::new(
        settings.user_id.clone(),
        settings.api_key.clone(),
        settings.website_username.clone(),
        settings.website_password.clone(),
        settings.flaresolverr_url.clone(),
    );

    let now_ts = std::time::SystemTime::now()
        .duration_since(std::time::SystemTime::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64();

    let local_posts = local_store
        .list_favorites(None, None)
        .map_err(|e| format!("Failed to read local favorites: {}", e))?;

    let mut local_by_id = HashMap::new();
    for post in &local_posts {
        local_by_id.insert(post.id, post.clone());
    }

    debug_logs.push_str("\nFetching remote favorites...");
    let mut remote_posts = Vec::new();
    let mut remote_fetch_succeeded = false;
    let mut is_complete = false;
    let limit = std::cmp::max(settings.page_size, 200);

    for attempt in 1..=2 {
        match solver_client.list_favorites(limit, debug_logs).await {
            Ok((posts, complete)) => {
                remote_posts = posts;
                is_complete = complete;
                remote_fetch_succeeded = true;
                break;
            }
            Err(e) => {
                error_logs.push_str(&format!("\nAttempt {} failed: {}", attempt, e));
                tokio::time::sleep(std::time::Duration::from_secs(1)).await;
            }
        }
    }

    if !remote_fetch_succeeded {
        debug_logs.push_str("\nFavorites sync fallback to local cache. Outcome: remote favorites empty or unavailable.");
        if settings.has_credentials()
            && !settings.website_username.is_empty()
            && !settings.website_password.is_empty()
        {
            let mut pending_file = crate::mutations::load_pending_mutations().unwrap_or_default();
            let has_work = !pending_file.add.is_empty() || !pending_file.remove.is_empty();
            if has_work {
                debug_logs.push_str("\nProcessing pending mutations during fallback...");
                if let (Some(prog), Some(streaks)) = (progress_opt, streaks_opt) {
                    let due_add_ids: std::collections::HashSet<i64> = pending_file
                        .add
                        .iter()
                        .filter(|m| m.next_attempt_at <= now_ts)
                        .map(|m| m.id)
                        .collect();
                    let due_remove_ids: std::collections::HashSet<i64> = pending_file
                        .remove
                        .iter()
                        .filter(|m| m.next_attempt_at <= now_ts)
                        .map(|m| m.id)
                        .collect();

                    solver_client.close().await;

                    let mutation_res =
                        crate::mutations::process_pending_mutations_impl(settings, prog, streaks)
                            .await;

                    if let Err(e) = mutation_res {
                        debug_logs
                            .push_str(&format!("\nFailed to process pending mutations: {}", e));
                    } else {
                        debug_logs.push_str("\nMutations processed successfully.");
                    }

                    // Reload pending mutations to see what succeeded
                    pending_file = crate::mutations::load_pending_mutations().unwrap_or_default();

                    // Confirm successfully completed mutations and remove them from the queue!
                    let mut confirmed_add_count = 0;
                    pending_file.add.retain(|m| {
                        let confirmed = due_add_ids.contains(&m.id)
                            && m.attempts == 0
                            && (m.next_attempt_at - now_ts) > 100.0;
                        if confirmed {
                            confirmed_add_count += 1;
                        }
                        !confirmed
                    });

                    let mut confirmed_remove_count = 0;
                    pending_file.remove.retain(|m| {
                        let confirmed = due_remove_ids.contains(&m.id)
                            && m.attempts == 0
                            && (m.next_attempt_at - now_ts) > 100.0;
                        if confirmed {
                            confirmed_remove_count += 1;
                        }
                        !confirmed
                    });

                    let total_confirmed = confirmed_add_count + confirmed_remove_count;
                    if total_confirmed > 0
                        && crate::mutations::save_pending_mutations(&pending_file).is_ok()
                    {
                        debug_logs.push_str(&format!(
                            "\nConfirmed {} pending mutations (adds/removes) on remote rule34 account.",
                            total_confirmed
                        ));
                        if let Some(mutex) = progress_opt {
                            let mut prog = mutex.lock().unwrap();
                            prog.completed_mutations += total_confirmed;
                            prog.current_pending =
                                crate::mutations::count_active_mutations(&pending_file);
                        }
                    }
                }
            }
        }
        solver_client.close().await;
        return Ok(local_posts);
    }

    // Set has_synced_once to true since we successfully fetched the remote favorites!
    if let Some(atomic) = has_synced_once_opt {
        atomic.store(true, std::sync::atomic::Ordering::Relaxed);
    }

    // Load pending mutations
    let mut pending_file = crate::mutations::load_pending_mutations().unwrap_or_default();

    // 1. Detect remote changes since the last session
    let pending_add_ids: std::collections::HashSet<i64> =
        pending_file.add.iter().map(|m| m.id).collect();
    let pending_remove_ids: std::collections::HashSet<i64> =
        pending_file.remove.iter().map(|m| m.id).collect();
    let local_ids: std::collections::HashSet<i64> = local_posts.iter().map(|p| p.id).collect();

    // Filter out pending removes from the remote list for change detection
    let effective_remote_posts_for_detection: Vec<Post> = remote_posts
        .iter()
        .filter(|p| !pending_remove_ids.contains(&p.id))
        .cloned()
        .collect();
    let remote_ids_for_detection: std::collections::HashSet<i64> =
        effective_remote_posts_for_detection
            .iter()
            .map(|p| p.id)
            .collect();

    let mut remote_changes_detected = false;

    // Check for remote additions (in remote but not in local)
    for rid in &remote_ids_for_detection {
        if !local_ids.contains(rid) {
            remote_changes_detected = true;
            break;
        }
    }

    // Check for remote deletions (in local but not in remote, and not a local pending add or pending remove)
    if !remote_changes_detected && is_complete {
        for lid in &local_ids {
            if !remote_ids_for_detection.contains(lid)
                && !pending_add_ids.contains(lid)
                && !pending_remove_ids.contains(lid)
            {
                remote_changes_detected = true;
                break;
            }
        }
    }

    let strategy = settings.sync_conflict_strategy.trim().to_lowercase();
    let use_remote_wins = strategy == "remote_wins" && remote_changes_detected && is_complete;

    // Process remaining pending mutations (run process_pending_mutations_impl)
    let mut due_add_ids = std::collections::HashSet::new();
    let mut due_remove_ids = std::collections::HashSet::new();

    if settings.has_credentials()
        && !settings.website_username.is_empty()
        && !settings.website_password.is_empty()
    {
        let has_work = !pending_file.add.is_empty() || !pending_file.remove.is_empty();
        if has_work {
            debug_logs.push_str("\nProcessing pending mutations...");
            if let (Some(prog), Some(streaks)) = (progress_opt, streaks_opt) {
                due_add_ids = pending_file
                    .add
                    .iter()
                    .filter(|m| m.next_attempt_at <= now_ts)
                    .map(|m| m.id)
                    .collect();
                due_remove_ids = pending_file
                    .remove
                    .iter()
                    .filter(|m| m.next_attempt_at <= now_ts)
                    .map(|m| m.id)
                    .collect();

                // Drop client session before running mutations to let it connect again or use same client
                solver_client.close().await;

                let mutation_res =
                    crate::mutations::process_pending_mutations_impl(settings, prog, streaks).await;

                if let Err(e) = mutation_res {
                    debug_logs.push_str(&format!("\nFailed to process pending mutations: {}", e));
                } else {
                    debug_logs.push_str("\nMutations processed successfully.");
                }

                // Reload pending mutations to see what succeeded
                pending_file = crate::mutations::load_pending_mutations().unwrap_or_default();
            }
        }
    }

    // Now update remote_posts to reflect successfully processed mutations!
    let raw_remote_ids_after_mut: std::collections::HashSet<i64> =
        remote_posts.iter().map(|p| p.id).collect();

    // Reload raw_remote_ids with successfully added posts and remove successfully deleted posts
    for m in &pending_file.add {
        let succeeded =
            due_add_ids.contains(&m.id) && m.attempts == 0 && (m.next_attempt_at - now_ts) > 100.0;
        if succeeded && !raw_remote_ids_after_mut.contains(&m.id) {
            if let Some(post) = local_by_id.get(&m.id) {
                remote_posts.push(post.clone());
            }
        }
    }
    for m in &pending_file.remove {
        let succeeded = due_remove_ids.contains(&m.id)
            && m.attempts == 0
            && (m.next_attempt_at - now_ts) > 100.0;
        if succeeded {
            remote_posts.retain(|p| p.id != m.id);
        }
    }

    // Recompute raw remote ids after local mutations update
    let raw_remote_ids_updated: std::collections::HashSet<i64> =
        remote_posts.iter().map(|p| p.id).collect();

    // Confirm successfully completed mutations and remove them from the queue!
    let mut confirmed_add_count = 0;
    pending_file.add.retain(|m| {
        let confirmed = (due_add_ids.contains(&m.id)
            && m.attempts == 0
            && (m.next_attempt_at - now_ts) > 100.0)
            || raw_remote_ids_updated.contains(&m.id);
        if confirmed {
            confirmed_add_count += 1;
        }
        !confirmed
    });

    let mut confirmed_remove_count = 0;
    pending_file.remove.retain(|m| {
        let confirmed = (due_remove_ids.contains(&m.id)
            && m.attempts == 0
            && (m.next_attempt_at - now_ts) > 100.0)
            || (is_complete && !raw_remote_ids_updated.contains(&m.id));
        if confirmed {
            confirmed_remove_count += 1;
        }
        !confirmed
    });

    let total_confirmed = confirmed_add_count + confirmed_remove_count;
    if total_confirmed > 0 && crate::mutations::save_pending_mutations(&pending_file).is_ok() {
        debug_logs.push_str(&format!(
            "\nConfirmed {} pending mutations (adds/removes) on remote rule34 account.",
            total_confirmed
        ));
        if let Some(mutex) = progress_opt {
            let mut prog = mutex.lock().unwrap();
            prog.completed_mutations += total_confirmed;
            prog.current_pending = crate::mutations::count_active_mutations(&pending_file);
        }
    }

    // Filter out remaining pending removes (i.e. those that failed to execute) from the remote list for database sync
    let remaining_pending_remove_ids: std::collections::HashSet<i64> =
        pending_file.remove.iter().map(|m| m.id).collect();

    let effective_remote_posts: Vec<Post> = remote_posts
        .into_iter()
        .filter(|p| !remaining_pending_remove_ids.contains(&p.id))
        .collect();

    if strategy == "remote_wins" && !remote_changes_detected {
        debug_logs.push_str("\nFavorites sync strategy remote_wins, but no remote changes detected. Keeping local cache.");
        return Ok(local_posts);
    }

    if effective_remote_posts.is_empty() {
        if strategy == "local_wins" {
            debug_logs.push_str("\nFavorites sync remote empty (local_wins). Keeping local cache.");
            return Ok(local_posts);
        }
        if !use_remote_wins {
            debug_logs.push_str("\nFavorites sync remote empty (merge). Keeping local cache.");
            return Ok(local_posts);
        }
        // remote_wins: wipe local cache but preserve pending adds
        debug_logs.push_str("\nFavorites sync remote empty (remote_wins). Clearing local cache but preserving pending adds.");
        let mut final_posts = Vec::new();
        for local_post in &local_posts {
            let pending_add_ids: std::collections::HashSet<i64> =
                pending_file.add.iter().map(|m| m.id).collect();
            if pending_add_ids.contains(&local_post.id) {
                final_posts.push(local_post.clone());
            }
        }
        local_store
            .replace_all(&final_posts)
            .map_err(|e| format!("Failed to clear database: {}", e))?;
        return Ok(final_posts);
    }

    if strategy == "local_wins" {
        debug_logs.push_str("\nFavorites sync strategy local_wins. Keeping local favorites cache.");
        return Ok(local_posts);
    }

    if use_remote_wins {
        debug_logs.push_str(
            "\nFavorites sync strategy remote_wins. Replacing local cache with remote posts (preserving pending additions).",
        );
        let mut final_posts = effective_remote_posts.clone();
        let pending_add_ids: std::collections::HashSet<i64> =
            pending_file.add.iter().map(|m| m.id).collect();
        for local_post in &local_posts {
            if pending_add_ids.contains(&local_post.id)
                && !final_posts.iter().any(|p| p.id == local_post.id)
            {
                final_posts.push(local_post.clone());
            }
        }
        local_store
            .replace_all(&final_posts)
            .map_err(|e| format!("Failed to update database: {}", e))?;
        return Ok(local_store
            .list_favorites(None, None)
            .unwrap_or(final_posts));
    }

    // Merge strategy (no remote changes detected, or explicit merge strategy)
    debug_logs.push_str("\nFavorites sync strategy merge. Merging local and remote favorites...");
    let merged = merge_favorites(&local_posts, &effective_remote_posts);

    local_store
        .replace_all(&merged)
        .map_err(|e| format!("Failed to update database with merged posts: {}", e))?;

    debug_logs.push_str("\nSync completed successfully.");

    // Close session to cleanup container tasks
    solver_client.close().await;

    Ok(local_store.list_favorites(None, None).unwrap_or(merged))
}

pub fn merge_favorites(local_posts: &[Post], remote_posts: &[Post]) -> Vec<Post> {
    let mut local_by_id = HashMap::new();
    for post in local_posts {
        local_by_id.insert(post.id, post);
    }

    let mut merged = Vec::new();
    let mut remote_ids = std::collections::HashSet::new();

    for remote in remote_posts {
        remote_ids.insert(remote.id);
        if let Some(local) = local_by_id.get(&remote.id) {
            // Merge posts
            let mut merged_post = remote.clone();
            if merged_post.tags.is_empty() {
                merged_post.tags = local.tags.clone();
            }
            if merged_post.rating.is_empty() {
                merged_post.rating = local.rating.clone();
            }
            if merged_post.score.is_none() {
                merged_post.score = local.score;
            }
            if merged_post.width.is_none() {
                merged_post.width = local.width;
            }
            if merged_post.height.is_none() {
                merged_post.height = local.height;
            }
            if merged_post.file_size.is_none() {
                merged_post.file_size = local.file_size;
            }
            if merged_post.source.is_empty() {
                merged_post.source = local.source.clone();
            }
            if merged_post.md5.is_empty() {
                merged_post.md5 = local.md5.clone();
            }
            if merged_post.preview_url.is_empty() {
                merged_post.preview_url = local.preview_url.clone();
            }
            if merged_post.sample_url.is_empty() {
                merged_post.sample_url = local.sample_url.clone();
            }
            if merged_post.file_url.is_empty() {
                merged_post.file_url = local.file_url.clone();
            }
            if merged_post.created_at.is_empty() {
                merged_post.created_at = local.created_at.clone();
            }

            merged.push(merged_post);
        } else {
            merged.push(remote.clone());
        }
    }

    // Add local posts not present on remote
    for local in local_posts {
        if !remote_ids.contains(&local.id) {
            merged.push(local.clone());
        }
    }

    merged
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_merge_favorites_empty() {
        let local: Vec<Post> = Vec::new();
        let remote: Vec<Post> = Vec::new();
        let merged = merge_favorites(&local, &remote);
        assert!(merged.is_empty());
    }

    #[test]
    fn test_merge_favorites_only_local() {
        let local = vec![Post {
            id: 1,
            tags: vec!["tag1".to_string()],
            rating: "q".to_string(),
            score: Some(10),
            width: None,
            height: None,
            file_size: None,
            source: "".to_string(),
            md5: "md5_1".to_string(),
            preview_url: "".to_string(),
            sample_url: "".to_string(),
            file_url: "".to_string(),
            created_at: "".to_string(),
        }];
        let remote = vec![];
        let merged = merge_favorites(&local, &remote);
        assert_eq!(merged.len(), 1);
        assert_eq!(merged[0].id, 1);
        assert_eq!(merged[0].tags, vec!["tag1".to_string()]);
    }

    #[test]
    fn test_merge_favorites_only_remote() {
        let local = vec![];
        let remote = vec![Post {
            id: 2,
            tags: vec!["tag2".to_string()],
            rating: "s".to_string(),
            score: Some(5),
            width: None,
            height: None,
            file_size: None,
            source: "".to_string(),
            md5: "md5_2".to_string(),
            preview_url: "".to_string(),
            sample_url: "".to_string(),
            file_url: "".to_string(),
            created_at: "".to_string(),
        }];
        let merged = merge_favorites(&local, &remote);
        assert_eq!(merged.len(), 1);
        assert_eq!(merged[0].id, 2);
        assert_eq!(merged[0].tags, vec!["tag2".to_string()]);
    }

    #[test]
    fn test_merge_favorites_combine_and_resolve() {
        let local = vec![
            Post {
                id: 1,
                tags: vec!["tag1".to_string()],
                rating: "q".to_string(),
                score: Some(10),
                width: Some(100),
                height: Some(200),
                file_size: Some(1000),
                source: "src_local".to_string(),
                md5: "md5_1".to_string(),
                preview_url: "preview_local".to_string(),
                sample_url: "sample_local".to_string(),
                file_url: "file_local".to_string(),
                created_at: "time_local".to_string(),
            },
            Post {
                id: 2,
                tags: vec!["tag2".to_string()],
                rating: "s".to_string(),
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
            },
        ];

        let remote = vec![
            Post {
                id: 2,
                tags: vec![],
                rating: "".to_string(),
                score: Some(20),
                width: Some(300),
                height: Some(400),
                file_size: Some(2000),
                source: "src_remote".to_string(),
                md5: "md5_2".to_string(),
                preview_url: "preview_remote".to_string(),
                sample_url: "sample_remote".to_string(),
                file_url: "file_remote".to_string(),
                created_at: "time_remote".to_string(),
            },
            Post {
                id: 3,
                tags: vec!["tag3".to_string()],
                rating: "e".to_string(),
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
            },
        ];

        let merged = merge_favorites(&local, &remote);
        assert_eq!(merged.len(), 3);

        // Verify Post 2
        let p2 = merged.iter().find(|p| p.id == 2).unwrap();
        assert_eq!(p2.tags, vec!["tag2".to_string()]);
        assert_eq!(p2.rating, "s");
        assert_eq!(p2.score, Some(20));
        assert_eq!(p2.width, Some(300));
        assert_eq!(p2.source, "src_remote");

        // Verify Post 3
        let p3 = merged.iter().find(|p| p.id == 3).unwrap();
        assert_eq!(p3.tags, vec!["tag3".to_string()]);
        assert_eq!(p3.rating, "e");

        // Verify Post 1
        let p1 = merged.iter().find(|p| p.id == 1).unwrap();
        assert_eq!(p1.tags, vec!["tag1".to_string()]);
        assert_eq!(p1.rating, "q");
        assert_eq!(p1.score, Some(10));
        assert_eq!(p1.width, Some(100));
        assert_eq!(p1.source, "src_local");
    }

    #[tokio::test]
    async fn test_sync_remote_favorites_fallback_mutations() {
        let _guard = crate::mutations::TEST_MUTEX.lock().await;

        let mut path = std::env::temp_dir();
        let name = format!(
            "r34_sync_test_{}.db",
            std::time::SystemTime::now()
                .duration_since(std::time::SystemTime::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        );
        path.push(name);
        let store = LocalFavoritesStore::new(Some(path.clone()));

        // Settings with invalid flaresolverr_url to force remote fetch failure
        let settings = AppSettings {
            user_id: "dummy_user".to_string(),
            api_key: "dummy_key".to_string(),
            website_username: "dummy_user".to_string(),
            website_password: "dummy_password".to_string(),
            flaresolverr_url: "http://127.0.0.1:9999".to_string(),
            ..Default::default()
        };

        // Clear existing test pending mutations if any
        let pm_path = crate::mutations::pending_mutations_path();
        if pm_path.exists() {
            std::fs::remove_file(&pm_path).ok();
        }

        // Queue a pending add so we have work in the queue
        crate::mutations::queue_pending_add(77777, "fallback test").unwrap();

        let mut debug_logs = String::new();
        let mut error_logs = String::new();
        let progress = std::sync::Mutex::new(crate::models::MutationProgress::default());
        let streaks = std::sync::Mutex::new(std::collections::HashMap::new());
        let has_synced_once = std::sync::atomic::AtomicBool::new(false);

        // Run sync_remote_favorites
        // Since flaresolverr_url is invalid, fetching remote favorites fails.
        // It should fallback to local, but it should still call process_pending_mutations_impl.
        let res = sync_remote_favorites(
            &settings,
            &store,
            &mut debug_logs,
            &mut error_logs,
            Some(&progress),
            Some(&streaks),
            Some(&has_synced_once),
        )
        .await;

        println!("SYNC_TEST_DEBUG_LOGS:\n{}", debug_logs);
        println!("SYNC_TEST_ERROR_LOGS:\n{}", error_logs);
        assert!(res.is_ok());

        let pending = crate::mutations::load_pending_mutations().unwrap();
        assert_eq!(pending.add.len(), 1);
        assert!(!pending.add[0].last_error.is_empty());
        assert!(
            pending.add[0].last_error.contains("connection")
                || pending.add[0]
                    .last_error
                    .contains("Solver connection error")
                || pending.add[0].last_error.contains("refused")
                || pending.add[0].last_error.contains("9999")
        );

        if pm_path.exists() {
            std::fs::remove_file(&pm_path).ok();
        }
        if path.exists() {
            std::fs::remove_file(&path).ok();
        }
    }
}
