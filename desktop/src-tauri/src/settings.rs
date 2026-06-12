use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::env;
use std::fs;
use std::sync::Mutex;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppSettings {
    pub user_id: String,
    pub api_key: String,
    pub website_username: String,
    pub website_password: String,
    pub download_directory: String,
    pub page_size: i32,
    pub flaresolverr_enabled: bool,
    pub flaresolverr_url: String,
    pub sync_conflict_strategy: String,
    pub background_sync_interval_minutes: i32,
    pub download_naming_template: String,
    pub download_path_template: String,
    pub download_use_sample: bool,
    pub download_sidecar_enabled: bool,
    pub download_sidecar_format: String,
    pub download_max_retries: i32,
}

impl AppSettings {
    pub fn has_credentials(&self) -> bool {
        !self.user_id.trim().is_empty() && !self.api_key.trim().is_empty()
    }
}

impl Default for AppSettings {
    fn default() -> Self {
        Self {
            user_id: "".to_string(),
            api_key: "".to_string(),
            website_username: "".to_string(),
            website_password: "".to_string(),
            download_directory: "".to_string(),
            page_size: 50,
            flaresolverr_enabled: false,
            flaresolverr_url: "http://127.0.0.1:8191".to_string(),
            sync_conflict_strategy: "merge".to_string(),
            background_sync_interval_minutes: 0,
            download_naming_template: "{id}".to_string(),
            download_path_template: "".to_string(),
            download_use_sample: false,
            download_sidecar_enabled: false,
            download_sidecar_format: "json".to_string(),
            download_max_retries: 3,
        }
    }
}

#[derive(Serialize, Deserialize)]
struct RawApiSettings {
    #[serde(default)]
    user_id: String,
    #[serde(default)]
    api_key: String,
}

#[derive(Serialize, Deserialize)]
struct RawSyncSettings {
    #[serde(default)]
    website_username: String,
    #[serde(default)]
    website_password: String,
    #[serde(default)]
    flaresolverr_enabled: bool,
    #[serde(default = "default_flaresolverr_url")]
    flaresolverr_url: String,
    #[serde(default = "default_strategy")]
    conflict_strategy: String,
    #[serde(default)]
    background_interval_minutes: i32,
}

fn default_flaresolverr_url() -> String { "http://127.0.0.1:8191".to_string() }
fn default_strategy() -> String { "merge".to_string() }

#[derive(Serialize, Deserialize)]
struct RawDownloadsSettings {
    #[serde(default)]
    directory: String,
    #[serde(default = "default_naming")]
    naming_template: String,
    #[serde(default)]
    path_template: String,
    #[serde(default)]
    use_sample: bool,
    #[serde(default)]
    sidecar_enabled: bool,
    #[serde(default = "default_sidecar_format")]
    sidecar_format: String,
    #[serde(default = "default_max_retries")]
    max_retries: i32,
}

fn default_naming() -> String { "{id}".to_string() }
fn default_sidecar_format() -> String { "json".to_string() }
fn default_max_retries() -> i32 { 3 }

#[derive(Serialize, Deserialize)]
struct RawUiSettings {
    #[serde(default = "default_page_size")]
    page_size: i32,
}

fn default_page_size() -> i32 { 50 }

#[derive(Serialize, Deserialize)]
struct RawSettingsFile {
    #[serde(default)]
    api: Option<RawApiSettings>,
    #[serde(default)]
    sync: Option<RawSyncSettings>,
    #[serde(default)]
    downloads: Option<RawDownloadsSettings>,
    #[serde(default)]
    ui: Option<RawUiSettings>,
    #[serde(default)]
    search: Option<serde_json::Value>,
}

pub struct SettingsStore {
    settings_path: PathBuf,
    cached_data: Mutex<RawSettingsFile>,
}

impl SettingsStore {
    pub fn new() -> Self {
        let settings_path = Self::default_settings_path();
        let cached = Self::load_file(&settings_path);
        Self {
            settings_path,
            cached_data: Mutex::new(cached),
        }
    }

