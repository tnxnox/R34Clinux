import React, { useState } from "react";
import { RefreshCw, Trash2, Plus } from "lucide-react";

export function SettingsTab({
  settings,
  setSettings,
  syncStatus,
  saveSettings,
  
  // Phase 2 Tag Blacklist Props (optional)
  blacklistedTags = [],
  onAddBlacklistTag,
  onRemoveBlacklistTag,
}) {
  const [newBlacklistTag, setNewBlacklistTag] = useState("");

  const handleAddTag = (e) => {
    e.preventDefault();
    if (newBlacklistTag.trim() && onAddBlacklistTag) {
      onAddBlacklistTag(newBlacklistTag.trim());
      setNewBlacklistTag("");
    }
  };

  return (
    <div style={{ maxWidth: "600px" }}>
      {/* Rule34 API Credentials */}
      <div
        className="cred-card"
        style={{ width: "100%", textAlign: "left", marginBottom: "30px" }}
      >
        <h3 style={{ fontSize: "16px", marginBottom: "20px" }}>
          Rule34 API Credentials
        </h3>
        <div className="form-group">
          <label>User ID</label>
          <input
            type="text"
            className="form-input"
            value={settings.user_id}
            onChange={(e) =>
              setSettings((p) => ({ ...p, user_id: e.target.value }))
            }
          />
        </div>
        <div className="form-group">
          <label>API Key</label>
          <input
            type="password"
            className="form-input"
            value={settings.api_key}
            onChange={(e) =>
              setSettings((p) => ({ ...p, api_key: e.target.value }))
            }
          />
        </div>
      </div>

      {/* Rule34 Website Login */}
      <div
        className="cred-card"
        style={{ width: "100%", textAlign: "left", marginBottom: "30px" }}
      >
        <h3 style={{ fontSize: "16px", marginBottom: "20px" }}>
          Rule34 Website Login (for Sync)
        </h3>
        <div className="form-group">
          <label>Username</label>
          <input
            type="text"
            className="form-input"
            value={settings.website_username}
            onChange={(e) =>
              setSettings((p) => ({ ...p, website_username: e.target.value }))
            }
          />
        </div>
        <div className="form-group">
          <label>Password</label>
          <input
            type="password"
            className="form-input"
            value={settings.website_password}
            onChange={(e) =>
              setSettings((p) => ({ ...p, website_password: e.target.value }))
            }
          />
        </div>
      </div>

      {/* Tag Blacklist Section (Phase 2 preview/setup) */}
      {onAddBlacklistTag && (
        <div
          className="cred-card"
          style={{ width: "100%", textAlign: "left", marginBottom: "30px" }}
        >
          <h3 style={{ fontSize: "16px", marginBottom: "20px" }}>
            Tag Blacklist
          </h3>
          <form
            onSubmit={handleAddTag}
            style={{ display: "flex", gap: "12px", marginBottom: "16px" }}
          >
            <input
              type="text"
              className="form-input"
              placeholder="e.g. gore, scat..."
              value={newBlacklistTag}
              onChange={(e) => setNewBlacklistTag(e.target.value)}
            />
            <button type="submit" className="btn-primary" style={{ width: "80px", padding: "10px" }}>
              Add
            </button>
          </form>

          {blacklistedTags.length > 0 ? (
            <div className="tags-container" style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
              {blacklistedTags.map((tag) => (
                <span
                  key={tag}
                  className="tag-badge"
                  style={{ display: "flex", alignItems: "center", gap: "6px", cursor: "default" }}
                >
                  {tag}
                  <Trash2
                    size={12}
                    style={{ cursor: "pointer", color: "var(--text-muted)" }}
                    onClick={() => onRemoveBlacklistTag && onRemoveBlacklistTag(tag)}
                  />
                </span>
              ))}
            </div>
          ) : (
            <p style={{ fontSize: "13px", color: "var(--text-muted)" }}>
              No tags blacklisted yet.
            </p>
          )}
        </div>
      )}

      {/* Download Preferences */}
      <div
        className="cred-card"
        style={{ width: "100%", textAlign: "left", marginBottom: "30px" }}
      >
        <h3 style={{ fontSize: "16px", marginBottom: "20px" }}>
          Download Preferences
        </h3>
        <div className="form-group">
          <label>Download Directory</label>
          <input
            type="text"
            className="form-input"
            value={settings.download_directory}
            onChange={(e) =>
              setSettings((p) => ({ ...p, download_directory: e.target.value }))
            }
          />
        </div>
        <div className="form-group">
          <label>Naming Template (e.g. &#123;id&#125; or &#123;md5&#125;)</label>
          <input
            type="text"
            className="form-input"
            value={settings.download_naming_template}
            onChange={(e) =>
              setSettings((p) => ({
                ...p,
                download_naming_template: e.target.value,
              }))
            }
          />
        </div>
        <div style={{ display: "flex", gap: "20px", marginTop: "16px" }}>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              cursor: "pointer",
              fontSize: "13px",
            }}
          >
            <input
              type="checkbox"
              checked={settings.download_sidecar_enabled}
              onChange={(e) =>
                setSettings((p) => ({
                  ...p,
                  download_sidecar_enabled: e.target.checked,
                }))
              }
            />
            Save JSON/TXT tags sidecar
          </label>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              cursor: "pointer",
              fontSize: "13px",
            }}
          >
            <input
              type="checkbox"
              checked={settings.download_use_sample}
              onChange={(e) =>
                setSettings((p) => ({
                  ...p,
                  download_use_sample: e.target.checked,
                }))
              }
            />
            Use compressed sample files
          </label>
        </div>
      </div>

      {/* Sync Conflict Strategy */}
      <div
        className="cred-card"
        style={{ width: "100%", textAlign: "left", marginBottom: "30px" }}
      >
        <h3 style={{ fontSize: "16px", marginBottom: "20px" }}>
          Sync Conflict Strategy
        </h3>
        <div className="form-group">
          <label htmlFor="sync-conflict-strategy">Conflict Resolution Strategy</label>
          <select
            id="sync-conflict-strategy"
            className="form-input"
            style={{ background: "rgba(0, 0, 0, 0.25)", color: "white" }}
            value={settings.sync_conflict_strategy || "remote_wins"}
            onChange={(e) =>
              setSettings((p) => ({ ...p, sync_conflict_strategy: e.target.value }))
            }
          >
            <option value="remote_wins" style={{ background: "#1f2937" }}>Remote Wins (Propagate remote deletions to local)</option>
            <option value="merge" style={{ background: "#1f2937" }}>Merge (Keep local favorites and remote favorites)</option>
            <option value="local_wins" style={{ background: "#1f2937" }}>Local Wins (Keep local favorites, do not import remote changes)</option>
          </select>
          <p style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "8px", lineHeight: "1.4" }}>
            Controls what happens when local favorites differ from remote website favorites.
            Switch to <strong>Remote Wins</strong> if you want deletions made on the remote website to be reflected on your local list when syncing.
          </p>
        </div>
      </div>

      {/* FlareSolverr Proxy */}
      <div
        className="cred-card"
        style={{ width: "100%", textAlign: "left", marginBottom: "30px" }}
      >
        <h3 style={{ fontSize: "16px", marginBottom: "20px" }}>
          FlareSolverr (Cloudflare Bypass)
        </h3>
        <div style={{ marginBottom: "16px" }}>
          <label
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              cursor: "pointer",
              fontSize: "13px",
            }}
          >
            <input
              type="checkbox"
              checked={settings.flaresolverr_enabled}
              onChange={(e) =>
                setSettings((p) => ({
                  ...p,
                  flaresolverr_enabled: e.target.checked,
                }))
              }
            />
            Enable FlareSolverr Proxy
          </label>
        </div>
        <div className="form-group">
          <label>FlareSolverr URL</label>
          <input
            type="text"
            className="form-input"
            value={settings.flaresolverr_url}
            onChange={(e) =>
              setSettings((p) => ({ ...p, flaresolverr_url: e.target.value }))
            }
          />
        </div>
      </div>

      {/* Sync Status Log */}
      <div
        className="cred-card"
        style={{
          width: "100%",
          textAlign: "left",
          marginBottom: "30px",
          background: "rgba(15,17,32,0.6)",
        }}
      >
        <h3
          style={{
            fontSize: "16px",
            marginBottom: "12px",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <RefreshCw size={16} /> Favorites Sync Logs
        </h3>
        {syncStatus.debug || syncStatus.error ? (
          <div
            style={{
              background: "rgba(0,0,0,0.3)",
              padding: "12px",
              borderRadius: "8px",
              maxHeight: "200px",
              overflowY: "auto",
              fontFamily: "monospace",
              fontSize: "12px",
            }}
          >
            {syncStatus.error && (
              <div
                style={{ color: "#f87171", marginBottom: "8px", fontWeight: "bold" }}
              >
                Error: {syncStatus.error}
              </div>
            )}
            {syncStatus.debug.split("\n").map((line, idx) => (
              <div
                key={idx}
                style={{
                  color:
                    line.includes("[Outcome]") || line.includes("completed")
                      ? "#34d399"
                      : "var(--text-secondary)",
                }}
              >
                {line}
              </div>
            ))}
          </div>
        ) : (
          <p style={{ fontSize: "13px", color: "var(--text-muted)" }}>
            No sync operation has run in this session yet.
          </p>
        )}
      </div>

      <button className="btn-primary" onClick={() => saveSettings(settings)}>
        Save All Settings
      </button>
    </div>
  );
}
