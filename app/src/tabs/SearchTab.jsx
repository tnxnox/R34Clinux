import React from "react";
import { Search as SearchIcon, Loader, ChevronLeft, ChevronRight } from "lucide-react";
import { PostCard } from "../components/PostCard";
import "./SearchTab.css";

export function SearchTab({
  searchQuery,
  setSearchQuery,
  suggestions,
  searchResults,
  currentPage,
  hasMore,
  loading,
  favorites,
  handleSearch,
  toggleFavorite,
  triggerDownload,
  setSelectedPost,
  handleSuggestionClick,
  autocompleteRef,
  
  // Selection Props
  selectedPostIds = [],
  onSelectToggle,
}) {
  return (
    <div>
      <div className="search-wrapper" ref={autocompleteRef}>
        <div className="search-input-container">
          <SearchIcon className="search-icon-inside" size={18} />
          <input
            type="text"
            className="search-input"
            placeholder="Search tags (e.g. solo, rating:safe, score:>10)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch(0)}
          />
          {suggestions.length > 0 && (
            <div className="autocomplete-dropdown">
              {suggestions.map((s, idx) => (
                <div
                  key={idx}
                  className="autocomplete-item"
                  onClick={() => handleSuggestionClick(s.value)}
                >
                  <span>{s.value}</span>
                  <span className="tag-count">
                    {s.count ? s.count.toLocaleString() : ""}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
        <button
          className="btn-primary"
          style={{ width: "120px" }}
          onClick={() => handleSearch(0)}
        >
          Search
        </button>
      </div>

      {loading ? (
        <div className="loader-container">
          <div className="spinner"></div>
          <p>Searching rule34 database...</p>
        </div>
      ) : searchResults.length > 0 ? (
        <div>
          <div className="media-grid">
            {searchResults.map((post) => {
              const isFav = favorites.some((f) => f.id === post.id);
              return (
                <PostCard
                  key={post.id}
                  post={post}
                  isFavorite={isFav}
                  onCardClick={setSelectedPost}
                  onFavoriteToggle={toggleFavorite}
                  onDownload={triggerDownload}
                  isSelected={selectedPostIds.includes(post.id)}
                  onSelectToggle={onSelectToggle}
                />
              );
            })}
          </div>

          <div className="pagination">
            <button
              className="btn-secondary"
              onClick={() => handleSearch(currentPage - 1)}
              disabled={currentPage === 0}
            >
              <ChevronLeft size={16} /> Previous
            </button>
            <span className="page-num">Page {currentPage + 1}</span>
            <button
              className="btn-secondary"
              onClick={() => handleSearch(currentPage + 1)}
              disabled={!hasMore}
            >
              Next <ChevronRight size={16} />
            </button>
          </div>
        </div>
      ) : (
        <div
          style={{
            textAlign: "center",
            color: "var(--text-muted)",
            marginTop: "80px",
          }}
        >
          <SearchIcon size={48} style={{ marginBottom: "16px" }} />
          <p>Enter tags above and press Enter to search rule34.xxx database.</p>
        </div>
      )}
    </div>
  );
}
