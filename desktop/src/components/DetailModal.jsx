import React, { useState, useEffect } from "react";
import { Heart, Download, X } from "lucide-react";
import { invoke, convertFileSrc } from "@tauri-apps/api/core";
import "./DetailModal.css";

const VideoPlayer = React.memo(function VideoPlayer({ src }) {
  return (
    <video
      src={src}
      className="modal-media"
      controls
      autoPlay
      loop
    />
  );
});

export const DetailModal = React.memo(function DetailModal({
  post,
  collections,
  favorites,
  onClose,
  onFavoriteToggle,
  onDownload,
  onAssignCollection,
  onTagClick,
}) {
  const [postCollectionAssign, setPostCollectionAssign] = useState("");

  // Zoom & Pan state
  const [zoomScale, setZoomScale] = useState(1);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  // Reset zoom & pan when post changes
  useEffect(() => {
    setZoomScale(1);
    setPanOffset({ x: 0, y: 0 });
    setIsDragging(false);
  }, [post?.id]);

  const handleWheel = (e) => {
    if (e.ctrlKey) {
      e.preventDefault();
      const delta = e.deltaY < 0 ? 0.25 : -0.25;
      setZoomScale((prev) => {
        const next = Math.min(Math.max(prev + delta, 1), 8);
        if (next === 1) {
          setPanOffset({ x: 0, y: 0 });
        }
        return next;
      });
    }
  };

  const handleMouseDown = (e) => {
    if (zoomScale > 1 && e.button === 0) {
      e.preventDefault();
      setIsDragging(true);
      setDragStart({ x: e.clientX - panOffset.x, y: e.clientY - panOffset.y });
    }
  };

  const handleMouseMove = (e) => {
    if (isDragging && zoomScale > 1) {
      e.preventDefault();
      setPanOffset({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y,
      });
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  const handleMouseLeave = () => {
    setIsDragging(false);
  };

  const handleDoubleClick = () => {
    setZoomScale(1);
    setPanOffset({ x: 0, y: 0 });
  };

  const [localUrl, setLocalUrl] = useState(null);

  useEffect(() => {
    let active = true;
    const checkLocalFile = async () => {
      if (!post.id) return;
      try {
        const path = await invoke("get_downloaded_path", { postId: post.id, md5: post.md5 || "" });
        if (path && active) {
          const assetUrl = convertFileSrc(path);
          setLocalUrl(assetUrl);
        } else if (active) {
          setLocalUrl(prev => prev !== null ? null : prev);
        }
      } catch (err) {
        console.error("Failed to check local download path:", err);
      }
    };
    checkLocalFile();
    return () => {
      active = false;
    };
  }, [post.id, post.md5]);

  const isFav = favorites.some((f) => f.id === post.id);
  const remoteUrl = post.file_url || post.sample_url || post.preview_url;
  const url = localUrl || remoteUrl;
  const isVideo = remoteUrl?.endsWith(".mp4") || remoteUrl?.endsWith(".webm");

  const renderModalMedia = () => {
    if (isVideo) {
      return <VideoPlayer src={url} />;
    }

    return (
      <img
        src={url}
        alt="modal media"
        className="modal-media"
        draggable={false}
        style={{
          transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${zoomScale})`,
          cursor: zoomScale > 1 ? (isDragging ? "grabbing" : "grab") : "default",
          transition: isDragging ? "none" : "transform 0.1s ease-out",
          transformOrigin: "center center",
        }}
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
        onDoubleClick={handleDoubleClick}
      />
    );
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-media-pane">{renderModalMedia()}</div>

        <div className="modal-info-pane">
          <div className="modal-info-header">
            <span className="modal-title">Post #{post.id}</span>
            <button className="icon-btn" onClick={onClose}>
              <X size={20} />
            </button>
          </div>

          <div className="modal-body-scroll">
            {/* Stats */}
            <div className="info-section">
              <h3>Metadata</h3>
              <div className="metadata-grid">
                <div className="metadata-item">
                  <div className="metadata-label">Score</div>
                  <div style={{ fontWeight: "600" }}>{post.score || 0}</div>
                </div>
                <div className="metadata-item">
                  <div className="metadata-label">Rating</div>
                  <div style={{ fontWeight: "600", textTransform: "capitalize" }}>
                    {post.rating}
                  </div>
                </div>
                <div className="metadata-item">
                  <div className="metadata-label">Dimensions</div>
                  <div style={{ fontWeight: "600" }}>{post.dimensions || "Unknown"}</div>
                </div>
                <div className="metadata-item">
                  <div className="metadata-label">Date</div>
                  <div style={{ fontWeight: "600" }}>
                    {post.created_at
                      ? new Date(parseInt(post.created_at) * 1000).toLocaleDateString()
                      : "Unknown"}
                  </div>
                </div>
              </div>
            </div>

            {/* Collections assignments */}
            {collections.length > 0 && (
              <div className="info-section">
                <h3>Assign to Collection</h3>
                <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
                  <select
                    className="form-input"
                    value={postCollectionAssign}
                    onChange={(e) => setPostCollectionAssign(e.target.value)}
                  >
                    <option value="">Select collection...</option>
                    {collections.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                  <button
                    className="btn-primary"
                    style={{ width: "80px", padding: "10px" }}
                    onClick={() => {
                      onAssignCollection(post, postCollectionAssign);
                      setPostCollectionAssign("");
                    }}
                  >
                    Assign
                  </button>
                </div>
              </div>
            )}

            {/* Tags */}
            {post.tags && post.tags.length > 0 ? (
              <div className="info-section">
                <h3>Associated Tags</h3>
                <div className="tags-container" style={{ marginTop: "8px" }}>
                  {post.tags.map((tag) => (
                    <span
                      key={tag}
                      className="tag-badge"
                      onClick={() => onTagClick(tag)}
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            ) : !post.file_url ? (
              <div className="info-section">
                <h3>Associated Tags</h3>
                <div style={{ fontStyle: "italic", opacity: 0.6, marginTop: "8px" }}>
                  Loading full post details...
                </div>
              </div>
            ) : null}
          </div>

          {/* Actions Footer */}
          <div className="modal-actions">
            <button
              className={`btn-action fav ${isFav ? "active" : ""}`}
              onClick={() => onFavoriteToggle(post)}
            >
              <Heart size={16} fill={isFav ? "currentColor" : "none"} />
              Favorite
            </button>
            <button className="btn-action download" onClick={() => onDownload(post)}>
              <Download size={16} />
              Download
            </button>
          </div>
        </div>
      </div>
    </div>
  );
});
