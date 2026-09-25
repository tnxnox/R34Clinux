import React from "react";
import { Heart, Download, Play } from "lucide-react";
import "./PostCard.css";

export function isMediaVideo(url) {
  if (!url || typeof url !== "string") return false;
  const cleanUrl = url.split("?")[0].split("#")[0].toLowerCase();
  return cleanUrl.endsWith(".mp4") || cleanUrl.endsWith(".webm");
}

export function isLongStrip(post) {
  if (!post) return false;
  const width = Number(post.width);
  const height = Number(post.height);
  if (!width || !height || isNaN(width) || isNaN(height)) return false;
  const ratio = height / width;
  return ratio >= 2.0 || ratio <= 0.5;
}

export function getStripType(post) {
  if (!post) return null;
  const width = Number(post.width);
  const height = Number(post.height);
  if (!width || !height || isNaN(width) || isNaN(height)) return null;
  const ratio = height / width;
  if (ratio >= 2.0) return "vertical";
  if (ratio <= 0.5) return "horizontal";
  return null;
}

export function Thumbnail({ post }) {
  const isStrip = isLongStrip(post);
  // For long strip images, rule34's preview_url thumbnail is squashed to <=150px on the longest side,
  // making a 1:10 comic strip only ~15px wide, which produces severe blur when zoomed with object-fit: cover.
  // Using sample_url (~850px width) or file_url delivers crisp high-def resolution.
  const url = isStrip
    ? (post.sample_url || post.file_url || post.preview_url)
    : (post.preview_url || post.sample_url || post.file_url);

  const isVideo = isMediaVideo(url);
  const stripType = getStripType(post);
  const stripClass = stripType === "vertical" ? " long-strip-vertical" : (stripType === "horizontal" ? " long-strip-horizontal" : "");

  if (isVideo) {
    return (
      <video
        src={url}
        className={`card-thumbnail${stripClass}`}
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
      className={`card-thumbnail${stripClass}`}
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
  const stripType = getStripType(post);
  const isStrip = Boolean(stripType);

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
        {isStrip && !isVideo && (
          <span className="strip-badge">
            {stripType === "vertical" ? "STRIP" : "PANORAMA"}
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
