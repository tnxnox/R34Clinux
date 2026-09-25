import React, { useState } from "react";
import { Users, Trash2, Heart, ChevronLeft, ChevronRight } from "lucide-react";
import { PostCard } from "../components/PostCard";
import "./FriendsTab.css";

export function FriendsTab({
  activeFriend,
  setActiveFriend,
  friendUserId: propUserId,
  setFriendUserId: propSetUserId,
  friendDisplayName: propDisplayName,
  setFriendDisplayName: propSetDisplayName,
  friendNotes: propNotes,
  setFriendNotes: propSetNotes,
  addFriend,
  friends = [],
  removeFriend,
  loadingFriendFavs,
  friendFavorites = [],
  setFriendFavorites,
  friendPage = 0,
  fetchFriendFavs,
  favorites = [],
  toggleFavorite,
  setSelectedPost,
}) {
  const [internalUserId, setInternalUserId] = useState("");
  const [internalDisplayName, setInternalDisplayName] = useState("");
  const [internalNotes, setInternalNotes] = useState("");

  const userId = propUserId !== undefined ? propUserId : internalUserId;
  const setUserId = propSetUserId || setInternalUserId;
  const displayName = propDisplayName !== undefined ? propDisplayName : internalDisplayName;
  const setDisplayName = propSetDisplayName || setInternalDisplayName;
  const notes = propNotes !== undefined ? propNotes : internalNotes;
  const setNotes = propSetNotes || setInternalNotes;

  const handleAddFriend = () => {
    if (addFriend) {
      addFriend({ userId, displayName, notes });
      if (!propSetUserId) setInternalUserId("");
      if (!propSetDisplayName) setInternalDisplayName("");
      if (!propSetNotes) setInternalNotes("");
    }
  };

  if (activeFriend) {
    return (
      <div>
        <div style={{ marginBottom: "20px" }}>
          <button
            className="btn-secondary"
            onClick={() => {
              setActiveFriend(null);
              if (setFriendFavorites) setFriendFavorites([]);
            }}
          >
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
                const isFav = favorites.some((f) => f.id === post.id);
                return (
                  <PostCard
                    key={post.id}
                    post={post}
                    isFavorite={isFav}
                    onCardClick={setSelectedPost}
                    onFavoriteToggle={toggleFavorite}
                    showPublicBadge={true}
                    showIdAsScore={true}
                  />
                );
              })}
            </div>

            <div className="pagination">
              <button
                className="btn-secondary"
                onClick={() => fetchFriendFavs && fetchFriendFavs(activeFriend.user_id, friendPage - 1)}
                disabled={friendPage === 0}
              >
                <ChevronLeft size={16} /> Previous
              </button>
              <span className="page-num">Page {friendPage + 1}</span>
              <button
                className="btn-secondary"
                onClick={() => fetchFriendFavs && fetchFriendFavs(activeFriend.user_id, friendPage + 1)}
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
              marginTop: "60px",
            }}
          >
            <Heart size={48} style={{ marginBottom: "16px" }} />
            <p>No public favorites found for this friend or request blocked by Cloudflare.</p>
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      <div
        className="cred-card"
        style={{ width: "100%", textAlign: "left", marginBottom: "30px" }}
      >
        <h3 style={{ fontSize: "16px", marginBottom: "16px" }}>Add Friend Account</h3>
        <div style={{ display: "flex", gap: "16px" }}>
          <input
            type="text"
            className="form-input"
            placeholder="Friend User ID"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
          />
          <input
            type="text"
            className="form-input"
            placeholder="Display Name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
          />
          <input
            type="text"
            className="form-input"
            placeholder="Notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
          <button
            className="btn-primary"
            style={{ width: "150px" }}
            onClick={handleAddFriend}
          >
            Add Friend
          </button>
        </div>
      </div>

      {friends.length > 0 ? (
        <div>
          {friends.map((friend) => (
            <div key={friend.user_id} className="friend-card">
              <div className="friend-details">
                <h4>{friend.display_name}</h4>
                <p>
                  User ID: {friend.user_id}{" "}
                  {friend.notes ? `• ${friend.notes}` : ""}
                </p>
              </div>
              <div style={{ display: "flex", gap: "12px" }}>
                <button
                  className="btn-secondary"
                  onClick={() => {
                    setActiveFriend(friend);
                    if (fetchFriendFavs) fetchFriendFavs(friend.user_id, 0);
                  }}
                >
                  View Favorites
                </button>
                <button
                  className="icon-btn"
                  onClick={() => removeFriend && removeFriend(friend.user_id)}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div
          style={{
            textAlign: "center",
            color: "var(--text-muted)",
            marginTop: "60px",
          }}
        >
          <Users size={48} style={{ marginBottom: "16px" }} />
          <p>You haven't added any friend user accounts yet.</p>
        </div>
      )}
    </div>
  );
}
