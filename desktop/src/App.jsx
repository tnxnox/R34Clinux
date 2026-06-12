import { useState, useEffect, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";
import {
  Search as SearchIcon,
  Heart,
  Users,
  Folder,
  Settings as SettingsIcon,
  Download,
  Play,
  Pause,
  X,
  Loader,
  Plus,
  Trash2,
  ChevronLeft,
  ChevronRight,
  Check,
  AlertTriangle,
  RefreshCw,
  Info
} from "lucide-react";
import "./App.css";

function App() {

  const [activeTab, setActiveTab] = useState("search");
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [searchResults, setSearchResults] = useState([]);
  const [currentPage, setCurrentPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  // Favorites & Collections state
  const [favorites, setFavorites] = useState([]);
  const [collections, setCollections] = useState([]);
  const [selectedCollection, setSelectedCollection] = useState("");
  const [newCollectionName, setNewCollectionName] = useState("");

  // Friends state
  const [friends, setFriends] = useState([]);
  const [friendUserId, setFriendUserId] = useState("");
  const [friendDisplayName, setFriendDisplayName] = useState("");
  const [friendNotes, setFriendNotes] = useState("");
  const [activeFriend, setActiveFriend] = useState(null);
  const [friendFavorites, setFriendFavorites] = useState([]);
  const [friendPage, setFriendPage] = useState(0);
  const [loadingFriendFavs, setLoadingFriendFavs] = useState(false);

  // Sync state
  const [syncStatus, setSyncStatus] = useState({ is_running: false, debug: "", error: "", success: false });
  const [mutationProgress, setMutationProgress] = useState({ total_mutations: 0, completed_mutations: 0, current_pending: 0 });

  // Detail view state
  const [selectedPost, setSelectedPost] = useState(null);
  const [postCollectionAssign, setPostCollectionAssign] = useState("");

  // Autocomplete ref
  const autocompleteRef = useRef(null);

  // Fetch settings on mount
  useEffect(() => {
    fetchSettings();
    fetchCollections();
    fetchFriends();
    fetchSyncStatus();
    fetchMutationProgress();
  }, []);

  // Fetch favorites when selected collection changes
  useEffect(() => {
    fetchFavorites();
  }, [selectedCollection]);

  // Handle autocomplete search
  useEffect(() => {
    if (searchQuery.trim() === "") {
      setSuggestions([]);
      return;
    }

    const delayDebounce = setTimeout(async () => {
      // Get the last tag typed (separated by spaces)
      const tags = searchQuery.trim().split(/\s+/);
      const lastTag = tags[tags.length - 1];
      if (lastTag.length < 2) {
        setSuggestions([]);
        return;
      }

      try {
        const data = await invoke("autocomplete_tags", { prefix: lastTag });
        setSuggestions(data);
      } catch (err) {
        console.error(err);
      }
    }, 300);

    return () => clearTimeout(delayDebounce);
  }, [searchQuery]);

  // Click outside autocomplete to dismiss
  useEffect(() => {
    function handleClickOutside(event) {
      if (autocompleteRef.current && !autocompleteRef.current.contains(event.target)) {
        setSuggestions([]);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Poll sync status and mutation progress
  useEffect(() => {
    let interval;
    const shouldPoll = syncStatus.is_running || mutationProgress.current_pending > 0;
    if (shouldPoll) {
      interval = setInterval(() => {
        fetchSyncStatus();
        fetchMutationProgress();
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [syncStatus.is_running, mutationProgress.current_pending]);

  // Fetch favorites and collections when sync completes
  const prevIsRunningRef = useRef(false);
  useEffect(() => {
    if (prevIsRunningRef.current && !syncStatus.is_running) {
      // Transitioned from running to not running (finished sync)
      fetchFavorites();
      fetchCollections();
      if (syncStatus.success) {
        showToast("Sync completed successfully!");
      } else if (syncStatus.error) {
        showToast("Sync completed with errors.", "error");
      }
    }
    prevIsRunningRef.current = syncStatus.is_running;
  }, [syncStatus.is_running, syncStatus.success, syncStatus.error]);

  const showToast = (message, type = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  };

  const fetchSettings = async () => {
    try {
      const data = await invoke("get_settings");
      setSettings(data);
    } catch (err) {
      setError("Unable to communicate with the Tauri backend.");
    }
  };

  const saveSettings = async (updated) => {
    setLoading(true);
    try {
      await invoke("update_settings", { payload: updated });
      showToast("Settings saved successfully.");
      fetchSettings();
    } catch (err) {
      showToast("Failed to save settings: " + err, "error");
    } finally {
      setLoading(false);
    }
  };

  const fetchFavorites = async () => {
    try {
      const data = await invoke("list_favorites", {
        collection: selectedCollection || null
      });
      setFavorites(data);
    } catch (err) {
      console.error("Failed to load favorites", err);
    }
  };

  const fetchCollections = async () => {
    try {
      const data = await invoke("list_collections");
      setCollections(data);
    } catch (err) {
      console.error("Failed to load collections", err);
    }
  };

  const fetchFriends = async () => {
    try {
      const data = await invoke("list_friends");
      setFriends(data);
    } catch (err) {
      console.error("Failed to load friends", err);
    }
  };

  const fetchSyncStatus = async () => {
    try {
      const data = await invoke("get_sync_status");
      setSyncStatus(data);
    } catch (err) {
      console.error("Failed to load sync status", err);
    }
  };

  const fetchMutationProgress = async () => {
    try {
      const data = await invoke("get_mutation_progress");
      setMutationProgress(data);
    } catch (err) {
      console.error("Failed to load mutation progress", err);
    }
  };

  const triggerSync = async () => {
    try {
      await invoke("start_sync");
      showToast("Favorites synchronization started.");
      fetchSyncStatus();
    } catch (err) {
      showToast("Failed to run sync: " + err, "error");
    }
  };

  const handleSearch = async (page = 0) => {
    setLoading(true);
    try {
      const data = await invoke("search_posts", {
        tags: searchQuery,
        page: page,
        limit: settings?.page_size || 50
      });
      setSearchResults(data);
      setCurrentPage(page);
      setHasMore(data.length >= (settings?.page_size || 50));
    } catch (err) {
      showToast("Search failed: " + err, "error");
    } finally {
      setLoading(false);
    }
  };

  const toggleFavorite = async (post) => {
    const isFav = favorites.some(f => f.id === post.id);
    try {
      if (isFav) {
        await invoke("remove_favorite", { postId: post.id });
        setFavorites(prev => prev.filter(f => f.id !== post.id));
        showToast("Post removed from favorites.");
      } else {
        const postPayload = {
          id: post.id,
          tags: post.tags || [],
          rating: post.rating || "",
          score: post.score || null,
          width: post.width || null,
          height: post.height || null,
          file_size: post.file_size || null,
          source: post.source || "",
          md5: post.md5 || "",
          preview_url: post.preview_url || "",
          sample_url: post.sample_url || "",
          file_url: post.file_url || "",
          created_at: post.created_at || ""
        };
        await invoke("add_favorite", { post: postPayload });
        setFavorites(prev => [post, ...prev]);
        showToast("Post added to favorites.");
      }
      fetchMutationProgress();
    } catch (err) {
      showToast("Error updating favorites: " + err, "error");
    }
  };

  const triggerDownload = async (post) => {
    showToast("Starting download...");
    try {
      const postPayload = {
        id: post.id,
        tags: post.tags || [],
        rating: post.rating || "",
        score: post.score || null,
        width: post.width || null,
        height: post.height || null,
        file_size: post.file_size || null,
        source: post.source || "",
        md5: post.md5 || "",
        preview_url: post.preview_url || "",
        sample_url: post.sample_url || "",
        file_url: post.file_url || "",
        created_at: post.created_at || ""
      };
      const data = await invoke("download_post", { post: postPayload });
      if (data.status === "downloaded") {
        showToast(`Downloaded to: ${data.path}`);
      } else {
        showToast("Post already downloaded.", "info");
      }
    } catch (err) {
      showToast("Error executing download: " + err, "error");
    }
  };

  const createCollection = async () => {
    if (!newCollectionName.trim()) return;
    try {
      await invoke("create_collection", { name: newCollectionName });
      showToast("Collection created.");
      setNewCollectionName("");
      fetchCollections();
    } catch (err) {
      showToast("Error creating collection: " + err, "error");
    }
  };

  const deleteCollection = async (name) => {
    if (!confirm(`Delete collection "${name}"? Posts in this collection will not be deleted.`)) return;
    try {
      await invoke("delete_collection", { name });
      showToast("Collection deleted.");
      fetchCollections();
    } catch (err) {
      showToast("Error deleting collection: " + err, "error");
    }
  };

  const assignPostToCollection = async (postId, collectionName) => {
    if (!collectionName) return;
    try {
      await invoke("assign_posts_to_collection", { name: collectionName, postIds: [postId] });
      showToast(`Post assigned to ${collectionName}.`);
      setPostCollectionAssign("");
    } catch (err) {
      showToast("Error assigning post: " + err, "error");
    }
  };

  const addFriend = async () => {
    if (!friendUserId.trim() || !friendDisplayName.trim()) return;
    try {
      await invoke("add_friend", {
        userId: friendUserId,
        displayName: friendDisplayName,
        notes: friendNotes || null
      });
      showToast("Friend added.");
      setFriendUserId("");
      setFriendDisplayName("");
      setFriendNotes("");
      fetchFriends();
    } catch (err) {
      showToast("Error adding friend: " + err, "error");
    }
  };

  const removeFriend = async (userId) => {
    if (!confirm("Remove this friend?")) return;
    try {
      await invoke("remove_friend", { userId });
      showToast("Friend removed.");
      fetchFriends();
    } catch (err) {
      showToast("Error removing friend: " + err, "error");
    }
  };

  const fetchFriendFavs = async (userId, page = 0) => {
    setLoadingFriendFavs(true);
    try {
      const data = await invoke("get_friend_favorites", { userId, page });
      setFriendFavorites(data);
      setFriendPage(page);
    } catch (err) {
      showToast("Error fetching friend favorites: " + err, "error");
    } finally {
      setLoadingFriendFavs(false);
    }
  };

  const handleSuggestionClick = (value) => {
    const tags = searchQuery.trim().split(/\s+/);
    tags[tags.length - 1] = value; // Replace the last prefix with full tag
    setSearchQuery(tags.join(" ") + " ");
    setSuggestions([]);
  };

  const handleTagClick = (tag) => {
    // Append tag to search query
    if (!searchQuery.includes(tag)) {
      setSearchQuery(prev => (prev.trim() + " " + tag + " ").replace(/\s+/g, " "));
      setActiveTab("search");
      showToast(`Added tag: ${tag}`);
    }
  };

  const renderMedia = (post, isPreview = false) => {
    const url = post.sample_url || post.file_url || post.preview_url;
    const isVideo = url.endsWith(".mp4") || url.endsWith(".webm");

    if (isVideo) {
      return (
        <video
          src={url}
          className={isPreview ? "modal-media" : "card-thumbnail"}
          controls={isPreview}
          autoPlay={isPreview}
          loop
          muted={!isPreview}
        />
      );
    }

    return (
      <img
        src={url}
        alt="media"
        className={isPreview ? "modal-media" : "card-thumbnail"}
        loading="lazy"
      />
    );
  };

  // Setup Wizard if credentials missing
  if (settings && !settings.has_credentials && activeTab !== "settings") {
    return (
      <div className="app-container">
        <div className="cred-container">
          <div className="cred-card">
            <h2>API Settings Required</h2>
            <p>Welcome! Before you can search rule34.xxx or sync favorites, you need to configure your API Credentials.</p>
            <div className="form-group">
              <label>Rule34 User ID</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. 123456"
                value={settings.user_id}
                onChange={e => setSettings(p => ({ ...p, user_id: e.target.value }))}
              />
            </div>
            <div className="form-group">
              <label>API Key</label>
              <input
                type="password"
                className="form-input"
                placeholder="Enter Rule34 API Key"
                value={settings.api_key}
                onChange={e => setSettings(p => ({ ...p, api_key: e.target.value }))}
              />
            </div>
            <button
              className="btn-primary"
              onClick={() => saveSettings({ user_id: settings.user_id, api_key: settings.api_key })}
            >
              Configure Credentials
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="app-container">
      {/* Toast Notification */}
      {toast && (
        <div style={{
          position: "fixed",
          bottom: "30px",
          right: "30px",
          padding: "16px 24px",
          background: toast.type === "error" ? "rgba(239, 68, 68, 0.95)" : "rgba(99, 102, 241, 0.95)",
          color: "white",
          borderRadius: "12px",
          backdropFilter: "blur(10px)",
          boxShadow: "0 10px 25px rgba(0,0,0,0.3)",
          zIndex: 9999,
          display: "flex",
          alignItems: "center",
          gap: "10px",
          fontSize: "14px",
          fontWeight: "600",
          animation: "fadeIn 0.2s ease-out"
        }}>
          {toast.type === "error" ? <AlertTriangle size={18} /> : <Check size={18} />}
          {toast.message}
        </div>
      )}

      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="logo-container">
          <div className="logo-icon">R</div>
          <span className="logo-text">R34 Client</span>
        </div>

        <nav className="nav-links">
          <div
            className={`nav-item ${activeTab === "search" ? "active" : ""}`}
            onClick={() => { setActiveTab("search"); setActiveFriend(null); }}
          >
            <SearchIcon />
            Search Gallery
          </div>
          <div
            className={`nav-item ${activeTab === "favorites" ? "active" : ""}`}
            onClick={() => { setActiveTab("favorites"); setActiveFriend(null); }}
          >
            <Heart />
            Favorites
          </div>
          <div
            className={`nav-item ${activeTab === "collections" ? "active" : ""}`}
            onClick={() => { setActiveTab("collections"); setActiveFriend(null); }}
          >
            <Folder />
            Collections
          </div>
          <div
            className={`nav-item ${activeTab === "friends" ? "active" : ""}`}
            onClick={() => { setActiveTab("friends"); }}
          >
            <Users />
            Friends
          </div>
          <div
            className={`nav-item ${activeTab === "settings" ? "active" : ""}`}
            onClick={() => { setActiveTab("settings"); setActiveFriend(null); }}
          >
            <SettingsIcon />
            Settings
          </div>
        </nav>


      </aside>

      {/* Main Panel */}
      <main className="main-content">
        <header className="header">
          <h1>
            {activeFriend
              ? `Friend: ${activeFriend.display_name}`
              : activeTab === "search"
              ? "Search Rule34"
              : activeTab === "favorites"
              ? "My Favorites"
              : activeTab === "collections"
              ? "My Collections"
              : activeTab === "friends"
              ? "Friends Manager"
              : "App Settings"}
          </h1>
          {syncStatus.is_running && (
            <div style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "13px", color: "var(--accent)" }}>
              <Loader className="spinner" size={14} /> Synchronizing remote changes...
            </div>
          )}
        </header>

        <div className="content-body">
          {mutationProgress.current_pending > 0 && (
            <div className="mutation-progress-banner">
              <div className="mutation-progress-info">
                <span className="mutation-progress-title">
                  <RefreshCw className="spinner" size={14} style={{ marginRight: '6px' }} />
                  Syncing favorites remotely...
                </span>
                <span className="mutation-progress-count">
                  {mutationProgress.completed_mutations} / {mutationProgress.total_mutations} synced ({mutationProgress.current_pending} left)
                </span>
              </div>
              <div className="mutation-progress-bar-bg">
                <div 
                  className="mutation-progress-bar-fill" 
                  style={{ 
                    width: `${mutationProgress.total_mutations > 0 ? (mutationProgress.completed_mutations / mutationProgress.total_mutations) * 100 : 0}%` 
                  }}
                />
              </div>
            </div>
          )}
          {error && (
            <div style={{
              background: "rgba(239, 68, 68, 0.1)",
              border: "1px solid rgba(239, 68, 68, 0.25)",
              color: "#f87171",
              padding: "16px",
              borderRadius: "12px",
              marginBottom: "20px",
              display: "flex",
              alignItems: "center",
              gap: "10px"
            }}>
              <AlertTriangle size={18} />
              {error}
            </div>
          )}

          {/* Tab: SEARCH */}
          {activeTab === "search" && !activeFriend && (
            <div>
              <div className="search-wrapper" ref={autocompleteRef}>
                <div className="search-input-container">
                  <SearchIcon className="search-icon-inside" size={18} />
                  <input
                    type="text"
                    className="search-input"
                    placeholder="Search tags (e.g. solo, rating:safe, score:>10)..."
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && handleSearch(0)}
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
                          <span className="tag-count">{s.count ? s.count.toLocaleString() : ""}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <button className="btn-primary" style={{ width: "120px" }} onClick={() => handleSearch(0)}>
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
                      const isFav = favorites.some(f => f.id === post.id);
                      return (
                        <div key={post.id} className="post-card" onClick={() => setSelectedPost(post)}>
                          <div className="card-thumbnail-container">
                            {renderMedia(post)}
                            {post.file_url.endsWith(".mp4") && (
                              <span className="video-badge">
                                <Play size={10} fill="white" /> VIDEO
                              </span>
                            )}
                            <span className="rating-badge">{post.rating}</span>
                          </div>
                          <div className="card-info">
                            <span className="card-score">Score: {post.score || 0}</span>
                            <div className="card-actions" onClick={e => e.stopPropagation()}>
                              <button
                                className={`icon-btn favorite ${isFav ? "active" : ""}`}
                                onClick={() => toggleFavorite(post)}
                              >
                                <Heart size={16} fill={isFav ? "currentColor" : "none"} />
                              </button>
                              <button className="icon-btn" onClick={() => triggerDownload(post)}>
                                <Download size={16} />
                              </button>
                            </div>
                          </div>
                        </div>
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
                <div style={{ textAlign: "center", color: "var(--text-muted)", marginTop: "80px" }}>
                  <SearchIcon size={48} style={{ marginBottom: "16px" }} />
                  <p>Enter tags above and press Enter to search rule34.xxx database.</p>
                </div>
              )}
            </div>
          )}

          {/* Tab: FAVORITES */}
          {activeTab === "favorites" && !activeFriend && (
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "16px", marginBottom: "30px" }}>
                <select
                  className="form-input"
                  style={{ width: "250px" }}
                  value={selectedCollection}
                  onChange={e => setSelectedCollection(e.target.value)}
                >
                  <option value="">All Collections</option>
                  {collections.map(c => (
                    <option key={c} value={c}>{c}</option>
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
                      <div key={post.id} className="post-card" onClick={() => setSelectedPost(post)}>
                        <div className="card-thumbnail-container">
                          {renderMedia(post)}
                          {post.file_url.endsWith(".mp4") && (
                            <span className="video-badge">
                              <Play size={10} fill="white" /> VIDEO
                            </span>
                          )}
                          <span className="rating-badge">{post.rating}</span>
                        </div>
                        <div className="card-info">
                          <span className="card-score">Score: {post.score || 0}</span>
                          <div className="card-actions" onClick={e => e.stopPropagation()}>
                            <button
                              className="icon-btn favorite active"
                              onClick={() => toggleFavorite(post)}
                            >
                              <Heart size={16} fill="currentColor" />
                            </button>
                            <button className="icon-btn" onClick={() => triggerDownload(post)}>
                              <Download size={16} />
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                </div>
              ) : (
                <div style={{ textAlign: "center", color: "var(--text-muted)", marginTop: "80px" }}>
                  <Heart size={48} style={{ marginBottom: "16px" }} />
                  <p>You haven't saved any favorites to your local database yet.</p>
                </div>
              )}
            </div>
          )}

          {/* Tab: COLLECTIONS */}
          {activeTab === "collections" && !activeFriend && (
            <div className="collections-panel">
              <div className="create-collection-box">
                <input
                  type="text"
                  className="form-input"
                  placeholder="New collection name..."
                  value={newCollectionName}
                  onChange={e => setNewCollectionName(e.target.value)}
                />
                <button className="btn-primary" style={{ width: "160px" }} onClick={createCollection}>
                  <Plus size={16} style={{ marginRight: "6px" }} /> Create
                </button>
              </div>

              {collections.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  {collections.map(name => (
                    <div key={name} className="collection-row">
                      <span style={{ fontWeight: "600" }}>{name}</span>
                      <button className="icon-btn" onClick={() => deleteCollection(name)}>
                        <Trash2 size={16} className="text-danger" />
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ textAlign: "center", color: "var(--text-muted)", marginTop: "60px" }}>
                  <Folder size={48} style={{ marginBottom: "16px" }} />
                  <p>No collections created. Group your local favorites into folders.</p>
                </div>
              )}
            </div>
          )}

          {/* Tab: FRIENDS */}
          {activeTab === "friends" && !activeFriend && (
            <div>
              <div className="cred-card" style={{ width: "100%", textAlign: "left", marginBottom: "30px" }}>
                <h3 style={{ fontSize: "16px", marginBottom: "16px" }}>Add Friend Account</h3>
                <div style={{ display: "flex", gap: "16px" }}>
                  <input
                    type="text"
                    className="form-input"
                    placeholder="Friend User ID"
                    value={friendUserId}
                    onChange={e => setFriendUserId(e.target.value)}
                  />
                  <input
                    type="text"
                    className="form-input"
                    placeholder="Display Name"
                    value={friendDisplayName}
                    onChange={e => setFriendDisplayName(e.target.value)}
                  />
                  <input
                    type="text"
                    className="form-input"
                    placeholder="Notes"
                    value={friendNotes}
                    onChange={e => setFriendNotes(e.target.value)}
                  />
                  <button className="btn-primary" style={{ width: "150px" }} onClick={addFriend}>
                    Add Friend
                  </button>
                </div>
              </div>

              {friends.length > 0 ? (
                <div>
                  {friends.map(friend => (
                    <div key={friend.user_id} className="friend-card">
                      <div className="friend-details">
                        <h4>{friend.display_name}</h4>
                        <p>User ID: {friend.user_id} {friend.notes ? `• ${friend.notes}` : ""}</p>
                      </div>
                      <div style={{ display: "flex", gap: "12px" }}>
                        <button
                          className="btn-secondary"
                          onClick={() => {
                            setActiveFriend(friend);
                            fetchFriendFavs(friend.user_id, 0);
                          }}
                        >
                          View Favorites
                        </button>
                        <button className="icon-btn" onClick={() => removeFriend(friend.user_id)}>
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ textAlign: "center", color: "var(--text-muted)", marginTop: "60px" }}>
                  <Users size={48} style={{ marginBottom: "16px" }} />
                  <p>You haven't added any friend user accounts yet.</p>
                </div>
              )}
            </div>
          )}

          {/* View Friend Favorites Page */}
          {activeFriend && (
            <div>
              <div style={{ marginBottom: "20px" }}>
                <button className="btn-secondary" onClick={() => { setActiveFriend(null); setFriendFavorites([]); }}>
                  &larr; Back to Friends
                </button>
              </div>

              {loadingFriendFavs ? (
                <div className="loader-container">
                  <div className="spinner"></div>
                  <p>Scraping public favorites page (using FlareSolverr if enabled)...</p>
                </div>
              ) : friendFavorites.length > 0 ? (
                <div>
                  <div className="media-grid">
                    {friendFavorites.map((post) => {
                      const isFav = favorites.some(f => f.id === post.id);
                      return (
                        <div key={post.id} className="post-card" onClick={() => setSelectedPost(post)}>
                          <div className="card-thumbnail-container">
                            <img src={post.preview_url} alt="media preview" className="card-thumbnail" loading="lazy" />
                            <span className="rating-badge">Public</span>
                          </div>
                          <div className="card-info">
                            <span className="card-score">ID: {post.id}</span>
                            <div className="card-actions" onClick={e => e.stopPropagation()}>
                              <button
                                className={`icon-btn favorite ${isFav ? "active" : ""}`}
                                onClick={() => toggleFavorite(post)}
                              >
                                <Heart size={16} fill={isFav ? "currentColor" : "none"} />
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  <div className="pagination">
                    <button
                      className="btn-secondary"
                      onClick={() => fetchFriendFavs(activeFriend.user_id, friendPage - 1)}
                      disabled={friendPage === 0}
                    >
                      <ChevronLeft size={16} /> Previous
                    </button>
                    <span className="page-num">Page {friendPage + 1}</span>
                    <button
                      className="btn-secondary"
                      onClick={() => fetchFriendFavs(activeFriend.user_id, friendPage + 1)}
                    >
                      Next <ChevronRight size={16} />
                    </button>
                  </div>
                </div>
              ) : (
                <div style={{ textAlign: "center", color: "var(--text-muted)", marginTop: "60px" }}>
                  <Heart size={48} style={{ marginBottom: "16px" }} />
                  <p>No public favorites found for this friend or request blocked by Cloudflare.</p>
                </div>
              )}
            </div>
          )}

          {/* Tab: SETTINGS */}
          {activeTab === "settings" && settings && (
            <div style={{ maxWidth: "600px" }}>
              <div className="cred-card" style={{ width: "100%", textAlign: "left", marginBottom: "30px" }}>
                <h3 style={{ fontSize: "16px", marginBottom: "20px" }}>Rule34 API Credentials</h3>
                <div className="form-group">
                  <label>User ID</label>
                  <input
                    type="text"
                    className="form-input"
                    value={settings.user_id}
                    onChange={e => setSettings(p => ({ ...p, user_id: e.target.value }))}
                  />
                </div>
                <div className="form-group">
                  <label>API Key</label>
                  <input
                    type="password"
                    className="form-input"
                    value={settings.api_key}
                    onChange={e => setSettings(p => ({ ...p, api_key: e.target.value }))}
                  />
                </div>
              </div>

              <div className="cred-card" style={{ width: "100%", textAlign: "left", marginBottom: "30px" }}>
                <h3 style={{ fontSize: "16px", marginBottom: "20px" }}>Rule34 Website Login (for Sync)</h3>
                <div className="form-group">
                  <label>Username</label>
                  <input
                    type="text"
                    className="form-input"
                    value={settings.website_username}
                    onChange={e => setSettings(p => ({ ...p, website_username: e.target.value }))}
                  />
                </div>
                <div className="form-group">
                  <label>Password</label>
                  <input
                    type="password"
                    className="form-input"
                    value={settings.website_password}
                    onChange={e => setSettings(p => ({ ...p, website_password: e.target.value }))}
                  />
                </div>
              </div>

              <div className="cred-card" style={{ width: "100%", textAlign: "left", marginBottom: "30px" }}>
                <h3 style={{ fontSize: "16px", marginBottom: "20px" }}>Download Preferences</h3>
                <div className="form-group">
                  <label>Download Directory</label>
                  <input
                    type="text"
                    className="form-input"
                    value={settings.download_directory}
                    onChange={e => setSettings(p => ({ ...p, download_directory: e.target.value }))}
                  />
                </div>
                <div className="form-group">
                  <label>Naming Template (e.g. &#123;id&#125; or &#123;md5&#125;)</label>
                  <input
                    type="text"
                    className="form-input"
                    value={settings.download_naming_template}
                    onChange={e => setSettings(p => ({ ...p, download_naming_template: e.target.value }))}
                  />
                </div>
                <div style={{ display: "flex", gap: "20px", marginTop: "16px" }}>
                  <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer", fontSize: "13px" }}>
                    <input
                      type="checkbox"
                      checked={settings.download_sidecar_enabled}
                      onChange={e => setSettings(p => ({ ...p, download_sidecar_enabled: e.target.checked }))}
                    />
                    Save JSON/TXT tags sidecar
                  </label>
                  <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer", fontSize: "13px" }}>
                    <input
                      type="checkbox"
                      checked={settings.download_use_sample}
                      onChange={e => setSettings(p => ({ ...p, download_use_sample: e.target.checked }))}
                    />
                    Use compressed sample files
                  </label>
                </div>
              </div>

              <div className="cred-card" style={{ width: "100%", textAlign: "left", marginBottom: "30px" }}>
                <h3 style={{ fontSize: "16px", marginBottom: "20px" }}>FlareSolverr (Cloudflare Bypass)</h3>
                <div style={{ marginBottom: "16px" }}>
                  <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer", fontSize: "13px" }}>
                    <input
                      type="checkbox"
                      checked={settings.flaresolverr_enabled}
                      onChange={e => setSettings(p => ({ ...p, flaresolverr_enabled: e.target.checked }))}
                    />
                    Enable FlareSolverr Proxy
                  </label>
                </div>
                <div className="form-group">
                  <label>FlareSolverr URL</label>
                  <input
                    type="text"
                    className="form-input"
                    value={settings.flaresolverr_url}
                    onChange={e => setSettings(p => ({ ...p, flaresolverr_url: e.target.value }))}
                  />
                </div>
              </div>

              {/* Sync Status Log */}
              <div className="cred-card" style={{ width: "100%", textAlign: "left", marginBottom: "30px", background: "rgba(15,17,32,0.6)" }}>
                <h3 style={{ fontSize: "16px", marginBottom: "12px", display: "flex", alignItems: "center", gap: "8px" }}>
                  <RefreshCw size={16} /> Favorites Sync Logs
                </h3>
                {syncStatus.debug || syncStatus.error ? (
                  <div style={{ background: "rgba(0,0,0,0.3)", padding: "12px", borderRadius: "8px", maxHeight: "200px", overflowY: "auto", fontFamily: "monospace", fontSize: "12px" }}>
                    {syncStatus.error && (
                      <div style={{ color: "#f87171", marginBottom: "8px", fontWeight: "bold" }}>
                        Error: {syncStatus.error}
                      </div>
                    )}
                    {syncStatus.debug.split("\n").map((line, idx) => (
                      <div key={idx} style={{ color: line.includes("[Outcome]") || line.includes("completed") ? "#34d399" : "var(--text-secondary)" }}>
                        {line}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p style={{ fontSize: "13px", color: "var(--text-muted)" }}>No sync operation has run in this session yet.</p>
                )}
              </div>

              <button className="btn-primary" onClick={() => saveSettings(settings)}>
                Save All Settings
              </button>
            </div>
          )}
        </div>
      </main>

      {/* Detail view Modal */}
      {selectedPost && (
        <div className="modal-overlay" onClick={() => setSelectedPost(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-media-pane">
              {renderMedia(selectedPost, true)}
            </div>

            <div className="modal-info-pane">
              <div className="modal-info-header">
                <span className="modal-title">Post #{selectedPost.id}</span>
                <button className="icon-btn" onClick={() => setSelectedPost(null)}>
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
                      <div style={{ fontWeight: "600" }}>{selectedPost.score || 0}</div>
                    </div>
                    <div className="metadata-item">
                      <div className="metadata-label">Rating</div>
                      <div style={{ fontWeight: "600", textTransform: "capitalize" }}>{selectedPost.rating}</div>
                    </div>
                    <div className="metadata-item">
                      <div className="metadata-label">Dimensions</div>
                      <div style={{ fontWeight: "600" }}>{selectedPost.dimensions || "Unknown"}</div>
                    </div>
                    <div className="metadata-item">
                      <div className="metadata-label">Date</div>
                      <div style={{ fontWeight: "600" }}>
                        {selectedPost.created_at ? new Date(parseInt(selectedPost.created_at) * 1000).toLocaleDateString() : "Unknown"}
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
                        onChange={e => setPostCollectionAssign(e.target.value)}
                      >
                        <option value="">Select collection...</option>
                        {collections.map(c => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>
                      <button
                        className="btn-primary"
                        style={{ width: "80px", padding: "10px" }}
                        onClick={() => assignPostToCollection(selectedPost.id, postCollectionAssign)}
                      >
                        Assign
                      </button>
                    </div>
                  </div>
                )}

                {/* Tags */}
                {selectedPost.tags && selectedPost.tags.length > 0 && (
                  <div className="info-section">
                    <h3>Associated Tags</h3>
                    <div className="tags-container" style={{ marginTop: "8px" }}>
                      {selectedPost.tags.map(tag => (
                        <span key={tag} className="tag-badge" onClick={() => { handleTagClick(tag); setSelectedPost(null); }}>
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Actions Footer */}
              <div className="modal-actions">
                <button
                  className={`btn-action fav ${favorites.some(f => f.id === selectedPost.id) ? "active" : ""}`}
                  onClick={() => toggleFavorite(selectedPost)}
                >
                  <Heart size={16} fill={favorites.some(f => f.id === selectedPost.id) ? "currentColor" : "none"} />
                  Favorite
                </button>
                <button className="btn-action download" onClick={() => triggerDownload(selectedPost)}>
                  <Download size={16} />
                  Download
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
