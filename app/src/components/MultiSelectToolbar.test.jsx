import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MultiSelectToolbar } from "./MultiSelectToolbar";

const mockPosts = [
  { id: 1, tags: [] },
  { id: 2, tags: [] },
];

describe("MultiSelectToolbar component", () => {
  it("renders selected items count and action buttons", () => {
    const onClear = vi.fn();
    const onBulkFavorite = vi.fn();
    const onBulkDownload = vi.fn();
    const onBulkAssignCollection = vi.fn();

    render(
      <MultiSelectToolbar
        selectedPosts={mockPosts}
        activeTab="search"
        collections={["favs"]}
        onClear={onClear}
        onBulkFavorite={onBulkFavorite}
        onBulkDownload={onBulkDownload}
        onBulkAssignCollection={onBulkAssignCollection}
      />
    );

    expect(screen.getByText("2 items selected")).toBeInTheDocument();
    expect(screen.getByText("Favorite")).toBeInTheDocument();
    expect(screen.getByText("Download")).toBeInTheDocument();
  });

  it("calls buttons and triggers callbacks", () => {
    const onClear = vi.fn();
    const onBulkFavorite = vi.fn();
    const onBulkDownload = vi.fn();
    const onBulkAssignCollection = vi.fn();

    render(
      <MultiSelectToolbar
        selectedPosts={mockPosts}
        activeTab="search"
        collections={["favs"]}
        onClear={onClear}
        onBulkFavorite={onBulkFavorite}
        onBulkDownload={onBulkDownload}
        onBulkAssignCollection={onBulkAssignCollection}
      />
    );

    fireEvent.click(screen.getByText("Favorite"));
    expect(onBulkFavorite).toHaveBeenCalledWith(mockPosts, true);

    fireEvent.click(screen.getByText("Download"));
    expect(onBulkDownload).toHaveBeenCalledWith(mockPosts);
  });
});
