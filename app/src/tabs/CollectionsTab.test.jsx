import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { CollectionsTab } from "./CollectionsTab";

describe("CollectionsTab component", () => {
  const mockCollections = ["Wallpaper", "Anime", "Gamer"];

  it("renders empty collections state", () => {
    render(
      <CollectionsTab
        newCollectionName=""
        setNewCollectionName={vi.fn()}
        createCollection={vi.fn()}
        collections={[]}
        deleteCollection={vi.fn()}
      />
    );

    expect(
      screen.getByText("No collections created. Group your local favorites into folders.")
    ).toBeInTheDocument();
  });

  it("renders list of collections", () => {
    render(
      <CollectionsTab
        newCollectionName=""
        setNewCollectionName={vi.fn()}
        createCollection={vi.fn()}
        collections={mockCollections}
        deleteCollection={vi.fn()}
      />
    );

    expect(screen.getByText("Wallpaper")).toBeInTheDocument();
    expect(screen.getByText("Anime")).toBeInTheDocument();
    expect(screen.getByText("Gamer")).toBeInTheDocument();
  });

  it("manages typing in input and triggering creation", () => {
    const setNewCollectionName = vi.fn();
    const createCollection = vi.fn();

    render(
      <CollectionsTab
        newCollectionName="New Folder"
        setNewCollectionName={setNewCollectionName}
        createCollection={createCollection}
        collections={[]}
        deleteCollection={vi.fn()}
      />
    );

    // Test typing
    const input = screen.getByPlaceholderText("New collection name...");
    fireEvent.change(input, { target: { value: "New Folder Changed" } });
    expect(setNewCollectionName).toHaveBeenCalled();

    // Test clicking create
    const createButton = screen.getByRole("button", { name: "Create" });
    fireEvent.click(createButton);
    expect(createCollection).toHaveBeenCalled();
  });

  it("triggers deletion callback on item click", () => {
    const deleteCollection = vi.fn();

    render(
      <CollectionsTab
        newCollectionName=""
        setNewCollectionName={vi.fn()}
        createCollection={vi.fn()}
        collections={mockCollections}
        deleteCollection={deleteCollection}
      />
    );

    // Click delete on the first row
    const deleteButtons = screen.getAllByRole("button");
    // The first button in DOM might be "Create", the subsequent ones are trash icon-buttons on rows
    const firstDelete = deleteButtons.find((btn) => btn.className === "icon-btn");
    expect(firstDelete).toBeDefined();

    fireEvent.click(firstDelete);
    expect(deleteCollection).toHaveBeenCalledWith("Wallpaper");
  });
});
