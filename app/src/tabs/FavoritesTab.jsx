import React, { useState, useMemo } from "react";
import { Heart, Loader, RefreshCw, Search, X } from "lucide-react";
import { PostCard, isMediaVideo, isLongStrip } from "../components/PostCard";
import "./FavoritesTab.css";

function isMediaGif(post) {
  const url = post.file_url || post.sample_url || "";
  const cleanUrl = url.split("?")[0].split("#")[0].toLowerCase();
  return cleanUrl.endsWith(".gif");
}

function isStaticImage(post) {
  return (
    !isMediaVideo(post.file_url) &&
    !isMediaVideo(post.sample_url) &&
    !isMediaGif(post)
  );
}

function getPostTags(post) {
  if (Array.isArray(post.tags)) return post.tags;
  if (typeof post.tags === "string") {
    return post.tags.split(/\s+/).filter(Boolean);
  }
  return [];
}

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
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState("date-desc");
  const [mediaFilter, setMediaFilter] = useState("all");
  const [ratingFilter, setRatingFilter] = useState("all");

  const filteredAndSortedPosts = useMemo(() => {
    let list = (favorites || []).map((post, idx) => ({
      post,
      originalIndex: idx,
    }));

    // Filter pipeline
    list = list.filter(({ post }) => {
      // 1. Search Query (tags & ID matching, negative exclusion with -tag)
      if (searchQuery.trim()) {
        const terms = searchQuery
          .trim()
          .toLowerCase()
          .split(/\s+/)
          .filter(Boolean);
        const postTags = getPostTags(post).map((t) => t.toLowerCase());
        const postIdStr = post.id ? post.id.toString() : "";

        for (const term of terms) {
          if (term.startsWith("-") && term.length > 1) {
            const neg = term.slice(1);
            if (postTags.some((t) => t.includes(neg))) {
              return false;
            }
          } else {
            const matchesId = postIdStr.includes(term);
            const matchesTag = postTags.some((t) => t.includes(term));
            if (!matchesId && !matchesTag) {
              return false;
            }
          }
        }
      }

      // 2. Media Type Filter
      if (mediaFilter === "video") {
        if (!isMediaVideo(post.file_url) && !isMediaVideo(post.sample_url)) {
          return false;
        }
      } else if (mediaFilter === "gif") {
        if (!isMediaGif(post)) {
          return false;
        }
      } else if (mediaFilter === "strip") {
        if (!isLongStrip(post)) {
          return false;
        }
      } else if (mediaFilter === "image") {
        if (!isStaticImage(post)) {
          return false;
        }
      }

      // 3. Rating Filter
      if (ratingFilter === "explicit") {
        const r = (post.rating || "").toLowerCase();
        if (r !== "explicit" && r !== "e") {
          return false;
        }
      } else if (ratingFilter === "questionable") {
        const r = (post.rating || "").toLowerCase();
        if (r !== "questionable" && r !== "q") {
          return false;
        }
      }

      return true;
    });

    // Sorting pipeline
    list.sort((a, b) => {
      switch (sortBy) {
        case "date-asc":
          return b.originalIndex - a.originalIndex;
        case "date-desc":
          return a.originalIndex - b.originalIndex;
        case "score-desc":
          return (b.post.score || 0) - (a.post.score || 0);
        case "score-asc":
          return (a.post.score || 0) - (b.post.score || 0);
        case "id-desc":
          return b.post.id - a.post.id;
        case "id-asc":
          return a.post.id - b.post.id;
        default:
          return 0;
      }
    });

    return list.map((item) => item.post);
  }, [favorites, searchQuery, mediaFilter, ratingFilter, sortBy]);

  const hasActiveFilters = Boolean(
    searchQuery.trim() ||
      mediaFilter !== "all" ||
      ratingFilter !== "all" ||
      sortBy !== "date-desc"
  );

  const handleResetFilters = () => {
    setSearchQuery("");
    setMediaFilter("all");
    setRatingFilter("all");
    setSortBy("date-desc");
  };

  return (
    <div>
      {/* Controls Section */}
      <div className="favorites-controls">
        {/* Search Bar */}
        <div className="favorites-search-wrapper">
          <div className="favorites-search-input-container">
            <Search className="favorites-search-icon" size={18} />
            <input
              type="text"
              className="favorites-search-input"
              placeholder="Search tags or post ID in favorites (use -tag to exclude)..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button
                type="button"
                className="favorites-search-clear"
                onClick={() => setSearchQuery("")}
                aria-label="Clear search"
              >
                <X size={16} />
              </button>
            )}
          </div>
        </div>

        {/* Filter Row */}
        <div className="favorites-filters-row">
          <div className="favorites-filter-group">
            {/* Collection Select */}
            <select
              className="favorites-filter-select"
              style={{ minWidth: "160px" }}
              value={selectedCollection}
              onChange={(e) => setSelectedCollection(e.target.value)}
              aria-label="Filter by collection"
            >
              <option value="">All Collections</option>
              {collections.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>

            {/* Sort Dropdown */}
            <select
              className="favorites-filter-select"
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              aria-label="Sort favorites"
            >
              <option value="date-desc">Date Added (Newest)</option>
              <option value="date-asc">Date Added (Oldest)</option>
              <option value="score-desc">Score (Highest)</option>
              <option value="score-asc">Score (Lowest)</option>
              <option value="id-desc">Post ID (Newest)</option>
              <option value="id-asc">Post ID (Oldest)</option>
            </select>

            {/* Media Type Filter */}
            <select
              className="favorites-filter-select"
              value={mediaFilter}
              onChange={(e) => setMediaFilter(e.target.value)}
              aria-label="Filter by media type"
            >
              <option value="all">All Media</option>
              <option value="image">Images Only</option>
              <option value="video">Videos Only</option>
              <option value="gif">GIFs Only</option>
              <option value="strip">Long Strips</option>
            </select>

            {/* Rating Filter */}
            <select
              className="favorites-filter-select"
              value={ratingFilter}
              onChange={(e) => setRatingFilter(e.target.value)}
              aria-label="Filter by rating"
            >
              <option value="all">All Ratings</option>
              <option value="explicit">Explicit</option>
              <option value="questionable">Questionable</option>
            </select>
          </div>

          {/* Sync Button */}
          <button
            className="btn-secondary"
            style={{ width: "160px", justifyContent: "center" }}
            onClick={triggerSync}
            disabled={syncStatus?.is_running}
          >
            {syncStatus?.is_running ? (
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

        {/* Status & Match Counter */}
        {favorites && favorites.length > 0 && (
          <div className="favorites-status-bar">
            <span>
              Showing {filteredAndSortedPosts.length} of {favorites.length}{" "}
              favorites
            </span>
            {hasActiveFilters && (
              <button
                type="button"
                className="favorites-reset-link"
                onClick={handleResetFilters}
              >
                Reset filters
              </button>
            )}
          </div>
        )}
      </div>

      {/* Grid or Empty States */}
      {favorites && favorites.length > 0 ? (
        filteredAndSortedPosts.length > 0 ? (
          <div className="media-grid">
            {filteredAndSortedPosts.map((post) => (
              <PostCard
                key={post.id}
                post={post}
                isFavorite={true}
                onCardClick={setSelectedPost}
                onFavoriteToggle={toggleFavorite}
                onDownload={triggerDownload}
                isSelected={selectedPostIds.includes(post.id)}
                onSelectToggle={onSelectToggle}
              />
            ))}
          </div>
        ) : (
          <div className="favorites-empty-filtered">
            <Search size={40} style={{ marginBottom: "12px", opacity: 0.6 }} />
            <p>No favorites match your active search or filters.</p>
            <button
              className="btn-secondary"
              style={{ marginTop: "16px" }}
              onClick={handleResetFilters}
            >
              Reset Filters
            </button>
          </div>
        )
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
