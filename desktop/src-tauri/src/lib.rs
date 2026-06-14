#![allow(clippy::collapsible_if)]

mod api;
mod commands;
mod db;
mod downloader;
mod flaresolverr;
mod models;
mod mutations;
mod scraper;
mod settings;
mod sync;

use tauri::Emitter;
use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let db = db::LocalFavoritesStore::new(None);
            let settings = settings::SettingsStore::new();

            // We recreate a db handle for downloader just to avoid sharing issues, or use the cloned/created one
            let downloader_db = db::LocalFavoritesStore::new(None);
            let downloader = downloader::DownloadManager::new(downloader_db);

            let initial_progress = if let Ok(pending_file) = mutations::load_pending_mutations() {
                let count = mutations::count_active_mutations(&pending_file);
                models::MutationProgress {
                    total_mutations: count,
                    completed_mutations: 0,
                    current_pending: count,
                }
            } else {
                models::MutationProgress::default()
            };
            let initial_pending = initial_progress.current_pending;

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
                mutation_notify: tokio::sync::Notify::new(),
                mutation_progress: std::sync::Mutex::new(initial_progress),
                mutation_streaks: std::sync::Mutex::new(std::collections::HashMap::new()),
                has_synced_once: std::sync::atomic::AtomicBool::new(false),
            }));

            app.manage(state.clone());

            // Auto start flaresolverr container in background thread on startup
            let settings_data = state.0.settings.load();
            tauri::async_runtime::spawn(async move {
                flaresolverr::start_flaresolverr_container(&settings_data.flaresolverr_url).await;
            });

            // Background mutations retry queue runner
            let state_for_mutations = state.clone();
            tauri::async_runtime::spawn(async move {
                loop {
                    let settings = state_for_mutations.0.settings.load();
                    let run_res = if settings.has_credentials()
                        && !settings.website_username.is_empty()
                        && !settings.website_password.is_empty()
                    {
                        if !state_for_mutations
                            .0
                            .has_synced_once
                            .load(std::sync::atomic::Ordering::Relaxed)
                        {
                            // Delay processing mutations until the first sync has finished checking remote changes
                            Ok(Some(5.0))
                        } else if let Ok(_lock) = state_for_mutations.0.sync_lock.try_lock() {
                            mutations::process_pending_mutations_impl(
                                &settings,
                                &state_for_mutations.0.mutation_progress,
                                &state_for_mutations.0.mutation_streaks,
                            )
                            .await
                        } else {
                            Ok(Some(10.0))
                        }
                    } else {
                        Ok(None)
                    };

                    let sleep_secs = match run_res {
                        Ok(Some(wait_time)) => wait_time.clamp(1.0, 60.0),
                        Ok(None) => 24.0 * 3600.0,
                        Err(e) => {
                            eprintln!("Mutations queue processing error: {}", e);
                            10.0
                        }
                    };

                    let _ = tokio::time::timeout(
                        std::time::Duration::from_secs_f64(sleep_secs),
                        state_for_mutations.0.mutation_notify.notified(),
                    )
                    .await;
                }
            });

            if initial_pending > 0 {
                state.0.mutation_notify.notify_one();
            }

            // Background startup sync task
            let state_for_startup_sync = state.clone();
            tauri::async_runtime::spawn(async move {
                // Wait for FlareSolverr to start
                tokio::time::sleep(std::time::Duration::from_secs(3)).await;
                let settings = state_for_startup_sync.0.settings.load();
                if settings.has_credentials() {
                    if let Ok(_lock) = state_for_startup_sync.0.sync_lock.try_lock() {
                        {
                            let mut status = state_for_startup_sync.0.sync_status.lock().unwrap();
                            status.is_running = true;
                            status.debug = "Startup sync started.".to_string();
                            status.error = "".to_string();
                            status.success = false;
                        }

                        let mut debug_logs = "Startup sync started.".to_string();
                        let mut error_logs = "".to_string();
                        let res = sync::sync_remote_favorites(
                            &settings,
                            &state_for_startup_sync.0.db,
                            &mut debug_logs,
                            &mut error_logs,
                            Some(&state_for_startup_sync.0.mutation_progress),
                            Some(&state_for_startup_sync.0.mutation_streaks),
                            Some(&state_for_startup_sync.0.has_synced_once),
                        )
                        .await;

                        let mut status = state_for_startup_sync.0.sync_status.lock().unwrap();
                        status.is_running = false;
                        status.debug = debug_logs;
                        status.error = error_logs;
                        status.success = res.is_ok();
                    }
                }
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
            commands::get_mutation_progress,
            commands::get_post_by_id,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let tauri::RunEvent::ExitRequested { api, .. } = event {
            let state = app_handle.state::<commands::AppState>();
            let settings = state.0.settings.load();
            if settings.has_credentials() {
                // Prevent immediate exit to allow sync to complete
                api.prevent_exit();

                // Notify frontend to display the exiting/sync overlay
                let _ = app_handle.emit("app-exit-sync-start", ());

                let app_handle_clone = app_handle.clone();
                tauri::async_runtime::spawn(async move {
                    let state = app_handle_clone.state::<commands::AppState>();
                    let settings = state.0.settings.load();
                    
                    // Wait for any running sync task to finish, then run close-up sync
                    let _guard = state.0.sync_lock.lock().await;

                    let mut debug_logs = "Close up sync started.".to_string();
                    let mut error_logs = "".to_string();
                    let _ = sync::sync_remote_favorites(
                        &settings,
                        &state.0.db,
                        &mut debug_logs,
                        &mut error_logs,
                        Some(&state.0.mutation_progress),
                        Some(&state.0.mutation_streaks),
                        Some(&state.0.has_synced_once),
                    )
                    .await;

                    // Now exit the app safely
                    app_handle_clone.exit(0);
                });
            }
        }
    });
}
