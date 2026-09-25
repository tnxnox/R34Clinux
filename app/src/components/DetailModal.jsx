import React, { useState, useEffect, useRef } from "react";
import { Heart, Download, X, Maximize, Minimize, ChevronLeft, ChevronRight, ChevronUp, ChevronDown, Expand, Shrink, Play, Pause, Volume2, VolumeX } from "lucide-react";
import { convertFileSrc } from "@tauri-apps/api/core";
import { api } from "../services/api";
import { getStripType } from "./PostCard";
import "./DetailModal.css";

export function isMediaVideo(url) {
  if (!url || typeof url !== "string") return false;
  const cleanUrl = url.split("?")[0].split("#")[0].toLowerCase();
  return cleanUrl.endsWith(".mp4") || cleanUrl.endsWith(".webm");
}

export function formatPostDate(createdAt) {
  if (!createdAt) return "Unknown";
  const num = Number(createdAt);
  if (!isNaN(num) && num > 0) {
    const ms = num < 100_000_000_000 ? num * 1000 : num;
    const date = new Date(ms);
    return isNaN(date.getTime()) ? "Unknown" : date.toLocaleDateString();
  }
  const date = new Date(createdAt);
  return isNaN(date.getTime()) ? "Unknown" : date.toLocaleDateString();
}

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
  const [tagTypes, setTagTypes] = useState({});

  const mediaPaneRef = useRef(null);
  const imgRef = useRef(null);
  const isFullscreenPending = useRef(false);

  const [naturalDims, setNaturalDims] = useState({ width: 0, height: 0 });

  const stripType = getStripType(post);
  const effectiveStripType = stripType || (
    naturalDims.width > 0 && naturalDims.height > 0
      ? (naturalDims.height / naturalDims.width >= 2.0 ? "vertical" : (naturalDims.height / naturalDims.width <= 0.5 ? "horizontal" : null))
      : null
  );
  const isVerticalStrip = effectiveStripType === "vertical";
  const isHorizontalStrip = effectiveStripType === "horizontal";
  const isStrip = isVerticalStrip || isHorizontalStrip;

  // Fit mode: "contain" | "fit-width" | "fit-height"
  const [fitMode, setFitMode] = useState(() => {
    if (isVerticalStrip) return "fit-width";
    if (isHorizontalStrip) return "fit-height";
    return "contain";
  });

  const sliderTrackRef = useRef(null);
  const sliderTrackXRef = useRef(null);

  // Zoom & Pan state
  const [zoomScale, setZoomScale] = useState(1);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

  const remoteUrl = post?.file_url || post?.sample_url || post?.preview_url;
  const url = localUrl || remoteUrl;

  // Dimension metrics for strip navigation
  const paneHeight = mediaPaneRef.current?.clientHeight || 800;
  const paneWidth = mediaPaneRef.current?.clientWidth || 1000;
  const naturalRatio = (post?.width && post?.height) ? (Number(post.height) / Number(post.width)) : 1;

  let renderedHeight = paneHeight;
  let renderedWidth = paneWidth;

  if (imgRef.current && imgRef.current.offsetHeight > 0) {
    renderedHeight = imgRef.current.offsetHeight;
    renderedWidth = imgRef.current.offsetWidth;
  } else if (fitMode === "fit-width") {
    renderedWidth = paneWidth;
    renderedHeight = paneWidth * naturalRatio;
  } else if (fitMode === "fit-height") {
    renderedHeight = paneHeight;
    renderedWidth = naturalRatio > 0 ? paneHeight / naturalRatio : paneWidth;
  }

  const effectiveHeight = renderedHeight * zoomScale;
  const effectiveWidth = renderedWidth * zoomScale;

  const maxScrollY = Math.max(0, effectiveHeight - paneHeight);
  const maxScrollX = Math.max(0, effectiveWidth - paneWidth);

  const maxScrollYRef = useRef(maxScrollY);
  const maxScrollXRef = useRef(maxScrollX);
  useEffect(() => {
    maxScrollYRef.current = maxScrollY;
    maxScrollXRef.current = maxScrollX;
  }, [maxScrollY, maxScrollX]);

  const scrollPercentY = maxScrollY > 0 ? Math.min(100, Math.max(0, (-panOffset.y / maxScrollY) * 100)) : 0;
  const scrollPercentX = maxScrollX > 0 ? Math.min(100, Math.max(0, (-panOffset.x / maxScrollX) * 100)) : 0;

  const scrollToRatioY = (ratio) => {
    const clampedRatio = Math.min(1, Math.max(0, ratio));
    setPanOffset((prev) => ({
      ...prev,
      y: -clampedRatio * maxScrollYRef.current,
    }));
  };

  const handleTrackMouseDownY = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const track = sliderTrackRef.current;
    if (!track) return;
    const rect = track.getBoundingClientRect();
    const clickY = e.clientY - rect.top;
    const ratio = rect.height > 0 ? clickY / rect.height : 0;
    scrollToRatioY(ratio);

    const onMouseMove = (moveEvent) => {
      const curY = moveEvent.clientY - rect.top;
      const moveRatio = rect.height > 0 ? curY / rect.height : 0;
      scrollToRatioY(moveRatio);
    };

    const onMouseUp = () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  };

  const scrollToRatioX = (ratio) => {
    const clampedRatio = Math.min(1, Math.max(0, ratio));
    setPanOffset((prev) => ({
      ...prev,
      x: -clampedRatio * maxScrollXRef.current,
    }));
  };

  const handleTrackMouseDownX = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const track = sliderTrackXRef.current;
    if (!track) return;
    const rect = track.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const ratio = rect.width > 0 ? clickX / rect.width : 0;
    scrollToRatioX(ratio);

    const onMouseMove = (moveEvent) => {
      const curX = moveEvent.clientX - rect.left;
      const moveRatio = rect.width > 0 ? curX / rect.width : 0;
      scrollToRatioX(moveRatio);
    };

    const onMouseUp = () => {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  };

  const toggleFitMode = () => {
    setFitMode((prev) => {
      if (prev === "contain") {
        return isHorizontalStrip ? "fit-height" : "fit-width";
      }
      return "contain";
    });
    setZoomScale(1);
    setPanOffset({ x: 0, y: 0 });
  };

  // Fetch tag types from backend
  useEffect(() => {
    let active = true;
    const fetchTypes = async () => {
      if (!post?.tags || post.tags.length === 0) {
        if (active) setTagTypes({});
        return;
      }
      try {
        const res = await api.getTagsWithTypes({
          postId: post.id,
          tags: post.tags,
        });
        if (active && res && Object.keys(res).length > 0) {
          setTagTypes(res);
        }
      } catch (err) {
        console.error("Failed to fetch tag types:", err);
      }
    };
    fetchTypes();
    return () => {
      active = false;
      const p = api.cancelTagFetching();
      if (p && typeof p.catch === "function") {
        p.catch(() => {});
      }
    };
  }, [post?.id, post?.tags]);

  // Group tags by their type
  const groupedTags = React.useMemo(() => {
    const groups = {
      artist: [],
      character: [],
      copyright: [],
      metadata: [],
      general: [],
    };

    if (!post?.tags) return groups;

    post.tags.forEach((tag) => {
      const type = tagTypes[tag];
      if (type === 1) {
        groups.artist.push(tag);
      } else if (type === 4) {
        groups.character.push(tag);
      } else if (type === 3) {
        groups.copyright.push(tag);
      } else if (type === 5) {
        groups.metadata.push(tag);
      } else {
        groups.general.push(tag);
      }
    });

    // Sort tags alphabetically within their respective groups
    groups.artist.sort();
    groups.character.sort();
    groups.copyright.sort();
    groups.metadata.sort();
    groups.general.sort();

    return groups;
  }, [post?.tags, tagTypes]);

  // Reset zoom & pan, sidebar state, and fullscreen when post changes
  useEffect(() => {
    setNaturalDims({ width: 0, height: 0 });
    const nextStrip = getStripType(post);
    const targetMode = nextStrip === "vertical" ? "fit-width" : (nextStrip === "horizontal" ? "fit-height" : "contain");
    setFitMode((prev) => (prev === targetMode ? prev : targetMode));
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
    if (!stripType && naturalDims.width > 0 && naturalDims.height > 0) {
      const ratio = naturalDims.height / naturalDims.width;
      if (ratio >= 2.0) {
        setFitMode("fit-width");
      } else if (ratio <= 0.5) {
        setFitMode("fit-height");
      }
    }
  }, [stripType, naturalDims.width, naturalDims.height]);

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

  // Wheel listener: Ctrl+wheel for zoom, non-Ctrl wheel for scrolling through overflowing/strip content
  useEffect(() => {
    const currentImg = imgRef.current;
    const currentPane = mediaPaneRef.current;
    if (!currentImg && !currentPane) return;

    const handleNativeWheel = (e) => {
      if (e.ctrlKey) {
        e.preventDefault();
        const delta = e.deltaY < 0 ? 0.25 : -0.25;
        setZoomScale((prev) => {
          const next = Math.min(Math.max(prev + delta, 1), 8);
          if (next === 1 && fitMode === "contain") {
            setPanOffset({ x: 0, y: 0 });
          }
          return next;
        });
      } else {
        const curMaxY = maxScrollYRef.current;
        const curMaxX = maxScrollXRef.current;

        if (curMaxY > 0 && Math.abs(e.deltaY) > 0) {
          e.preventDefault();
          setPanOffset((prev) => {
            const nextY = Math.min(0, Math.max(-curMaxY, prev.y - e.deltaY));
            return { ...prev, y: nextY };
          });
        } else if (curMaxX > 0 && (Math.abs(e.deltaX) > 0 || (e.shiftKey && Math.abs(e.deltaY) > 0))) {
          e.preventDefault();
          const delta = e.deltaX !== 0 ? e.deltaX : e.deltaY;
          setPanOffset((prev) => {
            const nextX = Math.min(0, Math.max(-curMaxX, prev.x - delta));
            return { ...prev, x: nextX };
          });
        }
      }
    };

    if (currentImg) {
      currentImg.addEventListener("wheel", handleNativeWheel, { passive: false });
    }
    if (currentPane) {
      currentPane.addEventListener("wheel", handleNativeWheel, { passive: false });
    }

    return () => {
      if (currentImg) {
        currentImg.removeEventListener("wheel", handleNativeWheel);
      }
      if (currentPane) {
        currentPane.removeEventListener("wheel", handleNativeWheel);
      }
    };
  }, [url, fitMode]);

  const canPan = zoomScale > 1 || maxScrollY > 0 || maxScrollX > 0;

  const handleMouseDown = (e) => {
    if (canPan && e.button === 0) {
      e.preventDefault();
      setIsDragging(true);
      setDragStart({ x: e.clientX - panOffset.x, y: e.clientY - panOffset.y });
    }
  };

  const handleMouseMove = (e) => {
    if (isDragging && canPan) {
      e.preventDefault();
      const rawX = e.clientX - dragStart.x;
      const rawY = e.clientY - dragStart.y;
      const curMaxY = maxScrollYRef.current;
      const curMaxX = maxScrollXRef.current;

      const nextY = curMaxY > 0 ? Math.min(0, Math.max(-curMaxY, rawY)) : (zoomScale > 1 ? rawY : 0);
      const nextX = curMaxX > 0 ? Math.min(0, Math.max(-curMaxX, rawX)) : (zoomScale > 1 ? rawX : 0);

      setPanOffset({
        x: nextX,
        y: nextY,
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
        const path = await api.getDownloadedPath({ postId: post.id, md5: post.md5 || "" });
        if (path && active) {
          const assetUrl = convertFileSrc(path);
          setLocalUrl(assetUrl);
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
  const isVideo = isMediaVideo(url) || isMediaVideo(remoteUrl);

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

  const handleDownloadClick = async () => {
    if (!onDownload) return;
    try {
      const res = await onDownload(post);
      if (res?.path) {
        setLocalUrl(convertFileSrc(res.path));
      } else {
        const path = await api.getDownloadedPath({ postId: post.id, md5: post.md5 || "" });
        if (path) {
          setLocalUrl(convertFileSrc(path));
        }
      }
    } catch (err) {
      console.error("Download failed:", err);
    }
  };

  const renderModalMedia = () => {
    if (isVideo) {
      return <VideoPlayer src={url} />;
    }

    const isFitWidth = fitMode === "fit-width";
    const isFitHeight = fitMode === "fit-height";
    const mediaClasses = `modal-media${isFitWidth ? " is-fit-width" : ""}${isFitHeight ? " is-fit-height" : ""}`;

    return (
      <img
        ref={imgRef}
        src={url}
        alt="modal media"
        className={mediaClasses}
        draggable={false}
        onLoad={(e) => {
          if (e.target.naturalWidth && e.target.naturalHeight) {
            setNaturalDims({ width: e.target.naturalWidth, height: e.target.naturalHeight });
          }
        }}
        style={{
          transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${zoomScale})`,
          cursor: canPan ? (isDragging ? "grabbing" : "grab") : "default",
          transition: isDragging ? "none" : "transform 0.1s ease-out",
          transformOrigin: isFitWidth ? "top center" : (isFitHeight ? "center left" : "center center"),
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
          {!isVideo && isStrip && (
            <button
              data-testid="fit-mode-btn"
              className="fit-mode-btn"
              onClick={toggleFitMode}
              disabled={!url}
              aria-label={fitMode === "contain" ? "Fit to Width" : "Fit to Screen"}
              title={fitMode === "contain" ? "Fit to Width (Strip View)" : "Fit to Screen"}
            >
              {fitMode === "contain" ? <Expand size={18} /> : <Shrink size={18} />}
            </button>
          )}
          <button
            data-testid="fullscreen-btn"
            className="fullscreen-btn"
            onClick={toggleFullscreen}
            disabled={!url}
            aria-label="Toggle Fullscreen"
          >
            {isFullscreen ? <Minimize size={18} /> : <Maximize size={18} />}
          </button>

          {!isVideo && maxScrollY > 0 && (
            <div className="strip-slider-container vertical" data-testid="vertical-strip-slider">
              <button
                type="button"
                className="strip-slider-btn top"
                onClick={() => scrollToRatioY(0)}
                title="Jump to Top"
                aria-label="Jump to Top"
              >
                <ChevronUp size={16} />
              </button>
              <div
                className="strip-slider-track"
                ref={sliderTrackRef}
                onMouseDown={handleTrackMouseDownY}
              >
                <div
                  className="strip-slider-progress"
                  style={{ height: `${scrollPercentY}%` }}
                />
                <div
                  className="strip-slider-thumb"
                  style={{ top: `${scrollPercentY}%` }}
                >
                  <span className="strip-slider-tooltip">{Math.round(scrollPercentY)}%</span>
                </div>
              </div>
              <button
                type="button"
                className="strip-slider-btn bottom"
                onClick={() => scrollToRatioY(1)}
                title="Jump to Bottom"
                aria-label="Jump to Bottom"
              >
                <ChevronDown size={16} />
              </button>
            </div>
          )}

          {!isVideo && maxScrollX > 0 && maxScrollY === 0 && (
            <div className="strip-slider-container horizontal" data-testid="horizontal-strip-slider">
              <button
                type="button"
                className="strip-slider-btn left"
                onClick={() => scrollToRatioX(0)}
                title="Jump to Left"
                aria-label="Jump to Left"
              >
                <ChevronLeft size={16} />
              </button>
              <div
                className="strip-slider-track horizontal"
                ref={sliderTrackXRef}
                onMouseDown={handleTrackMouseDownX}
              >
                <div
                  className="strip-slider-progress horizontal"
                  style={{ width: `${scrollPercentX}%` }}
                />
                <div
                  className="strip-slider-thumb horizontal"
                  style={{ left: `${scrollPercentX}%` }}
                >
                  <span className="strip-slider-tooltip">{Math.round(scrollPercentX)}%</span>
                </div>
              </div>
              <button
                type="button"
                className="strip-slider-btn right"
                onClick={() => scrollToRatioX(1)}
                title="Jump to Right"
                aria-label="Jump to Right"
              >
                <ChevronRight size={16} />
              </button>
            </div>
          )}
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
                    {formatPostDate(post.created_at)}
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
              <>
                {/* Artists */}
                {groupedTags.artist.length > 0 && (
                  <div className="info-section">
                    <h3 className="tag-group-title artist">Artists</h3>
                    <div className="tags-container" style={{ marginTop: "8px" }}>
                      {groupedTags.artist.map((tag) => (
                        <span
                          key={tag}
                          className="tag-badge artist"
                          onClick={() => onTagClick(tag)}
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Characters */}
                {groupedTags.character.length > 0 && (
                  <div className="info-section">
                    <h3 className="tag-group-title character">Characters</h3>
                    <div className="tags-container" style={{ marginTop: "8px" }}>
                      {groupedTags.character.map((tag) => (
                        <span
                          key={tag}
                          className="tag-badge character"
                          onClick={() => onTagClick(tag)}
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Copyrights */}
                {groupedTags.copyright.length > 0 && (
                  <div className="info-section">
                    <h3 className="tag-group-title copyright">Copyrights</h3>
                    <div className="tags-container" style={{ marginTop: "8px" }}>
                      {groupedTags.copyright.map((tag) => (
                        <span
                          key={tag}
                          className="tag-badge copyright"
                          onClick={() => onTagClick(tag)}
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* General */}
                {groupedTags.general.length > 0 && (
                  <div className="info-section">
                    <h3 className="tag-group-title general">General</h3>
                    <div className="tags-container" style={{ marginTop: "8px" }}>
                      {groupedTags.general.map((tag) => (
                        <span
                          key={tag}
                          className="tag-badge general"
                          onClick={() => onTagClick(tag)}
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Metadata */}
                {groupedTags.metadata.length > 0 && (
                  <div className="info-section">
                    <h3 className="tag-group-title metadata">Metadata</h3>
                    <div className="tags-container" style={{ marginTop: "8px" }}>
                      {groupedTags.metadata.map((tag) => (
                        <span
                          key={tag}
                          className="tag-badge metadata"
                          onClick={() => onTagClick(tag)}
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </>
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
            <button className="btn-action download" onClick={handleDownloadClick}>
              <Download size={16} />
              Download
            </button>
          </div>
        </div>
      </div>
    </div>
  );
});
