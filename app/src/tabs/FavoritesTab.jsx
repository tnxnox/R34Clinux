import React from "react";
import { Heart, Loader, RefreshCw } from "lucide-react";
import { PostCard } from "../components/PostCard";

export function FavoritesTab({
  selectedCollection,
  setSelectedCollection,
  collections,
  favorites,
  syncStatus,
  triggerSync,
  toggleFavorite,
  triggerDownload,
  setSelectedPost,
  
  // Phase 3 Selection State (optional for now, defaults to empty)
  selectedPostIds = [],
  onSelectToggle,
}) {
  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "16px",
          marginBottom: "30px",
        }}
      >
        <select
          className="form-input"
          style={{ width: "250px" }}
          value={selectedCollection}
          onChange={(e) => setSelectedCollection(e.target.value)}
        >
          <option value="">All Collections</option>
          {collections.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>

        <button
          className="btn-secondary"
          style={{ width: "160px", justifyContent: "center" }}
          onClick={triggerSync}
          disabled={syncStatus.is_running}
        >
          {syncStatus.is_running ? (
            <>
              <Loader className="spinner" size={16} />
              Syncing...
            </>
          ) : (
            <>
              <RefreshCw size={16} />
              Sync Account
            </>
          )}
        </button>
      </div>

      {favorites.length > 0 ? (
        <div className="media-grid">
          {favorites.map((post) => (
            <PostCard
              key={post.id}
              post={post}
              isFavorite={true} // In favorites tab, all rendered posts are favorites
              onCardClick={setSelectedPost}
              onFavoriteToggle={toggleFavorite}
              onDownload={triggerDownload}
              isSelected={selectedPostIds.includes(post.id)}
              onSelectToggle={onSelectToggle}
            />
          ))}
        </div>
      ) : (
        <div
          style={{
            textAlign: "center",
            color: "var(--text-muted)",
            marginTop: "80px",
          }}
        >
          <Heart size={48} style={{ marginBottom: "16px" }} />
          <p>You haven't saved any favorites to your local database yet.</p>
        </div>
      )}
    </div>
  );
}
