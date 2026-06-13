import React from "react";
import { Folder, Plus, Trash2 } from "lucide-react";
import "./CollectionsTab.css";

export function CollectionsTab({
  newCollectionName,
  setNewCollectionName,
  createCollection,
  collections,
  deleteCollection,
}) {
  return (
    <div className="collections-panel">
      <div className="create-collection-box">
        <input
          type="text"
          className="form-input"
          placeholder="New collection name..."
          value={newCollectionName}
          onChange={(e) => setNewCollectionName(e.target.value)}
        />
        <button
          className="btn-primary"
          style={{ width: "160px" }}
          onClick={createCollection}
        >
          <Plus size={16} style={{ marginRight: "6px" }} /> Create
        </button>
      </div>

      {collections.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {collections.map((name) => (
            <div key={name} className="collection-row">
              <span style={{ fontWeight: "600" }}>{name}</span>
              <button className="icon-btn" onClick={() => deleteCollection(name)}>
                <Trash2 size={16} className="text-danger" />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div
          style={{
            textAlign: "center",
            color: "var(--text-muted)",
            marginTop: "60px",
          }}
        >
          <Folder size={48} style={{ marginBottom: "16px" }} />
          <p>No collections created. Group your local favorites into folders.</p>
        </div>
      )}
    </div>
  );
}
