import React, { useState } from "react";
import { Folder, Plus, Trash2 } from "lucide-react";
import "./CollectionsTab.css";

export function CollectionsTab({
  newCollectionName: propName,
  setNewCollectionName: propSetName,
  createCollection,
  collections = [],
  deleteCollection,
}) {
  const [internalName, setInternalName] = useState("");
  const name = propName !== undefined ? propName : internalName;
  const setName = propSetName || setInternalName;

  const handleCreate = () => {
    if (createCollection) {
      createCollection(name);
      if (!propSetName) {
        setInternalName("");
      }
    }
  };

  return (
    <div className="collections-panel">
      <div className="create-collection-box">
        <input
          type="text"
          className="form-input"
          placeholder="New collection name..."
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button
          className="btn-primary"
          style={{ width: "160px" }}
          onClick={handleCreate}
        >
          <Plus size={16} style={{ marginRight: "6px" }} /> Create
        </button>
      </div>

      {collections.length > 0 ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          {collections.map((colName) => (
            <div key={colName} className="collection-row">
              <span style={{ fontWeight: "600" }}>{colName}</span>
              <button className="icon-btn" onClick={() => deleteCollection && deleteCollection(colName)}>
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
