import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { FavoritesTab } from "./FavoritesTab";

describe("FavoritesTab component", () => {
  it("renders collection select and favorites list", () => {
    const triggerSync = vi.fn();
    const mockPosts = [
      { id: 1, tags: [], preview_url: "url1" },
    ];
    render(
      <FavoritesTab
        selectedCollection=""
        setSelectedCollection={vi.fn()}
        collections={["Folder A"]}
        favorites={mockPosts}
        syncStatus={{ is_running: false }}
        triggerSync={triggerSync}
        toggleFavorite={vi.fn()}
        triggerDownload={vi.fn()}
        setSelectedPost={vi.fn()}
      />
    );

    expect(screen.getByRole("combobox")).toBeInTheDocument();
    expect(screen.getByText("Folder A")).toBeInTheDocument();
    expect(screen.getByText("Score: 0")).toBeInTheDocument();

    const syncButton = screen.getByRole("button", { name: /Sync Account/ });
    expect(syncButton).toBeInTheDocument();
    
    fireEvent.click(syncButton);
    expect(triggerSync).toHaveBeenCalled();
  });

  it("disables sync button when synchronization is in progress", () => {
    render(
      <FavoritesTab
        selectedCollection=""
        setSelectedCollection={vi.fn()}
        collections={[]}
        favorites={[]}
        syncStatus={{ is_running: true }}
        triggerSync={vi.fn()}
        toggleFavorite={vi.fn()}
        triggerDownload={vi.fn()}
        setSelectedPost={vi.fn()}
      />
    );

    const syncButton = screen.getByRole("button", { name: /Syncing.../ });
    expect(syncButton).toBeDisabled();
  });
});
