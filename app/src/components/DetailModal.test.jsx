import React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
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

  it("does not crash when collections and favorites props are omitted", () => {
    const onClose = vi.fn();
    const onFavoriteToggle = vi.fn();
    const onDownload = vi.fn();

    render(
      <DetailModal
        post={mockPost}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
      />
    );

    expect(screen.getByText("Post #12345")).toBeInTheDocument();
  });

  it("attaches a native non-passive wheel event listener that handles zoom", () => {
    render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
      />
    );

    const img = screen.getByAltText("modal media");
    expect(img).toBeInTheDocument();

    // Create and dispatch native wheel event with ctrlKey
    const wheelEvent = new WheelEvent("wheel", {
      bubbles: true,
      cancelable: true,
      ctrlKey: true,
      deltaY: -100,
    });

    const preventDefaultSpy = vi.spyOn(wheelEvent, "preventDefault");
    img.dispatchEvent(wheelEvent);

    expect(preventDefaultSpy).toHaveBeenCalled();
  });

  it("closes the modal when Escape key is pressed", () => {
    const onClose = vi.fn();
    render(
      <DetailModal
        post={mockPost}
        onClose={onClose}
      />
    );

    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  it("renders categorized tag sections and badges when tag types are resolved", async () => {
    const mockPostCategorized = {
      ...mockPost,
      tags: ["artist_tag", "char_tag", "copy_tag", "meta_tag", "general_tag"],
    };

    const { invoke } = await import("@tauri-apps/api/core");
    invoke.mockImplementation((cmd) => {
      if (cmd === "get_tags_with_types") {
        return Promise.resolve({
          artist_tag: 1,
          char_tag: 4,
          copy_tag: 3,
          meta_tag: 5,
          general_tag: 0,
        });
      }
      return Promise.resolve(null);
    });

    await act(async () => {
      render(
        <DetailModal
          post={mockPostCategorized}
          collections={[]}
          favorites={[]}
        />
      );
    });

    const artistBadge = await screen.findByText("artist_tag");
    expect(artistBadge).toBeInTheDocument();
    expect(artistBadge).toHaveClass("tag-badge", "artist");

    const charBadge = screen.getByText("char_tag");
    expect(charBadge).toHaveClass("tag-badge", "character");

    const copyBadge = screen.getByText("copy_tag");
    expect(copyBadge).toHaveClass("tag-badge", "copyright");

    const metaBadge = screen.getByText("meta_tag");
    expect(metaBadge).toHaveClass("tag-badge", "metadata");

    const generalBadge = screen.getByText("general_tag");
    expect(generalBadge).toHaveClass("tag-badge", "general");

    expect(screen.getByText("Artists")).toBeInTheDocument();
    expect(screen.getByText("Characters")).toBeInTheDocument();
    expect(screen.getByText("Copyrights")).toBeInTheDocument();
    const metadataHeaders = screen.getAllByText("Metadata");
    expect(metadataHeaders.length).toBe(2);
    expect(screen.getByText("General")).toBeInTheDocument();
  });
});

