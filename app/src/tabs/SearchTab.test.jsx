import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { SearchTab } from "./SearchTab";

describe("SearchTab component", () => {
  it("renders search bar and input", () => {
    const handleSearch = vi.fn();
    render(
      <SearchTab
        searchQuery=""
        setSearchQuery={vi.fn()}
        suggestions={[]}
        searchResults={[]}
        currentPage={0}
        hasMore={false}
        loading={false}
        favorites={[]}
        handleSearch={handleSearch}
        toggleFavorite={vi.fn()}
        triggerDownload={vi.fn()}
        setSelectedPost={vi.fn()}
        handleSuggestionClick={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText(/Search tags/);
    expect(input).toBeInTheDocument();
    
    const searchButton = screen.getByRole("button", { name: "Search" });
    expect(searchButton).toBeInTheDocument();
    
    fireEvent.click(searchButton);
    expect(handleSearch).toHaveBeenCalledWith(0);
  });

  it("renders results and pagination", () => {
    const handleSearch = vi.fn();
    const mockPosts = [
      { id: 1, tags: [], preview_url: "url1" },
    ];
    render(
      <SearchTab
        searchQuery=""
        setSearchQuery={vi.fn()}
        suggestions={[]}
        searchResults={mockPosts}
        currentPage={0}
        hasMore={true}
        loading={false}
        favorites={[]}
        handleSearch={handleSearch}
        toggleFavorite={vi.fn()}
        triggerDownload={vi.fn()}
        setSelectedPost={vi.fn()}
        handleSuggestionClick={vi.fn()}
      />
    );

    expect(screen.getByText("Score: 0")).toBeInTheDocument();
    
    const nextButton = screen.getByRole("button", { name: /Next/ });
    expect(nextButton).toBeInTheDocument();
    
    fireEvent.click(nextButton);
    expect(handleSearch).toHaveBeenCalledWith(1);
  });
});
