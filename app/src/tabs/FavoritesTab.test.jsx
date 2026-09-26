import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { FavoritesTab } from "./FavoritesTab";

describe("FavoritesTab component", () => {
  const samplePosts = [
    {
      id: 101,
      tags: ["solo", "blonde_hair", "blue_eyes"],
      preview_url: "preview1.jpg",
      file_url: "file1.png",
      score: 50,
      rating: "explicit",
      width: 1000,
      height: 1000,
    },
    {
      id: 102,
      tags: ["duo", "video_tag"],
      preview_url: "preview2.jpg",
      file_url: "animation.mp4",
      score: 120,
      rating: "questionable",
      width: 1920,
      height: 1080,
    },
    {
      id: 103,
      tags: ["comic", "strip_tag"],
      preview_url: "preview3.jpg",
      file_url: "strip.jpg",
      score: 10,
      rating: "explicit",
      width: 500,
      height: 2500, // height / width = 5.0 -> isLongStrip = true
    },
    {
      id: 104,
      tags: ["animated", "gif_tag"],
      preview_url: "preview4.jpg",
      file_url: "animated.gif",
      score: 85,
      rating: "explicit",
      width: 600,
      height: 600,
    },
  ];

  it("renders collection select and favorites list", () => {
    const triggerSync = vi.fn();
    render(
      <FavoritesTab
        selectedCollection=""
        setSelectedCollection={vi.fn()}
        collections={["Folder A"]}
        favorites={samplePosts.slice(0, 1)}
        syncStatus={{ is_running: false }}
        triggerSync={triggerSync}
        toggleFavorite={vi.fn()}
        triggerDownload={vi.fn()}
        setSelectedPost={vi.fn()}
      />
    );

    expect(screen.getByLabelText("Filter by collection")).toBeInTheDocument();
    expect(screen.getByText("Folder A")).toBeInTheDocument();
    expect(screen.getByText("Score: 50")).toBeInTheDocument();

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

  it("filters posts by search query and tag exclusion", () => {
    render(
      <FavoritesTab
        selectedCollection=""
        setSelectedCollection={vi.fn()}
        collections={[]}
        favorites={samplePosts}
        syncStatus={{ is_running: false }}
        triggerSync={vi.fn()}
        toggleFavorite={vi.fn()}
        triggerDownload={vi.fn()}
        setSelectedPost={vi.fn()}
      />
    );

    const searchInput = screen.getByPlaceholderText(/Search tags or post ID/);

    // Search for blonde_hair
    fireEvent.change(searchInput, { target: { value: "blonde_hair" } });
    expect(screen.getByText("Score: 50")).toBeInTheDocument();
    expect(screen.queryByText("Score: 120")).not.toBeInTheDocument();
    expect(screen.getByText("Showing 1 of 4 favorites")).toBeInTheDocument();

    // Negative tag exclusion: exclude solo
    fireEvent.change(searchInput, { target: { value: "-solo" } });
    expect(screen.queryByText("Score: 50")).not.toBeInTheDocument();
    expect(screen.getByText("Score: 120")).toBeInTheDocument();
    expect(screen.getByText("Showing 3 of 4 favorites")).toBeInTheDocument();

    // Search by Post ID
    fireEvent.change(searchInput, { target: { value: "103" } });
    expect(screen.getByText("Score: 10")).toBeInTheDocument();
    expect(screen.queryByText("Score: 50")).not.toBeInTheDocument();
  });

  it("filters posts by media type", () => {
    render(
      <FavoritesTab
        selectedCollection=""
        setSelectedCollection={vi.fn()}
        collections={[]}
        favorites={samplePosts}
        syncStatus={{ is_running: false }}
        triggerSync={vi.fn()}
        toggleFavorite={vi.fn()}
        triggerDownload={vi.fn()}
        setSelectedPost={vi.fn()}
      />
    );

    const mediaSelect = screen.getByLabelText("Filter by media type");

    // Filter to Videos Only
    fireEvent.change(mediaSelect, { target: { value: "video" } });
    expect(screen.getByText("Score: 120")).toBeInTheDocument();
    expect(screen.queryByText("Score: 50")).not.toBeInTheDocument();
    expect(screen.getByText("Showing 1 of 4 favorites")).toBeInTheDocument();

    // Filter to GIFs Only
    fireEvent.change(mediaSelect, { target: { value: "gif" } });
    expect(screen.getByText("Score: 85")).toBeInTheDocument();
    expect(screen.queryByText("Score: 120")).not.toBeInTheDocument();

    // Filter to Long Strips
    fireEvent.change(mediaSelect, { target: { value: "strip" } });
    expect(screen.getByText("Score: 10")).toBeInTheDocument();
    expect(screen.queryByText("Score: 85")).not.toBeInTheDocument();

    // Filter to Static Images Only
    fireEvent.change(mediaSelect, { target: { value: "image" } });
    expect(screen.getByText("Score: 50")).toBeInTheDocument();
    expect(screen.getByText("Score: 10")).toBeInTheDocument();
    expect(screen.queryByText("Score: 120")).not.toBeInTheDocument(); // video excluded
    expect(screen.queryByText("Score: 85")).not.toBeInTheDocument(); // gif excluded
  });

  it("filters posts by rating", () => {
    render(
      <FavoritesTab
        selectedCollection=""
        setSelectedCollection={vi.fn()}
        collections={[]}
        favorites={samplePosts}
        syncStatus={{ is_running: false }}
        triggerSync={vi.fn()}
        toggleFavorite={vi.fn()}
        triggerDownload={vi.fn()}
        setSelectedPost={vi.fn()}
      />
    );

    const ratingSelect = screen.getByLabelText("Filter by rating");

    // Filter Questionable
    fireEvent.change(ratingSelect, { target: { value: "questionable" } });
    expect(screen.getByText("Score: 120")).toBeInTheDocument();
    expect(screen.queryByText("Score: 50")).not.toBeInTheDocument();
    expect(screen.getByText("Showing 1 of 4 favorites")).toBeInTheDocument();

    // Filter Explicit
    fireEvent.change(ratingSelect, { target: { value: "explicit" } });
    expect(screen.getByText("Score: 50")).toBeInTheDocument();
    expect(screen.getByText("Score: 10")).toBeInTheDocument();
    expect(screen.getByText("Score: 85")).toBeInTheDocument();
    expect(screen.queryByText("Score: 120")).not.toBeInTheDocument();
  });

  it("sorts posts by score and ID", () => {
    render(
      <FavoritesTab
        selectedCollection=""
        setSelectedCollection={vi.fn()}
        collections={[]}
        favorites={samplePosts}
        syncStatus={{ is_running: false }}
        triggerSync={vi.fn()}
        toggleFavorite={vi.fn()}
        triggerDownload={vi.fn()}
        setSelectedPost={vi.fn()}
      />
    );

    const sortSelect = screen.getByLabelText("Sort favorites");

    // Sort by Score (Highest)
    fireEvent.change(sortSelect, { target: { value: "score-desc" } });
    const scoreElements = screen.getAllByText(/Score: \d+/);
    expect(scoreElements[0]).toHaveTextContent("Score: 120");
    expect(scoreElements[1]).toHaveTextContent("Score: 85");
    expect(scoreElements[2]).toHaveTextContent("Score: 50");
    expect(scoreElements[3]).toHaveTextContent("Score: 10");

    // Sort by Score (Lowest)
    fireEvent.change(sortSelect, { target: { value: "score-asc" } });
    const scoreElementsAsc = screen.getAllByText(/Score: \d+/);
    expect(scoreElementsAsc[0]).toHaveTextContent("Score: 10");
    expect(scoreElementsAsc[1]).toHaveTextContent("Score: 50");
  });

  it("resets filters when no posts match", () => {
    render(
      <FavoritesTab
        selectedCollection=""
        setSelectedCollection={vi.fn()}
        collections={[]}
        favorites={samplePosts}
        syncStatus={{ is_running: false }}
        triggerSync={vi.fn()}
        toggleFavorite={vi.fn()}
        triggerDownload={vi.fn()}
        setSelectedPost={vi.fn()}
      />
    );

    const searchInput = screen.getByPlaceholderText(/Search tags or post ID/);
    fireEvent.change(searchInput, { target: { value: "nonexistent_tag_xyz" } });

    expect(screen.getByText("No favorites match your active search or filters.")).toBeInTheDocument();

    const resetButton = screen.getByRole("button", { name: /Reset Filters/ });
    fireEvent.click(resetButton);

    expect(searchInput.value).toBe("");
    expect(screen.getByText("Showing 4 of 4 favorites")).toBeInTheDocument();
  });
});
