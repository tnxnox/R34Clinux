import React from "react";
import {
  Search as SearchIcon,
  Heart,
  Folder,
  Users,
  Settings as SettingsIcon,
} from "lucide-react";
import "./Sidebar.css";

export function Sidebar({ activeTab, setActiveTab, setActiveFriend }) {
  const handleTabClick = (tab) => {
    setActiveTab(tab);
    if (tab !== "friends") {
      setActiveFriend(null);
    }
  };

  return (
    <aside className="sidebar">
      <div className="logo-container">
        <div className="logo-icon">R</div>
        <span className="logo-text">R34 Client</span>
      </div>

      <nav className="nav-links">
        <div
          className={`nav-item ${activeTab === "search" ? "active" : ""}`}
          onClick={() => handleTabClick("search")}
        >
          <SearchIcon />
          Search Gallery
        </div>
        <div
          className={`nav-item ${activeTab === "favorites" ? "active" : ""}`}
          onClick={() => handleTabClick("favorites")}
        >
          <Heart />
          Favorites
        </div>
        <div
          className={`nav-item ${activeTab === "collections" ? "active" : ""}`}
          onClick={() => handleTabClick("collections")}
        >
          <Folder />
          Collections
        </div>
        <div
          className={`nav-item ${activeTab === "friends" ? "active" : ""}`}
          onClick={() => handleTabClick("friends")}
        >
          <Users />
          Friends
        </div>
        <div
          className={`nav-item ${activeTab === "settings" ? "active" : ""}`}
          onClick={() => handleTabClick("settings")}
        >
          <SettingsIcon />
          Settings
        </div>
      </nav>
    </aside>
  );
}
