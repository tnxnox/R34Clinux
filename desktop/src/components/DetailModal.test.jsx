import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { DetailModal } from "./DetailModal";

const mockPost = {
  id: 12345,
  preview_url: "http://example.com/preview.jpg",
  file_url: "http://example.com/file.jpg",
  rating: "safe",
  score: 10,
  dimensions: "1920x1080",
  created_at: "1620000000",
  tags: ["solo", "safe"],
};

describe("DetailModal component", () => {
  it("renders detail modal fields correctly", () => {
    const onClose = vi.fn();
    const onFavoriteToggle = vi.fn();
    const onDownload = vi.fn();
    const onAssignCollection = vi.fn();
    const onTagClick = vi.fn();

    render(
      <DetailModal
        post={mockPost}
        collections={["test-collection"]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );

    expect(screen.getByText("Post #12345")).toBeInTheDocument();
    expect(screen.getByText("1920x1080")).toBeInTheDocument();
    expect(screen.getByText("solo")).toBeInTheDocument();
  });

  it("calls buttons and triggers callbacks", () => {
    const onClose = vi.fn();
    const onFavoriteToggle = vi.fn();
    const onDownload = vi.fn();
    const onAssignCollection = vi.fn();
    const onTagClick = vi.fn();

    render(
      <DetailModal
        post={mockPost}
        collections={["test-collection"]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );

    // Click tag "solo"
    fireEvent.click(screen.getByText("solo"));
    expect(onTagClick).toHaveBeenCalledWith("solo");

    // Click favorite button
    fireEvent.click(screen.getByText("Favorite"));
    expect(onFavoriteToggle).toHaveBeenCalledWith(mockPost);

    // Click download button
    fireEvent.click(screen.getByText("Download"));
    expect(onDownload).toHaveBeenCalledWith(mockPost);
  });
});