    fn default_settings_path() -> PathBuf {
        let root = if let Ok(xdg_config) = env::var("XDG_CONFIG_HOME") {
            PathBuf::from(xdg_config).join("R34LinuxClient")
        } else {
            let home = env::var("HOME").unwrap_or_else(|_| "/".to_string());
            PathBuf::from(home).join(".config").join("R34LinuxClient")
        };
        std::fs::create_dir_all(&root).ok();
        root.join("settings.json")
    }

    fn load_file(path: &PathBuf) -> RawSettingsFile {
        if path.exists() {
            if let Ok(content) = fs::read_to_string(path) {
                if let Ok(parsed) = serde_json::from_str(&content) {
                    return parsed;
                }
            }
        }
        RawSettingsFile {
            api: None,
            sync: None,
            downloads: None,
            ui: None,
            search: None,
        }
    }

    fn save_file(&self, data: &RawSettingsFile) {
        if let Ok(serialized) = serde_json::to_string_pretty(data) {
            fs::write(&self.settings_path, serialized).ok();
        }
    }

    pub fn load(&self) -> AppSettings {
        let guard = self.cached_data.lock().unwrap();
        
        let user_id = guard.api.as_ref().map(|a| a.user_id.clone()).unwrap_or_default();
        let api_key = guard.api.as_ref().map(|a| a.api_key.clone()).unwrap_or_default();
        
        let website_username = guard.sync.as_ref().map(|s| s.website_username.clone()).unwrap_or_default();
        let website_password = guard.sync.as_ref().map(|s| s.website_password.clone()).unwrap_or_default();
        let flaresolverr_enabled = guard.sync.as_ref().map(|s| s.flaresolverr_enabled).unwrap_or(false);
        let flaresolverr_url = guard.sync.as_ref().map(|s| s.flaresolverr_url.clone()).unwrap_or_else(default_flaresolverr_url);
        let sync_conflict_strategy = guard.sync.as_ref().map(|s| s.conflict_strategy.clone()).unwrap_or_else(default_strategy);
        let background_sync_interval_minutes = guard.sync.as_ref().map(|s| s.background_interval_minutes).unwrap_or(0);

        let download_directory = guard.downloads.as_ref().map(|d| d.directory.clone()).unwrap_or_else(|| {
            let home = env::var("HOME").unwrap_or_else(|_| "/".to_string());
            PathBuf::from(home).join("Downloads").to_string_lossy().to_string()
        });
        let download_naming_template = guard.downloads.as_ref().map(|d| d.naming_template.clone()).unwrap_or_else(default_naming);
        let download_path_template = guard.downloads.as_ref().map(|d| d.path_template.clone()).unwrap_or_default();
        let download_use_sample = guard.downloads.as_ref().map(|d| d.use_sample).unwrap_or(false);
        let download_sidecar_enabled = guard.downloads.as_ref().map(|d| d.sidecar_enabled).unwrap_or(false);
        let download_sidecar_format = guard.downloads.as_ref().map(|d| d.sidecar_format.clone()).unwrap_or_else(default_sidecar_format);
        let download_max_retries = guard.downloads.as_ref().map(|d| d.max_retries).unwrap_or(3);

        let page_size = guard.ui.as_ref().map(|u| u.page_size).unwrap_or(50);

        let settings = AppSettings {
            user_id,
            api_key,
            website_username,
            website_password,
            download_directory,
            page_size,
            flaresolverr_enabled,
            flaresolverr_url,
            sync_conflict_strategy,
            background_sync_interval_minutes,
            download_naming_template,
            download_path_template,
            download_use_sample,
            download_sidecar_enabled,
            download_sidecar_format,
            download_max_retries,
        };
        
        self.validate_settings(&settings)
    }

    fn validate_settings(&self, settings: &AppSettings) -> AppSettings {
        let mut validated = settings.clone();
        if validated.page_size < 1 {
            validated.page_size = 50;
        } else if validated.page_size > 1000 {
            validated.page_size = 1000;
        }
        if validated.download_max_retries < 0 {
            validated.download_max_retries = 0;
        }
        if validated.sync_conflict_strategy != "merge" && validated.sync_conflict_strategy != "local_wins" && validated.sync_conflict_strategy != "remote_wins" {
            validated.sync_conflict_strategy = "merge".to_string();
        }
        if validated.download_sidecar_format != "json" && validated.download_sidecar_format != "txt" && validated.download_sidecar_format != "both" {
            validated.download_sidecar_format = "json".to_string();
        }
        validated
    }

