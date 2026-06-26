import React, { useState, useEffect, useRef } from "react";
import { Heart, Download, X, Maximize, Minimize, ChevronLeft, ChevronRight, Play, Pause, Volume2, VolumeX } from "lucide-react";
import { invoke, convertFileSrc } from "@tauri-apps/api/core";
import "./DetailModal.css";

const VideoPlayer = React.memo(function VideoPlayer({ src }) {
  const videoRef = useRef(null);
  const [isPlaying, setIsPlaying] = useState(true);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isMuted, setIsMuted] = useState(false);
  const [showControls, setShowControls] = useState(false);
  const controlsTimeoutRef = useRef(null);

  useEffect(() => {
    setIsPlaying(true);
    if (videoRef.current) {
      if (typeof videoRef.current.load === "function") {
        videoRef.current.load();
      }
      if (typeof videoRef.current.play === "function") {
        const playPromise = videoRef.current.play();
        if (playPromise && typeof playPromise.catch === "function") {
          playPromise.catch((err) => console.error("Auto-play error on source change:", err));
        }
      }
    }
  }, [src]);

  const handlePlayPause = (e) => {
    if (videoRef.current) {
      if (isPlaying) {
        if (typeof videoRef.current.pause === "function") {
          videoRef.current.pause();
        }
        setIsPlaying(false);
      } else {
        if (typeof videoRef.current.play === "function") {
          const playPromise = videoRef.current.play();
          if (playPromise && typeof playPromise.catch === "function") {
            playPromise.catch((err) => console.error(err));
          }
        }
        setIsPlaying(true);
      }
    }
  };

  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setCurrentTime(videoRef.current.currentTime);
    }
  };

  const handleLoadedMetadata = () => {
    if (videoRef.current) {
      setDuration(videoRef.current.duration);
    }
  };

  const handleSeek = (e) => {
    e.stopPropagation();
    if (!videoRef.current || !duration) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const percentage = clickX / rect.width;
    const newTime = percentage * duration;
    videoRef.current.currentTime = newTime;
    setCurrentTime(newTime);
  };

  const toggleMute = (e) => {
    e.stopPropagation();
    if (videoRef.current) {
      const nextMute = !isMuted;
      videoRef.current.muted = nextMute;
      setIsMuted(nextMute);
    }
  };

  const formatTime = (seconds) => {
    if (isNaN(seconds)) return "00:00";
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  const handleMouseMove = () => {
    setShowControls(true);
    if (controlsTimeoutRef.current) {
      clearTimeout(controlsTimeoutRef.current);
    }
    controlsTimeoutRef.current = setTimeout(() => {
      setShowControls(false);
    }, 2000);
  };

  useEffect(() => {
    return () => {
      if (controlsTimeoutRef.current) {
        clearTimeout(controlsTimeoutRef.current);
      }
    };
  }, []);

  const progressPercent = duration ? (currentTime / duration) * 100 : 0;

  return (
    <div
      className="video-player-container"
      onMouseMove={handleMouseMove}
      onMouseLeave={() => setShowControls(false)}
      onClick={handlePlayPause}
    >
      <video
        ref={videoRef}
        src={src}
        className="modal-media"
        autoPlay
        loop
        muted={isMuted}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        playsInline
      />
      <div className={`video-controls-overlay ${showControls ? "visible" : ""}`} onClick={(e) => e.stopPropagation()}>
        <button className="video-control-btn" onClick={handlePlayPause} aria-label={isPlaying ? "Pause" : "Play"}>
          {isPlaying ? <Pause size={18} /> : <Play size={18} />}
        </button>

        <div className="video-time-display">{formatTime(currentTime)}</div>

        <div className="video-progress-bar-container" onClick={handleSeek}>
          <div className="video-progress-bar-bg">
            <div className="video-progress-bar-fill" style={{ width: `${progressPercent}%` }} />
          </div>
        </div>

        <div className="video-time-display">{formatTime(duration)}</div>

        <button className="video-control-btn" onClick={toggleMute} aria-label={isMuted ? "Unmute" : "Mute"}>
          {isMuted ? <VolumeX size={18} /> : <Volume2 size={18} />}
        </button>
      </div>
    </div>
  );
});

