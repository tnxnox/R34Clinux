import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { FriendsTab } from "./FriendsTab";

describe("FriendsTab component", () => {
  const mockFriends = [
    { user_id: "111", display_name: "Friend One", notes: "Note One" },
    { user_id: "222", display_name: "Friend Two", notes: "Note Two" },
  ];

  const mockFavorites = [
    {
      id: 12345,
      tags: ["solo"],
      rating: "s",
      score: 10,
      md5: "abc",
      preview_url: "",
      sample_url: "",
      file_url: "",
      created_at: "",
    },
  ];

  it("renders empty dashboard state", () => {
    render(
      <FriendsTab
        activeFriend={null}
        setActiveFriend={vi.fn()}
        friendUserId=""
        setFriendUserId={vi.fn()}
        friendDisplayName=""
        setFriendDisplayName={vi.fn()}
        friendNotes=""
        setFriendNotes={vi.fn()}
        addFriend={vi.fn()}
        friends={[]}
        removeFriend={vi.fn()}
        loadingFriendFavs={false}
        friendFavorites={[]}
        setFriendFavorites={vi.fn()}
        friendPage={0}
        fetchFriendFavs={vi.fn()}
        favorites={[]}
        toggleFavorite={vi.fn()}
        setSelectedPost={vi.fn()}
      />
    );

    expect(
      screen.getByText("You haven't added any friend user accounts yet.")
    ).toBeInTheDocument();
  });

  it("renders friends list on dashboard", () => {
    render(
      <FriendsTab
        activeFriend={null}
        setActiveFriend={vi.fn()}
        friendUserId=""
        setFriendUserId={vi.fn()}
        friendDisplayName=""
        setFriendDisplayName={vi.fn()}
        friendNotes=""
        setFriendNotes={vi.fn()}
        addFriend={vi.fn()}
        friends={mockFriends}
        removeFriend={vi.fn()}
        loadingFriendFavs={false}
        friendFavorites={[]}
        setFriendFavorites={vi.fn()}
        friendPage={0}
        fetchFriendFavs={vi.fn()}
        favorites={[]}
        toggleFavorite={vi.fn()}
        setSelectedPost={vi.fn()}
      />
    );

    expect(screen.getByText("Friend One")).toBeInTheDocument();
    expect(screen.getByText("User ID: 111 • Note One")).toBeInTheDocument();
    expect(screen.getByText("Friend Two")).toBeInTheDocument();
  });

  it("manages form inputs and triggers addFriend callback", () => {
    const setFriendUserId = vi.fn();
    const setFriendDisplayName = vi.fn();
    const setFriendNotes = vi.fn();
    const addFriend = vi.fn();

    render(
      <FriendsTab
        activeFriend={null}
        setActiveFriend={vi.fn()}
        friendUserId="123"
        setFriendUserId={setFriendUserId}
        friendDisplayName="Test Name"
        setFriendDisplayName={setFriendDisplayName}
        friendNotes="Test Note"
        setFriendNotes={setFriendNotes}
        addFriend={addFriend}
        friends={[]}
        removeFriend={vi.fn()}
        loadingFriendFavs={false}
        friendFavorites={[]}
        setFriendFavorites={vi.fn()}
        friendPage={0}
        fetchFriendFavs={vi.fn()}
        favorites={[]}
        toggleFavorite={vi.fn()}
        setSelectedPost={vi.fn()}
      />
    );

    // Assert values rendered in inputs
    expect(screen.getByDisplayValue("123")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Test Name")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Test Note")).toBeInTheDocument();

    // Trigger typing
    fireEvent.change(screen.getByPlaceholderText("Friend User ID"), {
      target: { value: "1234" },
    });
    expect(setFriendUserId).toHaveBeenCalled();

    // Click Add Friend button
    fireEvent.click(screen.getByRole("button", { name: "Add Friend" }));
    expect(addFriend).toHaveBeenCalled();
  });

  it("triggers removeFriend callback when trash icon clicked", () => {
    const removeFriend = vi.fn();

    render(
      <FriendsTab
        activeFriend={null}
        setActiveFriend={vi.fn()}
        friendUserId=""
        setFriendUserId={vi.fn()}
        friendDisplayName=""
        setFriendDisplayName={vi.fn()}
        friendNotes=""
        setFriendNotes={vi.fn()}
        addFriend={vi.fn()}
        friends={mockFriends}
        removeFriend={removeFriend}
        loadingFriendFavs={false}
        friendFavorites={[]}
        setFriendFavorites={vi.fn()}
        friendPage={0}
        fetchFriendFavs={vi.fn()}
        favorites={[]}
        toggleFavorite={vi.fn()}
        setSelectedPost={vi.fn()}
      />
    );

    // Click remove (trash button) on the first friend card
    // The trash button is the second button on each friend card row
    const deleteButtons = screen.getAllByRole("button");
    const removeBtn = deleteButtons.find((btn) => btn.className === "icon-btn");
    expect(removeBtn).toBeDefined();

    fireEvent.click(removeBtn);
    expect(removeFriend).toHaveBeenCalledWith("111");
  });

  it("switches views when activeFriend is set and shows loader", () => {
    render(
      <FriendsTab
        activeFriend={mockFriends[0]}
        setActiveFriend={vi.fn()}
        friendUserId=""
        setFriendUserId={vi.fn()}
        friendDisplayName=""
        setFriendDisplayName={vi.fn()}
        friendNotes=""
        setFriendNotes={vi.fn()}
        addFriend={vi.fn()}
        friends={mockFriends}
        removeFriend={vi.fn()}
        loadingFriendFavs={true}
        friendFavorites={[]}
        setFriendFavorites={vi.fn()}
        friendPage={0}
        fetchFriendFavs={vi.fn()}
        favorites={[]}
        toggleFavorite={vi.fn()}
        setSelectedPost={vi.fn()}
      />
    );

    expect(screen.getByText("← Back to Friends")).toBeInTheDocument();
    expect(
      screen.getByText("Scraping public favorites page (using FlareSolverr if enabled)...")
    ).toBeInTheDocument();
  });

  it("renders friend favorites grid and paginates", () => {
    const fetchFriendFavs = vi.fn();
    const setActiveFriend = vi.fn();
    const setFriendFavorites = vi.fn();

    render(
      <FriendsTab
        activeFriend={mockFriends[0]}
        setActiveFriend={setActiveFriend}
        friendUserId=""
        setFriendUserId={vi.fn()}
        friendDisplayName=""
        setFriendDisplayName={vi.fn()}
        friendNotes=""
        setFriendNotes={vi.fn()}
        addFriend={vi.fn()}
        friends={mockFriends}
        removeFriend={vi.fn()}
        loadingFriendFavs={false}
        friendFavorites={mockFavorites}
        setFriendFavorites={setFriendFavorites}
        friendPage={1}
        fetchFriendFavs={fetchFriendFavs}
        favorites={[]}
        toggleFavorite={vi.fn()}
        setSelectedPost={vi.fn()}
      />
    );

    // Displays the post card
    expect(screen.getByText("ID: 12345")).toBeInTheDocument();

    // Displays pagination
    expect(screen.getByText("Page 2")).toBeInTheDocument();

    // Click Previous
    const prevBtn = screen.getByRole("button", { name: /previous/i });
    fireEvent.click(prevBtn);
    expect(fetchFriendFavs).toHaveBeenCalledWith("111", 0);

    // Click Next
    const nextBtn = screen.getByRole("button", { name: /next/i });
    fireEvent.click(nextBtn);
    expect(fetchFriendFavs).toHaveBeenCalledWith("111", 2);

    // Click Back
    const backBtn = screen.getByRole("button", { name: /back to friends/i });
    fireEvent.click(backBtn);
    expect(setActiveFriend).toHaveBeenCalledWith(null);
    expect(setFriendFavorites).toHaveBeenCalledWith([]);
  });
});