    pub fn save(&self, settings: &AppSettings) {
        let validated = self.validate_settings(settings);
        let mut guard = self.cached_data.lock().unwrap();
        
        guard.api = Some(RawApiSettings {
            user_id: validated.user_id,
            api_key: validated.api_key,
        });
        
        guard.sync = Some(RawSyncSettings {
            website_username: validated.website_username,
            website_password: validated.website_password,
            flaresolverr_enabled: validated.flaresolverr_enabled,
            flaresolverr_url: validated.flaresolverr_url,
            conflict_strategy: validated.sync_conflict_strategy,
            background_interval_minutes: validated.background_sync_interval_minutes,
        });

        guard.downloads = Some(RawDownloadsSettings {
            directory: validated.download_directory,
            naming_template: validated.download_naming_template,
            path_template: validated.download_path_template,
            use_sample: validated.download_use_sample,
            sidecar_enabled: validated.download_sidecar_enabled,
            sidecar_format: validated.download_sidecar_format,
            max_retries: validated.download_max_retries,
        });

        guard.ui = Some(RawUiSettings {
            page_size: validated.page_size,
        });

        self.save_file(&guard);
    }

    pub fn default_download_directory() -> String {
        let home = env::var("HOME").unwrap_or_else(|_| "/".to_string());
        PathBuf::from(home).join("Downloads").to_string_lossy().to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_has_credentials() {
        let mut settings = AppSettings::default();
        assert!(!settings.has_credentials());

        settings.user_id = "   ".to_string();
        settings.api_key = "123".to_string();
        assert!(!settings.has_credentials());

        settings.user_id = "user".to_string();
        settings.api_key = "   ".to_string();
        assert!(!settings.has_credentials());

        settings.user_id = "user".to_string();
        settings.api_key = "123".to_string();
        assert!(settings.has_credentials());
    }

    #[test]
    fn test_validate_settings() {
        let store = SettingsStore {
            settings_path: PathBuf::from("dummy_test_path"),
            cached_data: Mutex::new(RawSettingsFile {
                api: None,
                sync: None,
                downloads: None,
                ui: None,
                search: None,
            }),
        };

        // page_size validation
        let mut settings = AppSettings::default();
        settings.page_size = 0;
        let validated = store.validate_settings(&settings);
        assert_eq!(validated.page_size, 50);

        settings.page_size = 1500;
        let validated = store.validate_settings(&settings);
        assert_eq!(validated.page_size, 1000);

        settings.page_size = 200;
        let validated = store.validate_settings(&settings);
        assert_eq!(validated.page_size, 200);

        // download_max_retries validation
        settings.download_max_retries = -5;
        let validated = store.validate_settings(&settings);
        assert_eq!(validated.download_max_retries, 0);

        settings.download_max_retries = 5;
        let validated = store.validate_settings(&settings);
        assert_eq!(validated.download_max_retries, 5);

        // sync_conflict_strategy validation
        settings.sync_conflict_strategy = "invalid".to_string();
        let validated = store.validate_settings(&settings);
        assert_eq!(validated.sync_conflict_strategy, "merge");

        for valid_strategy in &["merge", "local_wins", "remote_wins"] {
            settings.sync_conflict_strategy = valid_strategy.to_string();
            let validated = store.validate_settings(&settings);
            assert_eq!(validated.sync_conflict_strategy, *valid_strategy);
        }

        // download_sidecar_format validation
        settings.download_sidecar_format = "invalid".to_string();
        let validated = store.validate_settings(&settings);
        assert_eq!(validated.download_sidecar_format, "json");

        for valid_format in &["json", "txt", "both"] {
            settings.download_sidecar_format = valid_format.to_string();
            let validated = store.validate_settings(&settings);
            assert_eq!(validated.download_sidecar_format, *valid_format);
        }
    }
}

