import React from "react";
import { Heart, Download, Play } from "lucide-react";
import "./PostCard.css";

export function isMediaVideo(url) {
  if (!url || typeof url !== "string") return false;
  const cleanUrl = url.split("?")[0].split("#")[0].toLowerCase();
  return cleanUrl.endsWith(".mp4") || cleanUrl.endsWith(".webm");
}

export function Thumbnail({ post }) {
  const url = post.preview_url || post.sample_url || post.file_url;
  const isVideo = isMediaVideo(url);

  if (isVideo) {
    return (
      <video
        src={url}
        className="card-thumbnail"
        loop
        muted
        playsInline
      />
    );
  }

  return (
    <img
      src={url || undefined}
      alt="media preview"
      className="card-thumbnail"
      loading="lazy"
      draggable={false}
    />
  );
}

export const PostCard = React.memo(function PostCard({
  post,
  isFavorite,
  onCardClick,
  onFavoriteToggle,
  onDownload,
  showPublicBadge = false,
  showIdAsScore = false,
  isSelected = false,
  onSelectToggle,
}) {
  const isVideo = isMediaVideo(post.file_url) || isMediaVideo(post.preview_url) || isMediaVideo(post.sample_url);

  return (
    <div
      className={`post-card ${isSelected ? "selected" : ""}`}
      onClick={() => onCardClick(post)}
    >
      <div className="card-thumbnail-container">
        {onSelectToggle && (
          <div className="card-select-checkbox" onClick={(e) => { e.stopPropagation(); onSelectToggle(post.id); }}>
            <input
              type="checkbox"
              checked={isSelected}
              onChange={() => {}} // Controlled component
            />
          </div>
        )}
        
        <Thumbnail post={post} />
        {isVideo && (
          <span className="video-badge">
            <Play size={10} fill="white" /> VIDEO
          </span>
        )}
        <span className="rating-badge">
          {showPublicBadge ? "Public" : post.rating}
        </span>
      </div>
      <div className="card-info">
        <span className="card-score">
          {showIdAsScore ? `ID: ${post.id}` : `Score: ${post.score || 0}`}
        </span>
        <div className="card-actions" onClick={(e) => e.stopPropagation()}>
          <button
            className={`icon-btn favorite ${isFavorite ? "active" : ""}`}
            onClick={() => onFavoriteToggle(post)}
          >
            <Heart size={16} fill={isFavorite ? "currentColor" : "none"} />
          </button>
          {onDownload && (
            <button className="icon-btn" onClick={() => onDownload(post)}>
              <Download size={16} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
});
