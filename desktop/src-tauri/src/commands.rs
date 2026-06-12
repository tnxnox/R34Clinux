#![allow(non_snake_case)]

use crate::api::Rule34Client;
use crate::db::LocalFavoritesStore;
use crate::downloader::DownloadManager;
use crate::models::{Friend, Post, SerializedPost, SyncStatus, TagSuggestion};
use crate::scraper::fetch_friend_favorites;
use crate::settings::{AppSettings, SettingsStore};
use crate::sync::sync_remote_favorites;

use serde::Deserialize;
use serde_json::Value;
use std::sync::{Arc, Mutex as StdMutex};
use tokio::sync::Mutex as TokioMutex;

pub struct AppStateInner {
    pub db: LocalFavoritesStore,
    pub settings: SettingsStore,
    pub downloader: DownloadManager,
    pub sync_lock: TokioMutex<()>,
    pub sync_status: StdMutex<SyncStatus>,
    pub mutation_notify: tokio::sync::Notify,
    pub mutation_progress: StdMutex<crate::models::MutationProgress>,
    pub mutation_streaks: StdMutex<std::collections::HashMap<String, i32>>,
}

#[derive(Clone)]
pub struct AppState(pub Arc<AppStateInner>);

#[derive(Deserialize)]
pub struct SettingsUpdatePayload {
    pub user_id: String,
    pub api_key: String,
    pub website_username: Option<String>,
    pub website_password: Option<String>,
    pub download_directory: Option<String>,
    pub page_size: Option<i32>,
    pub flaresolverr_enabled: Option<bool>,
    pub flaresolverr_url: Option<String>,
    pub sync_conflict_strategy: Option<String>,
    pub background_sync_interval_minutes: Option<i32>,
    pub download_naming_template: Option<String>,
    pub download_path_template: Option<String>,
    pub download_use_sample: Option<bool>,
    pub download_sidecar_enabled: Option<bool>,
    pub download_sidecar_format: Option<String>,
    pub download_max_retries: Option<i32>,
}

#[tauri::command]
pub fn get_settings(state: tauri::State<'_, AppState>) -> Value {
    let s = state.0.settings.load();
    let dl_dir = if s.download_directory.is_empty() {
        SettingsStore::default_download_directory()
    } else {
        s.download_directory.clone()
    };
    serde_json::json!({
        "user_id": s.user_id,
        "api_key": s.api_key,
        "website_username": s.website_username,
        "website_password": s.website_password,
        "download_directory": dl_dir,
        "page_size": s.page_size,
        "flaresolverr_enabled": s.flaresolverr_enabled,
        "flaresolverr_url": s.flaresolverr_url,
        "sync_conflict_strategy": s.sync_conflict_strategy,
        "background_sync_interval_minutes": s.background_sync_interval_minutes,
        "download_naming_template": s.download_naming_template,
        "download_path_template": s.download_path_template,
        "download_use_sample": s.download_use_sample,
        "download_sidecar_enabled": s.download_sidecar_enabled,
        "download_sidecar_format": s.download_sidecar_format,
        "download_max_retries": s.download_max_retries,
        "has_credentials": s.has_credentials(),
    })
}

#[tauri::command]
pub fn update_settings(
    state: tauri::State<'_, AppState>,
    payload: SettingsUpdatePayload,
) -> Result<Value, String> {
    let current = state.0.settings.load();
    let updated = AppSettings {
        user_id: payload.user_id,
        api_key: payload.api_key,
        website_username: payload.website_username.unwrap_or(current.website_username),
        website_password: payload.website_password.unwrap_or(current.website_password),
        download_directory: payload
            .download_directory
            .unwrap_or(current.download_directory),
        page_size: payload.page_size.unwrap_or(current.page_size),
        flaresolverr_enabled: payload
            .flaresolverr_enabled
            .unwrap_or(current.flaresolverr_enabled),
        flaresolverr_url: payload.flaresolverr_url.unwrap_or(current.flaresolverr_url),
        sync_conflict_strategy: payload
            .sync_conflict_strategy
            .unwrap_or(current.sync_conflict_strategy),
        background_sync_interval_minutes: payload
            .background_sync_interval_minutes
            .unwrap_or(current.background_sync_interval_minutes),
        download_naming_template: payload
            .download_naming_template
            .unwrap_or(current.download_naming_template),
        download_path_template: payload
            .download_path_template
            .unwrap_or(current.download_path_template),
        download_use_sample: payload
            .download_use_sample
            .unwrap_or(current.download_use_sample),
        download_sidecar_enabled: payload
            .download_sidecar_enabled
            .unwrap_or(current.download_sidecar_enabled),
        download_sidecar_format: payload
            .download_sidecar_format
            .unwrap_or(current.download_sidecar_format),
        download_max_retries: payload
            .download_max_retries
            .unwrap_or(current.download_max_retries),
    };
    state.0.settings.save(&updated);
    Ok(serde_json::json!({ "status": "ok" }))
}

