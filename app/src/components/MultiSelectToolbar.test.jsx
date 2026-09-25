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

  it("triggers onClear when the close button is clicked", () => {
    const onClear = vi.fn();

    render(
      <MultiSelectToolbar
        selectedPosts={mockPosts}
        activeTab="search"
        collections={[]}
        onClear={onClear}
        onBulkFavorite={vi.fn()}
        onBulkDownload={vi.fn()}
        onBulkAssignCollection={vi.fn()}
      />
    );

    const closeBtn = document.querySelector(".close-btn");
    expect(closeBtn).toBeInTheDocument();
    fireEvent.click(closeBtn);
    expect(onClear).toHaveBeenCalled();
  });

  it("handles assigning posts to a selected collection", () => {
    const onBulkAssignCollection = vi.fn();

    render(
      <MultiSelectToolbar
        selectedPosts={mockPosts}
        activeTab="search"
        collections={["Wallpaper", "Gamer"]}
        onClear={vi.fn()}
        onBulkFavorite={vi.fn()}
        onBulkDownload={vi.fn()}
        onBulkAssignCollection={onBulkAssignCollection}
      />
    );

    const select = screen.getByRole("combobox");
    const assignBtn = screen.getByRole("button", { name: "Assign" });
    expect(assignBtn).toBeDisabled();

    fireEvent.change(select, { target: { value: "Wallpaper" } });
    expect(assignBtn).not.toBeDisabled();

    fireEvent.click(assignBtn);
    expect(onBulkAssignCollection).toHaveBeenCalledWith(mockPosts, "Wallpaper");
  });
});
