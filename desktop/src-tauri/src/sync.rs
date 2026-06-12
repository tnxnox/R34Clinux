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
) -> Result<Vec<Post>, String> {
    
    let solver_client = FlareSolverrFavoritesClient::new(
        settings.user_id.clone(),
        settings.api_key.clone(),
        settings.website_username.clone(),
        settings.website_password.clone(),
        settings.flaresolverr_url.clone(),
    );

    let local_posts = local_store.list_favorites(None, None)
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

    let strategy = settings.sync_conflict_strategy.trim().to_lowercase();

    if remote_posts.is_empty() {
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
        local_store.replace_all(&[])
            .map_err(|e| format!("Failed to clear database: {}", e))?;
        return Ok(Vec::new());
    }

    if strategy == "local_wins" {
        debug_logs.push_str("\nFavorites sync strategy local_wins. Keeping local favorites cache.");
        return Ok(local_posts);
    }

    if strategy == "remote_wins" {
        debug_logs.push_str("\nFavorites sync strategy remote_wins. Replacing local cache with remote posts.");
        local_store.replace_all(&remote_posts)
            .map_err(|e| format!("Failed to update database: {}", e))?;
        return Ok(local_store.list_favorites(None, None).unwrap_or(remote_posts));
    }

    // Merge strategy
    debug_logs.push_str("\nFavorites sync strategy merge. Merging local and remote favorites...");
    let mut merged = Vec::new();
    let mut remote_ids = std::collections::HashSet::new();

    for remote in &remote_posts {
        remote_ids.insert(remote.id);
        if let Some(local) = local_by_id.get(&remote.id) {
            // Merge posts
            let mut merged_post = remote.clone();
            if merged_post.tags.is_empty() { merged_post.tags = local.tags.clone(); }
            if merged_post.rating.is_empty() { merged_post.rating = local.rating.clone(); }
            if merged_post.score.is_none() { merged_post.score = local.score; }
            if merged_post.width.is_none() { merged_post.width = local.width; }
            if merged_post.height.is_none() { merged_post.height = local.height; }
            if merged_post.file_size.is_none() { merged_post.file_size = local.file_size; }
            if merged_post.source.is_empty() { merged_post.source = local.source.clone(); }
            if merged_post.md5.is_empty() { merged_post.md5 = local.md5.clone(); }
            if merged_post.preview_url.is_empty() { merged_post.preview_url = local.preview_url.clone(); }
            if merged_post.sample_url.is_empty() { merged_post.sample_url = local.sample_url.clone(); }
            if merged_post.file_url.is_empty() { merged_post.file_url = local.file_url.clone(); }
            if merged_post.created_at.is_empty() { merged_post.created_at = local.created_at.clone(); }
            
            merged.push(merged_post);
        } else {
            merged.push(remote.clone());
        }
    }

    // Add local posts not present on remote
    for local in &local_posts {
        if !remote_ids.contains(&local.id) {
            merged.push(local.clone());
        }
    }

    local_store.replace_all(&merged)
        .map_err(|e| format!("Failed to update database with merged posts: {}", e))?;

    debug_logs.push_str("\nSync completed successfully.");
    
    // Close session to cleanup container tasks
    solver_client.close().await;

    Ok(local_store.list_favorites(None, None).unwrap_or(merged))
}