#[tauri::command]
pub async fn search_posts(
    state: tauri::State<'_, AppState>,
    tags: String,
    page: i32,
    limit: i32,
) -> Result<Vec<SerializedPost>, String> {
    let s = state.0.settings.load();
    if !s.has_credentials() {
        return Err("API credentials are not configured.".to_string());
    }
    let client = Rule34Client::new(s.user_id, s.api_key);
    let posts = client.search_posts(&tags, page, limit).await?;
    Ok(posts.into_iter().map(SerializedPost::from).collect())
}

#[tauri::command]
pub async fn autocomplete_tags(
    state: tauri::State<'_, AppState>,
    prefix: String,
) -> Result<Vec<TagSuggestion>, String> {
    let s = state.0.settings.load();
    if !s.has_credentials() {
        return Err("API credentials are not configured.".to_string());
    }
    let client = Rule34Client::new(s.user_id, s.api_key);
    client.autocomplete_tags(&prefix).await
}

#[tauri::command]
pub fn list_favorites(
    state: tauri::State<'_, AppState>,
    limit: Option<u32>,
    collection: Option<String>,
) -> Result<Vec<SerializedPost>, String> {
    let posts = state
        .0
        .db
        .list_favorites(limit, collection.as_deref())
        .map_err(|e| e.to_string())?;
    Ok(posts.into_iter().map(SerializedPost::from).collect())
}

#[tauri::command]
pub fn add_favorite(state: tauri::State<'_, AppState>, post: Post) -> Result<Value, String> {
    state.0.db.add_favorite(&post).map_err(|e| e.to_string())?;

    let settings = state.0.settings.load();
    if settings.has_credentials()
        && !settings.website_username.is_empty()
        && !settings.website_password.is_empty()
    {
        let mut prog = state.0.mutation_progress.lock().unwrap();
        let old_pending = prog.current_pending;

        crate::mutations::queue_pending_add(post.id, "user request")?;

        let new_pending = if let Ok(pending_file) = crate::mutations::load_pending_mutations() {
            pending_file.add.len() + pending_file.remove.len()
        } else {
            old_pending + 1
        };

        if new_pending == 0 {
            prog.total_mutations = 0;
            prog.completed_mutations = 0;
        } else if old_pending == 0 {
            prog.total_mutations = new_pending;
            prog.completed_mutations = 0;
        } else if new_pending > old_pending {
            prog.total_mutations += new_pending - old_pending;
        }
        prog.current_pending = new_pending;

        state.0.mutation_notify.notify_one();
    }

    Ok(serde_json::json!({ "status": "ok" }))
}

#[tauri::command]
pub fn remove_favorite(state: tauri::State<'_, AppState>, postId: i64) -> Result<Value, String> {
    state
        .0
        .db
        .remove_favorite(postId)
        .map_err(|e| e.to_string())?;

    let settings = state.0.settings.load();
    if settings.has_credentials()
        && !settings.website_username.is_empty()
        && !settings.website_password.is_empty()
    {
        let mut prog = state.0.mutation_progress.lock().unwrap();
        let old_pending = prog.current_pending;

        crate::mutations::queue_pending_remove(postId, "user request")?;

        let new_pending = if let Ok(pending_file) = crate::mutations::load_pending_mutations() {
            pending_file.add.len() + pending_file.remove.len()
        } else {
            old_pending + 1
        };

        if new_pending == 0 {
            prog.total_mutations = 0;
            prog.completed_mutations = 0;
        } else if old_pending == 0 {
            prog.total_mutations = new_pending;
            prog.completed_mutations = 0;
        } else if new_pending > old_pending {
            prog.total_mutations += new_pending - old_pending;
        }
        prog.current_pending = new_pending;

        state.0.mutation_notify.notify_one();
    }

    Ok(serde_json::json!({ "status": "ok" }))
}

#[tauri::command]
pub fn get_mutation_progress(state: tauri::State<'_, AppState>) -> crate::models::MutationProgress {
    let progress = state.0.mutation_progress.lock().unwrap();
    progress.clone()
}

