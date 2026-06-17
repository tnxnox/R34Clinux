import { useState, useEffect, useRef, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import {
  AlertTriangle,
  Check,
  Loader,
  RefreshCw
} from "lucide-react";
import "./App.css";

// Components
import { Sidebar } from "./components/Sidebar";
import { DetailModal } from "./components/DetailModal";
import { MultiSelectToolbar } from "./components/MultiSelectToolbar";

// Tabs
import { SearchTab } from "./tabs/SearchTab";
import { FavoritesTab } from "./tabs/FavoritesTab";
import { CollectionsTab } from "./tabs/CollectionsTab";
import { FriendsTab } from "./tabs/FriendsTab";
import { SettingsTab } from "./tabs/SettingsTab";

import { listen } from "@tauri-apps/api/event";
import { ErrorBoundary } from "./components/ErrorBoundary";

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

  // Selection state for bulk operations
  const [selectedPosts, setSelectedPosts] = useState([]);
  const [isExiting, setIsExiting] = useState(false);
  useEffect(() => {
    setSelectedPosts([]);
  }, [activeTab]);

  useEffect(() => {
    const unlistenPromise = listen("app-exit-sync-start", () => {
      setIsExiting(true);
    });
    return () => {
      unlistenPromise.then(unlisten => unlisten());
    };
  }, []);

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

  // Fetch full post detail on-demand when selected (useful for scraped friend favorites)
  useEffect(() => {
    if (!selectedPost) return;

    const needsDetail =
      !selectedPost.file_url ||
      selectedPost.sample_url === selectedPost.preview_url ||
      !selectedPost.tags ||
      selectedPost.tags.length === 0;

    if (!needsDetail) return;

    const loadPostDetail = async () => {
      try {
        const fullPost = await invoke("get_post_by_id", { id: selectedPost.id });
        if (fullPost) {
          setSelectedPost(fullPost);
        }
      } catch (err) {
        console.error("Failed to load post detail:", err);
      }
    };

    loadPostDetail();
  }, [selectedPost?.id]);

  // Handle autocomplete search
  useEffect(() => {
    if (searchQuery.trim() === "") {
      setSuggestions([]);
      return;
    }

    const delayDebounce = setTimeout(async () => {
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
    const interval = setInterval(() => {
      fetchSyncStatus();
      fetchMutationProgress();
    }, 3000);
    return () => clearInterval(interval);
  }, [fetchSyncStatus, fetchMutationProgress]);

  // Fetch favorites and collections when sync completes
  const prevIsRunningRef = useRef(false);
  useEffect(() => {
    if (prevIsRunningRef.current && !syncStatus.is_running) {
      fetchFavorites();
      fetchCollections();
      fetchMutationProgress();
      if (syncStatus.success) {
        showToast("Sync completed successfully!");
      } else if (syncStatus.error) {
        showToast("Sync completed with errors.", "error");
      }
    }
    prevIsRunningRef.current = syncStatus.is_running;
  }, [syncStatus.is_running, syncStatus.success, syncStatus.error]);

  const showToast = useCallback((message, type = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 4000);
  }, []);

  const fetchSettings = useCallback(async () => {
    try {
      const data = await invoke("get_settings");
      setSettings(data);
    } catch (err) {
      setError("Unable to communicate with the Tauri backend.");
    }
  }, []);

  const saveSettings = useCallback(async (updated) => {
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
  }, [showToast, fetchSettings]);

  const fetchFavorites = useCallback(async () => {
    try {
      const data = await invoke("list_favorites", {
        collection: selectedCollection || null
      });
      setFavorites(data);
    } catch (err) {
      console.error("Failed to load favorites", err);
    }
  }, [selectedCollection]);

  const fetchCollections = useCallback(async () => {
    try {
      const data = await invoke("list_collections");
      setCollections(data);
    } catch (err) {
      console.error("Failed to load collections", err);
    }
  }, []);

  const fetchFriends = useCallback(async () => {
    try {
      const data = await invoke("list_friends");
      setFriends(data);
    } catch (err) {
      console.error("Failed to load friends", err);
    }
  }, []);

  const fetchSyncStatus = useCallback(async () => {
    try {
      const data = await invoke("get_sync_status");
      setSyncStatus(data);
    } catch (err) {
      console.error("Failed to load sync status", err);
    }
  }, []);

  const fetchMutationProgress = useCallback(async () => {
    try {
      const data = await invoke("get_mutation_progress");
      setMutationProgress(data);
    } catch (err) {
      console.error("Failed to load mutation progress", err);
    }
  }, []);

  const triggerSync = useCallback(async () => {
    try {
      await invoke("start_sync");
      showToast("Favorites synchronization started.");
      fetchSyncStatus();
    } catch (err) {
      showToast("Failed to run sync: " + err, "error");
    }
  }, [showToast, fetchSyncStatus]);

  const handleSearch = useCallback(async (page = 0) => {
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
  }, [searchQuery, settings?.page_size, showToast]);

  const toggleFavorite = useCallback(async (post) => {
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
  }, [favorites, showToast, fetchMutationProgress]);

  const triggerDownload = useCallback(async (post) => {
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
  }, [showToast]);

  const createCollection = useCallback(async () => {
    if (!newCollectionName.trim()) return;
    try {
      await invoke("create_collection", { name: newCollectionName });
      showToast("Collection created.");
      setNewCollectionName("");
      fetchCollections();
    } catch (err) {
      showToast("Error creating collection: " + err, "error");
    }
  }, [newCollectionName, showToast, fetchCollections]);

  const deleteCollection = useCallback(async (name) => {
    if (!confirm(`Delete collection "${name}"? Posts in this collection will not be deleted.`)) return;
    try {
      await invoke("delete_collection", { name });
      showToast("Collection deleted.");
      fetchCollections();
    } catch (err) {
      showToast("Error deleting collection: " + err, "error");
    }
  }, [showToast, fetchCollections]);

  const assignPostToCollection = useCallback(async (post, collectionName) => {
    if (!collectionName) return;
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
      await invoke("assign_posts_to_collection", { name: collectionName, posts: [postPayload] });
      showToast(`Post assigned to ${collectionName}.`);
    } catch (err) {
      showToast("Error assigning post: " + err, "error");
    }
  }, [showToast]);

  const addFriend = useCallback(async () => {
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
  }, [friendUserId, friendDisplayName, friendNotes, showToast, fetchFriends]);

  const removeFriend = useCallback(async (userId) => {
    if (!confirm("Remove this friend?")) return;
    try {
      await invoke("remove_friend", { userId });
      showToast("Friend removed.");
      fetchFriends();
    } catch (err) {
      showToast("Error removing friend: " + err, "error");
    }
  }, [showToast, fetchFriends]);

  const fetchFriendFavs = useCallback(async (userId, page = 0) => {
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
  }, [showToast]);

  const handleSuggestionClick = useCallback((value) => {
    const tags = searchQuery.trim().split(/\s+/);
    tags[tags.length - 1] = value;
    setSearchQuery(tags.join(" ") + " ");
    setSuggestions([]);
  }, [searchQuery]);

  const handleTagClick = useCallback((tag) => {
    if (!searchQuery.includes(tag)) {
      setSearchQuery(prev => (prev.trim() + " " + tag + " ").replace(/\s+/g, " "));
      setActiveTab("search");
      showToast(`Added tag: ${tag}`);
    }
  }, [searchQuery, showToast]);

  const handleAddBlacklistTag = useCallback((tag) => {
    if (!settings) return;
    const currentTags = settings.blacklisted_tags || [];
    if (!currentTags.includes(tag)) {
      setSettings(prev => ({
        ...prev,
        blacklisted_tags: [...currentTags, tag]
      }));
    }
  }, [settings]);

  const handleRemoveBlacklistTag = useCallback((tag) => {
    if (!settings) return;
    const currentTags = settings.blacklisted_tags || [];
    setSettings(prev => ({
      ...prev,
      blacklisted_tags: currentTags.filter(t => t !== tag)
    }));
  }, [settings]);

  const handleSelectToggle = useCallback((postId) => {
    setSelectedPosts(prev => {
      const exists = prev.some(p => p.id === postId);
      if (exists) {
        return prev.filter(p => p.id !== postId);
      } else {
        const post = searchResults.find(p => p.id === postId) || favorites.find(p => p.id === postId) || friendFavorites.find(p => p.id === postId);
        if (post) {
          return [...prev, post];
        }
        return prev;
      }
    });
  }, [searchResults, favorites, friendFavorites]);

  const handleBulkFavorite = useCallback(async (posts, setFav) => {
    showToast(`${setFav ? "Favoriting" : "Unfavoriting"} ${posts.length} posts...`);
    let succeeded = 0;
    let failed = 0;
    
    for (const post of posts) {
      try {
        if (setFav) {
          const isAlreadyFav = favorites.some(f => f.id === post.id);
          if (!isAlreadyFav) {
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
          }
        } else {
          await invoke("remove_favorite", { postId: post.id });
          setFavorites(prev => prev.filter(f => f.id !== post.id));
        }
        succeeded++;
      } catch (err) {
        console.error("Bulk favorite failed for post id", post.id, err);
        failed++;
      }
    }
    
    fetchMutationProgress();
    setSelectedPosts([]);
    
    if (failed === 0) {
      showToast(`Successfully processed ${succeeded} posts.`);
    } else {
      showToast(`Processed posts: ${succeeded} succeeded, ${failed} failed.`, "error");
    }
  }, [favorites, showToast, fetchMutationProgress]);

  const handleBulkDownload = useCallback(async (posts) => {
    showToast(`Downloading ${posts.length} posts...`);
    let downloadedCount = 0;
    let skippedCount = 0;
    let failedCount = 0;
    
    for (const post of posts) {
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
          downloadedCount++;
        } else {
          skippedCount++;
        }
      } catch (err) {
        console.error("Download failed for post id", post.id, err);
        failedCount++;
      }
    }
    
    setSelectedPosts([]);
    if (failedCount === 0) {
      showToast(`Bulk download complete: ${downloadedCount} downloaded, ${skippedCount} skipped.`);
    } else {
      showToast(`Bulk download completed with errors: ${downloadedCount} downloaded, ${failedCount} failed.`, "error");
    }
  }, [showToast]);

  const handleBulkAssignCollection = useCallback(async (posts, collectionName) => {
    if (!collectionName) return;
    showToast(`Assigning ${posts.length} posts to collection "${collectionName}"...`);
    try {
      const postPayloads = posts.map(post => ({
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
      }));
      await invoke("assign_posts_to_collection", { name: collectionName, posts: postPayloads });
      showToast(`Successfully assigned ${posts.length} posts to collection "${collectionName}".`);
      setSelectedPosts([]);
      fetchFavorites();
    } catch (err) {
      showToast("Error assigning posts: " + err, "error");
    }
  }, [showToast, fetchFavorites]);

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

  if (isExiting) {
    return (
      <div style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(5, 5, 10, 0.85)",
        backdropFilter: "blur(20px)",
        zIndex: 99999,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        color: "white",
        gap: "24px",
      }}>
        <div className="spinner" style={{ width: "48px", height: "48px" }}></div>
        <div style={{ textAlign: "center" }}>
          <h2 style={{ fontSize: "20px", fontWeight: "700", marginBottom: "8px" }}>Syncing to Cloud...</h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "14px" }}>Saving your favorites before exiting. Please do not force close.</p>
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
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        setActiveFriend={setActiveFriend}
      />

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

          {/* Tab Content */}
          <ErrorBoundary>
            {activeTab === "search" && !activeFriend && (
              <SearchTab
                searchQuery={searchQuery}
                setSearchQuery={setSearchQuery}
                suggestions={suggestions}
                searchResults={searchResults}
                currentPage={currentPage}
                hasMore={hasMore}
                loading={loading}
                favorites={favorites}
                handleSearch={handleSearch}
                toggleFavorite={toggleFavorite}
                triggerDownload={triggerDownload}
                setSelectedPost={setSelectedPost}
                handleSuggestionClick={handleSuggestionClick}
                autocompleteRef={autocompleteRef}
                selectedPostIds={selectedPosts.map(p => p.id)}
                onSelectToggle={handleSelectToggle}
              />
            )}

            {activeTab === "favorites" && !activeFriend && (
              <FavoritesTab
                selectedCollection={selectedCollection}
                setSelectedCollection={setSelectedCollection}
                collections={collections}
                favorites={favorites}
                syncStatus={syncStatus}
                triggerSync={triggerSync}
                toggleFavorite={toggleFavorite}
                triggerDownload={triggerDownload}
                setSelectedPost={setSelectedPost}
                selectedPostIds={selectedPosts.map(p => p.id)}
                onSelectToggle={handleSelectToggle}
              />
            )}

            {activeTab === "collections" && !activeFriend && (
              <CollectionsTab
                newCollectionName={newCollectionName}
                setNewCollectionName={setNewCollectionName}
                createCollection={createCollection}
                collections={collections}
                deleteCollection={deleteCollection}
              />
            )}

            {activeTab === "friends" && (
              <FriendsTab
                activeFriend={activeFriend}
                setActiveFriend={setActiveFriend}
                friendUserId={friendUserId}
                setFriendUserId={setFriendUserId}
                friendDisplayName={friendDisplayName}
                setFriendDisplayName={setFriendDisplayName}
                friendNotes={friendNotes}
                setFriendNotes={setFriendNotes}
                addFriend={addFriend}
                friends={friends}
                removeFriend={removeFriend}
                loadingFriendFavs={loadingFriendFavs}
                friendFavorites={friendFavorites}
                setFriendFavorites={setFriendFavorites}
                friendPage={friendPage}
                fetchFriendFavs={fetchFriendFavs}
                favorites={favorites}
                toggleFavorite={toggleFavorite}
                setSelectedPost={setSelectedPost}
              />
            )}

            {activeTab === "settings" && settings && (
              <SettingsTab
                settings={settings}
                setSettings={setSettings}
                syncStatus={syncStatus}
                saveSettings={saveSettings}
                blacklistedTags={settings.blacklisted_tags || []}
                onAddBlacklistTag={handleAddBlacklistTag}
                onRemoveBlacklistTag={handleRemoveBlacklistTag}
              />
            )}
          </ErrorBoundary>
        </div>
      </main>

      {/* Detail view Modal */}
      {selectedPost && (
        <DetailModal
          post={selectedPost}
          collections={collections}
          favorites={favorites}
          onClose={() => setSelectedPost(null)}
          onFavoriteToggle={toggleFavorite}
          onDownload={triggerDownload}
          onAssignCollection={assignPostToCollection}
          onTagClick={handleTagClick}
        />
      )}

      {/* Bulk Operations Toolbar */}
      <MultiSelectToolbar
        selectedPosts={selectedPosts}
        activeTab={activeTab}
        collections={collections}
        onClear={() => setSelectedPosts([])}
        onBulkFavorite={handleBulkFavorite}
        onBulkDownload={handleBulkDownload}
        onBulkAssignCollection={handleBulkAssignCollection}
      />
    </div>
  );
}

export default App;
