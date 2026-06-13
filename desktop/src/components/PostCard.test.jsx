import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { PostCard } from "./PostCard";

const mockPost = {
  id: 12345,
  preview_url: "http://example.com/preview.jpg",
  file_url: "http://example.com/file.jpg",
  rating: "safe",
  score: 10,
};

describe("PostCard component", () => {
  it("renders post details correctly", () => {
    const onCardClick = vi.fn();
    const onFavoriteToggle = vi.fn();
    const onDownload = vi.fn();

    render(
      <PostCard
        post={mockPost}
        isFavorite={false}
        onCardClick={onCardClick}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
      />
    );

    expect(screen.getByText("Score: 10")).toBeInTheDocument();
    expect(screen.getByText("safe")).toBeInTheDocument();
    expect(screen.getByAltText("media preview")).toHaveAttribute(
      "src",
      "http://example.com/preview.jpg"
    );
  });

  it("calls callback handlers", () => {
    const onCardClick = vi.fn();
    const onFavoriteToggle = vi.fn();
    const onDownload = vi.fn();

    render(
      <PostCard
        post={mockPost}
        isFavorite={true}
        onCardClick={onCardClick}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
      />
    );

    // The whole card is clickable. Let's find the card wrapper by clicking on the image first,
    // which triggers onCardClick via bubbling up.
    fireEvent.click(screen.getByAltText("media preview"));
    expect(onCardClick).toHaveBeenCalledWith(mockPost);

    // Find the buttons (favorite and download)
    const buttons = screen.getAllByRole("button");
    
    fireEvent.click(buttons[0]);
    expect(onFavoriteToggle).toHaveBeenCalledWith(mockPost);

    fireEvent.click(buttons[1]);
    expect(onDownload).toHaveBeenCalledWith(mockPost);
  });
});
