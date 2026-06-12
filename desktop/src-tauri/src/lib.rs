mod models;
mod db;
mod settings;
mod api;
mod flaresolverr;
mod scraper;
mod downloader;
mod sync;
mod commands;

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let db = db::LocalFavoritesStore::new(None);
            let settings = settings::SettingsStore::new();
            
            // We recreate a db handle for downloader just to avoid sharing issues, or use the cloned/created one
            let downloader_db = db::LocalFavoritesStore::new(None);
            let downloader = downloader::DownloadManager::new(downloader_db);
            
            let state = commands::AppState(std::sync::Arc::new(commands::AppStateInner {
                db,
                settings,
                downloader,
                sync_lock: tokio::sync::Mutex::new(()),
                sync_status: std::sync::Mutex::new(models::SyncStatus {
                    is_running: false,
                    debug: "".to_string(),
                    error: "".to_string(),
                    success: false,
                }),
            }));
            
            app.manage(state.clone());
            
            // Auto start flaresolverr container in background thread on startup
            let settings_data = state.0.settings.load();
            tokio::spawn(async move {
                flaresolverr::start_flaresolverr_container(&settings_data.flaresolverr_url).await;
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::get_settings,
            commands::update_settings,
            commands::search_posts,
            commands::autocomplete_tags,
            commands::list_favorites,
            commands::add_favorite,
            commands::remove_favorite,
            commands::list_collections,
            commands::create_collection,
            commands::delete_collection,
            commands::assign_posts_to_collection,
            commands::remove_posts_from_collection,
            commands::list_friends,
            commands::add_friend,
            commands::remove_friend,
            commands::download_post,
            commands::get_sync_status,
            commands::start_sync,
            commands::get_friend_favorites,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
