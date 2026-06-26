import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Sidebar } from "./Sidebar";

describe("Sidebar component", () => {
  it("renders navigation items", () => {
    const setActiveTab = vi.fn();
    const setActiveFriend = vi.fn();
    render(
      <Sidebar
        activeTab="search"
        setActiveTab={setActiveTab}
        setActiveFriend={setActiveFriend}
      />
    );

    expect(screen.getByText("Search Gallery")).toBeInTheDocument();
    expect(screen.getByText("Favorites")).toBeInTheDocument();
    expect(screen.getByText("Collections")).toBeInTheDocument();
    expect(screen.getByText("Friends")).toBeInTheDocument();
    expect(screen.getByText("Settings")).toBeInTheDocument();
  });

  it("triggers tab change on click", () => {
    const setActiveTab = vi.fn();
    const setActiveFriend = vi.fn();
    render(
      <Sidebar
        activeTab="search"
        setActiveTab={setActiveTab}
        setActiveFriend={setActiveFriend}
      />
    );

    fireEvent.click(screen.getByText("Favorites"));
    expect(setActiveTab).toHaveBeenCalledWith("favorites");
    expect(setActiveFriend).toHaveBeenCalledWith(null);
  });
});
