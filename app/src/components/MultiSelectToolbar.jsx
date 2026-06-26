import React, { useState } from "react";
import { Heart, Download, X } from "lucide-react";
import "./MultiSelectToolbar.css";

export function MultiSelectToolbar({
  selectedPosts,
  activeTab,
  collections,
  onClear,
  onBulkFavorite,
  onBulkDownload,
  onBulkAssignCollection,
}) {
  const [targetCollection, setTargetCollection] = useState("");

  if (selectedPosts.length === 0) return null;

  const count = selectedPosts.length;
  const isSearchTab = activeTab === "search";
  const isFavoritesTab = activeTab === "favorites";

  return (
    <div className="multi-select-toolbar">
      <div className="toolbar-info">
        <span className="selected-count">{count} items selected</span>
      </div>

      <div className="toolbar-actions">
        {isSearchTab && (
          <button className="btn-action fav" onClick={() => onBulkFavorite(selectedPosts, true)}>
            <Heart size={16} fill="none" />
            Favorite
          </button>
        )}
        
        {isFavoritesTab && (
          <button className="btn-action fav active" onClick={() => onBulkFavorite(selectedPosts, false)}>
            <Heart size={16} fill="currentColor" />
            Unfavorite
          </button>
        )}

        <button className="btn-action download" onClick={() => onBulkDownload(selectedPosts)}>
          <Download size={16} />
          Download
        </button>

        {collections.length > 0 && (
          <div className="toolbar-collection-assign">
            <select
              className="form-input toolbar-select"
              value={targetCollection}
              onChange={(e) => setTargetCollection(e.target.value)}
            >
              <option value="">Add to Collection...</option>
              {collections.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <button
              className="btn-primary toolbar-btn"
              disabled={!targetCollection}
              onClick={() => {
                onBulkAssignCollection(selectedPosts, targetCollection);
                setTargetCollection("");
              }}
            >
              Assign
            </button>
          </div>
        )}

        <button className="icon-btn close-btn" onClick={onClear}>
          <X size={18} />
        </button>
      </div>
    </div>
  );
}