export const DetailModal = React.memo(function DetailModal({
  post,
  collections = [],
  favorites = [],
  onClose,
  onFavoriteToggle,
  onDownload,
  onAssignCollection,
  onTagClick,
}) {
  const [postCollectionAssign, setPostCollectionAssign] = useState("");
  const [isMetadataCollapsed, setIsMetadataCollapsed] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [localUrl, setLocalUrl] = useState(null);

  const mediaPaneRef = useRef(null);
  const imgRef = useRef(null);
  const isFullscreenPending = useRef(false);

  // Zoom & Pan state
  const [zoomScale, setZoomScale] = useState(1);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  const remoteUrl = post?.file_url || post?.sample_url || post?.preview_url;
  const url = localUrl || remoteUrl;

  // Reset zoom & pan, sidebar state, and fullscreen when post changes
  useEffect(() => {
    setZoomScale(1);
    setPanOffset({ x: 0, y: 0 });
    setIsDragging(false);
    setIsMetadataCollapsed(false);
    setLocalUrl(null);
    if (document.fullscreenElement && document.fullscreenElement === mediaPaneRef.current) {
      if (typeof document.exitFullscreen === "function") {
        document.exitFullscreen().catch((err) => console.error("Exit fullscreen error on post change:", err));
      }
    }
  }, [post?.id]);

  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(document.fullscreenElement === mediaPaneRef.current);
    };

    document.addEventListener("fullscreenchange", handleFullscreenChange);

    const currentMediaPane = mediaPaneRef.current;

    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
      // Clean up fullscreen state if modal unmounts while in fullscreen
      if (document.fullscreenElement && document.fullscreenElement === currentMediaPane) {
        if (typeof document.exitFullscreen === "function") {
          document.exitFullscreen().catch((err) => console.error("Exit fullscreen error on unmount:", err));
        }
      }
    };
  }, []);

  // Handle Escape key to close the modal
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        if (!document.fullscreenElement) {
          onClose();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  // ponytail: native non-passive wheel listener avoids browser warnings when preventing zoom
  useEffect(() => {
    const currentImg = imgRef.current;
    if (!currentImg) return;

    const handleNativeWheel = (e) => {
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

    currentImg.addEventListener("wheel", handleNativeWheel, { passive: false });

    return () => {
      if (currentImg) {
        currentImg.removeEventListener("wheel", handleNativeWheel);
      }
    };
  }, [url]);

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

  useEffect(() => {
    let active = true;
    const checkLocalFile = async () => {
      if (!post?.id) return;
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
  }, [post?.id, post?.md5]);

  if (!post) return null;

  const isFav = favorites.some((f) => f.id === post.id);
  const isVideo = remoteUrl?.endsWith(".mp4") || remoteUrl?.endsWith(".webm");

  const toggleFullscreen = async () => {
    if (!url || isFullscreenPending.current) return;
    try {
      isFullscreenPending.current = true;
      if (!document.fullscreenElement) {
        if (mediaPaneRef.current) {
          await mediaPaneRef.current.requestFullscreen();
        }
      } else {
        if (typeof document.exitFullscreen === "function") {
          await document.exitFullscreen();
        }
      }
    } catch (err) {
      console.error("Fullscreen toggle error:", err);
    } finally {
      isFullscreenPending.current = false;
    }
  };

  const renderModalMedia = () => {
    if (isVideo) {
      return <VideoPlayer src={url} />;
    }

    return (
      <img
        ref={imgRef}
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
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
        onDoubleClick={handleDoubleClick}
      />
    );
  };

  const mediaPaneClasses = `modal-media-pane${isFullscreen ? " is-fullscreen" : ""}${isMetadataCollapsed ? " expanded-full" : ""}`;
  const infoPaneClasses = `modal-info-pane${isMetadataCollapsed ? " collapsed" : ""}`;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content modal-large" onClick={(e) => e.stopPropagation()}>
        <div className={mediaPaneClasses} ref={mediaPaneRef}>
          {renderModalMedia()}
          <button
            data-testid="fullscreen-btn"
            className="fullscreen-btn"
            onClick={toggleFullscreen}
            disabled={!url}
            aria-label="Toggle Fullscreen"
          >
            {isFullscreen ? <Minimize size={18} /> : <Maximize size={18} />}
          </button>
        </div>

        <div className={infoPaneClasses}>
          <button
            data-testid="sidebar-toggle-btn"
            className="sidebar-toggle-btn"
            onClick={() => setIsMetadataCollapsed(!isMetadataCollapsed)}
            aria-label="Toggle Side Panel"
          >
            {isMetadataCollapsed ? <ChevronLeft size={16} /> : <ChevronRight size={16} />}
          </button>

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
