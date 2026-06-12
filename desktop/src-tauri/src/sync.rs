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
) -> Result<Vec<Post>, String> {
    let solver_client = FlareSolverrFavoritesClient::new(
        settings.user_id.clone(),
        settings.api_key.clone(),
        settings.website_username.clone(),
        settings.website_password.clone(),
        settings.flaresolverr_url.clone(),
    );

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
    let limit = std::cmp::max(settings.page_size, 200);

    for attempt in 1..=2 {
        match solver_client.list_favorites(limit, debug_logs).await {
            Ok(posts) => {
                remote_posts = posts;
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
        return Ok(local_posts);
    }

    // Load pending mutations
    let mut pending_file = crate::mutations::load_pending_mutations().unwrap_or_default();
    let pending_remove_ids: std::collections::HashSet<i64> =
        pending_file.remove.iter().map(|m| m.id).collect();

    // Filter out pending removes from the remote list
    let effective_remote_posts: Vec<Post> = remote_posts
        .into_iter()
        .filter(|p| !pending_remove_ids.contains(&p.id))
        .collect();

    let remote_ids: std::collections::HashSet<i64> =
        effective_remote_posts.iter().map(|p| p.id).collect();

    // Confirm pending adds that are now present on remote
    let mut confirmed_add_count = 0;
    pending_file.add.retain(|m| {
        let confirmed = remote_ids.contains(&m.id);
        if confirmed {
            confirmed_add_count += 1;
        }
        !confirmed
    });

    if confirmed_add_count > 0 && crate::mutations::save_pending_mutations(&pending_file).is_ok() {
        debug_logs.push_str(&format!(
            "\nConfirmed {} pending adds on remote rule34 account.",
            confirmed_add_count
        ));
        if let Some(mutex) = progress_opt {
            let mut prog = mutex.lock().unwrap();
            prog.completed_mutations += confirmed_add_count;
            prog.current_pending = pending_file.add.len() + pending_file.remove.len();
        }
    }

    let strategy = settings.sync_conflict_strategy.trim().to_lowercase();

    if effective_remote_posts.is_empty() {
        if strategy == "local_wins" {
            debug_logs.push_str("\nFavorites sync remote empty (local_wins). Keeping local cache.");
            return Ok(local_posts);
        }
        if strategy == "merge" {
            debug_logs.push_str("\nFavorites sync remote empty (merge). Keeping local cache.");
            return Ok(local_posts);
        }
        // remote_wins: wipe local cache
        debug_logs.push_str("\nFavorites sync remote empty (remote_wins). Clearing local cache.");
        local_store
            .replace_all(&[])
            .map_err(|e| format!("Failed to clear database: {}", e))?;
        return Ok(Vec::new());
    }

    if strategy == "local_wins" {
        debug_logs.push_str("\nFavorites sync strategy local_wins. Keeping local favorites cache.");
        return Ok(local_posts);
    }

    if strategy == "remote_wins" {
        debug_logs.push_str(
            "\nFavorites sync strategy remote_wins. Replacing local cache with remote posts.",
        );
        local_store
            .replace_all(&effective_remote_posts)
            .map_err(|e| format!("Failed to update database: {}", e))?;
        return Ok(local_store
            .list_favorites(None, None)
            .unwrap_or(effective_remote_posts));
    }

    // Merge strategy
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
}