#[tauri::command]
pub fn list_collections(state: tauri::State<'_, AppState>) -> Result<Vec<String>, String> {
    state.0.db.list_collections().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn create_collection(state: tauri::State<'_, AppState>, name: String) -> Result<Value, String> {
    let normalized = state
        .0
        .db
        .create_collection(&name)
        .map_err(|e| e.to_string())?;
    Ok(serde_json::json!({ "status": "ok", "name": normalized }))
}

#[tauri::command]
pub fn delete_collection(state: tauri::State<'_, AppState>, name: String) -> Result<Value, String> {
    state
        .0
        .db
        .delete_collection(&name)
        .map_err(|e| e.to_string())?;
    Ok(serde_json::json!({ "status": "ok" }))
}

#[tauri::command]
pub fn assign_posts_to_collection(
    state: tauri::State<'_, AppState>,
    name: String,
    postIds: Vec<i64>,
) -> Result<Value, String> {
    let count = state
        .0
        .db
        .assign_posts_to_collection(&postIds, &name)
        .map_err(|e| e.to_string())?;
    Ok(serde_json::json!({ "status": "ok", "assigned": count }))
}

#[tauri::command]
pub fn remove_posts_from_collection(
    state: tauri::State<'_, AppState>,
    name: String,
    postIds: Vec<i64>,
) -> Result<Value, String> {
    let count = state
        .0
        .db
        .remove_posts_from_collection(&postIds, &name)
        .map_err(|e| e.to_string())?;
    Ok(serde_json::json!({ "status": "ok", "removed": count }))
}

#[tauri::command]
pub fn list_friends(state: tauri::State<'_, AppState>) -> Result<Vec<Friend>, String> {
    state.0.db.list_friends().map_err(|e| e.to_string())
}

#[tauri::command]
pub fn add_friend(
    state: tauri::State<'_, AppState>,
    userId: String,
    displayName: String,
    notes: Option<String>,
) -> Result<Value, String> {
    state
        .0
        .db
        .add_friend(&userId, &displayName, &notes.unwrap_or_default())
        .map_err(|e| e.to_string())?;
    Ok(serde_json::json!({ "status": "ok" }))
}

#[tauri::command]
pub fn remove_friend(state: tauri::State<'_, AppState>, userId: String) -> Result<Value, String> {
    state
        .0
        .db
        .remove_friend(&userId)
        .map_err(|e| e.to_string())?;
    Ok(serde_json::json!({ "status": "ok" }))
}

#[tauri::command]
pub async fn download_post(state: tauri::State<'_, AppState>, post: Post) -> Result<Value, String> {
    let settings = state.0.settings.load();
    let dest = state.0.downloader.download_post(&post, &settings).await?;
    match dest {
        Some(path) => {
            Ok(serde_json::json!({ "status": "downloaded", "path": path.to_string_lossy() }))
        }
        None => Ok(serde_json::json!({ "status": "already_downloaded" })),
    }
}

#[tauri::command]
pub fn get_sync_status(state: tauri::State<'_, AppState>) -> SyncStatus {
    let status = state.0.sync_status.lock().unwrap();
    status.clone()
}

#[tauri::command]
pub fn start_sync(state: tauri::State<'_, AppState>) -> Value {
    let state_inner = state.0.clone();

    // Check if already running
    {
        let mut status = state_inner.sync_status.lock().unwrap();
        if status.is_running {
            return serde_json::json!({ "status": "already_running" });
        }
        status.is_running = true;
        status.debug = "Sync started.".to_string();
        status.error = "".to_string();
        status.success = false;
    }

    tauri::async_runtime::spawn(async move {
        let settings = state_inner.settings.load();
        let mut debug_logs = "Sync started.".to_string();
        let mut error_logs = "".to_string();

        let lock_guard = state_inner.sync_lock.try_lock();
        if lock_guard.is_err() {
            let mut status = state_inner.sync_status.lock().unwrap();
            status.is_running = false;
            status.error =
                "Sync skipped: Another sync operation is already in progress.".to_string();
            return;
        }

        let res = sync_remote_favorites(
            &settings,
            &state_inner.db,
            &mut debug_logs,
            &mut error_logs,
            Some(&state_inner.mutation_progress),
        )
        .await;

        let mut status = state_inner.sync_status.lock().unwrap();
        status.is_running = false;
        status.debug = debug_logs;
        status.error = error_logs;
        match res {
            Ok(_) => {
                status.success = true;
            }
            Err(e) => {
                status.success = false;
                status
                    .error
                    .push_str(&format!("\nUnexpected sync error: {}", e));
            }
        }
    });

    serde_json::json!({ "status": "started" })
}

#[tauri::command]
pub async fn get_friend_favorites(
    state: tauri::State<'_, AppState>,
    userId: String,
    page: i32,
) -> Result<Vec<SerializedPost>, String> {
    let settings = state.0.settings.load();
    let flare_solver_url = if settings.flaresolverr_enabled {
        &settings.flaresolverr_url
    } else {
        ""
    };
    let posts = fetch_friend_favorites(&userId, flare_solver_url, page).await?;
    Ok(posts.into_iter().map(SerializedPost::from).collect())
}
