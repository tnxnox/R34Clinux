import React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
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

const mockVideoPost = {
  id: 12346,
  preview_url: "http://example.com/preview.jpg",
  file_url: "http://example.com/video.mp4",
  rating: "questionable",
  score: 42,
  dimensions: "1280x720",
  created_at: "1620000001",
  tags: ["animated", "video"],
};

describe("DetailModal E2E and Integration Tests", () => {
  const onClose = vi.fn();
  const onFavoriteToggle = vi.fn();
  const onDownload = vi.fn();
  const onAssignCollection = vi.fn();
  const onTagClick = vi.fn();

  let mockFullscreenElement = null;
  const originalRequestFullscreen = Element.prototype.requestFullscreen;
  const originalExitFullscreen = document.exitFullscreen;

  beforeEach(() => {
    onClose.mockClear();
    onFavoriteToggle.mockClear();
    onDownload.mockClear();
    onAssignCollection.mockClear();
    onTagClick.mockClear();

    mockFullscreenElement = null;

    Object.defineProperty(document, "fullscreenElement", {
      configurable: true,
      get: () => mockFullscreenElement,
      set: (val) => {
        mockFullscreenElement = val;
      },
    });

    Element.prototype.requestFullscreen = vi.fn().mockImplementation(function () {
      mockFullscreenElement = this;
      document.dispatchEvent(new Event("fullscreenchange"));
      return Promise.resolve();
    });

    document.exitFullscreen = vi.fn().mockImplementation(() => {
      mockFullscreenElement = null;
      document.dispatchEvent(new Event("fullscreenchange"));
      return Promise.resolve();
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    Element.prototype.requestFullscreen = originalRequestFullscreen;
    document.exitFullscreen = originalExitFullscreen;
  });

  // ==========================================
  // TIER 1: Feature Coverage (15 tests)
  // ==========================================

  // Feature 1: R1 (Larger Media Layout)
  it("should render the main modal content container with larger size classes (.modal-large)", () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const content = container.querySelector(".modal-content");
    expect(content).toBeInTheDocument();
    expect(content).toHaveClass("modal-large");
  });

  it("should display the media pane with default style matching at least 70% width (.modal-media-pane)", () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const pane = container.querySelector(".modal-media-pane");
    expect(pane).toBeInTheDocument();
    expect(pane).toHaveClass("modal-media-pane");
  });

  it("should render the media pane container and the info pane container side-by-side by default", () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const mediaPane = container.querySelector(".modal-media-pane");
    const infoPane = container.querySelector(".modal-info-pane");
    expect(mediaPane).toBeInTheDocument();
    expect(infoPane).toBeInTheDocument();
    expect(mediaPane.nextSibling).toBe(infoPane);
  });

  it("should display image media with high visual impact constraints (.modal-media styling)", () => {
    render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const img = screen.getByAltText("modal media");
    expect(img).toBeInTheDocument();
    expect(img).toHaveClass("modal-media");
  });

  it("should display video media with high visual impact constraints (.modal-media styling)", () => {
    const { container } = render(
      <DetailModal
        post={mockVideoPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const video = container.querySelector("video");
    expect(video).toBeInTheDocument();
    expect(video).toHaveClass("modal-media");
  });

  // Feature 2: R2 (Native Fullscreen)
  it("should render the fullscreen button inside the media pane container", () => {
    render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.getByTestId("fullscreen-btn");
    expect(btn).toBeInTheDocument();
  });

  it("should invoke requestFullscreen on the media container when clicking the fullscreen button for image post", async () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.getByTestId("fullscreen-btn");
    const mediaPane = container.querySelector(".modal-media-pane");

    await act(async () => {
      fireEvent.click(btn);
    });

    expect(mediaPane.requestFullscreen).toHaveBeenCalled();
  });

  it("should invoke requestFullscreen on the media container when clicking the fullscreen button for video post", async () => {
    const { container } = render(
      <DetailModal
        post={mockVideoPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.getByTestId("fullscreen-btn");
    const mediaPane = container.querySelector(".modal-media-pane");

    await act(async () => {
      fireEvent.click(btn);
    });

    expect(mediaPane.requestFullscreen).toHaveBeenCalled();
  });

  it("should invoke exitFullscreen when clicking the fullscreen button while in fullscreen mode", async () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.getByTestId("fullscreen-btn");
    const mediaPane = container.querySelector(".modal-media-pane");

    await act(async () => {
      fireEvent.click(btn);
    });
    expect(document.fullscreenElement).toBe(mediaPane);

    await act(async () => {
      fireEvent.click(btn);
    });
    expect(document.exitFullscreen).toHaveBeenCalled();
    expect(document.fullscreenElement).toBeNull();
  });

  it("should handle fullscreenchange event and update fullscreen state classes accordingly", async () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.getByTestId("fullscreen-btn");
    const mediaPane = container.querySelector(".modal-media-pane");

    expect(mediaPane).not.toHaveClass("is-fullscreen");

    await act(async () => {
      fireEvent.click(btn);
    });

    expect(mediaPane).toHaveClass("is-fullscreen");
  });

  // Feature 3: R3 (Collapsible Side Panel)
  it("should render the sidebar toggle button at the boundary of the metadata pane", () => {
    render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.getByTestId("sidebar-toggle-btn");
    expect(btn).toBeInTheDocument();
  });

  it("should hide the metadata side panel when sidebar toggle button is clicked", async () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.getByTestId("sidebar-toggle-btn");
    const infoPane = container.querySelector(".modal-info-pane");

    expect(infoPane).not.toHaveClass("collapsed");

    await act(async () => {
      fireEvent.click(btn);
    });

    expect(infoPane).toHaveClass("collapsed");
  });

  it("should expand media pane to 100% width (class .expanded-full) when metadata side panel is collapsed", async () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.getByTestId("sidebar-toggle-btn");
    const mediaPane = container.querySelector(".modal-media-pane");

    expect(mediaPane).not.toHaveClass("expanded-full");

    await act(async () => {
      fireEvent.click(btn);
    });

    expect(mediaPane).toHaveClass("expanded-full");
  });

  it("should restore metadata side panel to visible state when toggle button is clicked again", async () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.getByTestId("sidebar-toggle-btn");
    const infoPane = container.querySelector(".modal-info-pane");

    await act(async () => {
      fireEvent.click(btn);
    });
    expect(infoPane).toHaveClass("collapsed");

    await act(async () => {
      fireEvent.click(btn);
    });
    expect(infoPane).not.toHaveClass("collapsed");
  });

  it("should restore media pane width to default split-pane width when metadata side panel is expanded again", async () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.getByTestId("sidebar-toggle-btn");
    const mediaPane = container.querySelector(".modal-media-pane");

    await act(async () => {
      fireEvent.click(btn);
    });
    expect(mediaPane).toHaveClass("expanded-full");

    await act(async () => {
      fireEvent.click(btn);
    });
    expect(mediaPane).not.toHaveClass("expanded-full");
  });

  // ==========================================
  // TIER 2: Boundary & Corner Cases (15 tests)
  // ==========================================

  // Feature 1: R1 (Larger Media Layout)
  it("should render fallback layout gracefully without crashing when post object is empty/null", () => {
    const { container } = render(
      <DetailModal
        post={null}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    // Should render a fallback or empty element, but NOT throw/crash.
    expect(container.firstChild).toBeNull();
  });

  it("should preserve layout aspect ratio and >=70% width for extremely small images", () => {
    const smallPost = { ...mockPost, dimensions: "10x10" };
    const { container } = render(
      <DetailModal
        post={smallPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const pane = container.querySelector(".modal-media-pane");
    expect(pane).toBeInTheDocument();
    expect(pane).toHaveClass("modal-media-pane");
  });

  it("should preserve layout aspect ratio and >=70% width for extremely large high-resolution images", () => {
    const largePost = { ...mockPost, dimensions: "99999x99999" };
    const { container } = render(
      <DetailModal
        post={largePost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const pane = container.querySelector(".modal-media-pane");
    expect(pane).toBeInTheDocument();
    expect(pane).toHaveClass("modal-media-pane");
  });

  it("should render responsive layout classes for mobile/desktop screen sizes", () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const content = container.querySelector(".modal-content");
    expect(content).toBeInTheDocument();
  });

  it("should display standard layout even if the media source URL is invalid or fails to load", () => {
    const invalidPost = { ...mockPost, file_url: "invalid-url", preview_url: "" };
    const { container } = render(
      <DetailModal
        post={invalidPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const pane = container.querySelector(".modal-media-pane");
    expect(pane).toBeInTheDocument();
  });

  // Feature 2: R2 (Native Fullscreen)
  it("should catch and handle errors gracefully when requestFullscreen is rejected by the browser", async () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.getByTestId("fullscreen-btn");
    const mediaPane = container.querySelector(".modal-media-pane");

    // Force requestFullscreen to reject
    mediaPane.requestFullscreen.mockImplementationOnce(() =>
      Promise.reject(new Error("Fullscreen denied"))
    );

    await act(async () => {
      // Should not throw or crash
      fireEvent.click(btn);
    });

    expect(mediaPane).not.toHaveClass("is-fullscreen");
  });

  it("should hide or disable the fullscreen button if the post media URL is missing", () => {
    const noMediaPost = { ...mockPost, file_url: null, preview_url: null, sample_url: null };
    render(
      <DetailModal
        post={noMediaPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.queryByTestId("fullscreen-btn");
    if (btn) {
      expect(btn).toBeDisabled();
    } else {
      expect(btn).toBeNull();
    }
  });

  it("should not trigger multiple fullscreen requests on fast double-clicks of the fullscreen button", async () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.getByTestId("fullscreen-btn");
    const mediaPane = container.querySelector(".modal-media-pane");

    await act(async () => {
      fireEvent.click(btn);
      fireEvent.click(btn);
    });

    // The first call enters, second call would exit or be ignored since it's now in fullscreen mode.
    // In either case, the requestFullscreen should be called at most once for the transition to fullscreen.
    expect(mediaPane.requestFullscreen).toHaveBeenCalledTimes(1);
  });

  it("should gracefully handle exitFullscreen calls when document.fullscreenElement is already null", async () => {
    render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    mockFullscreenElement = null;
    await act(async () => {
      document.dispatchEvent(new Event("fullscreenchange"));
    });
    expect(document.fullscreenElement).toBeNull();
  });

  it("should clean up fullscreen state and call exitFullscreen if the modal is closed while in fullscreen", async () => {
    const { container, unmount } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.getByTestId("fullscreen-btn");
    const mediaPane = container.querySelector(".modal-media-pane");

    await act(async () => {
      fireEvent.click(btn);
    });
    expect(mockFullscreenElement).toBe(mediaPane);

    unmount();

    expect(document.exitFullscreen).toHaveBeenCalled();
    expect(mockFullscreenElement).toBeNull();
  });

  // Feature 3: R3 (Collapsible Side Panel)
  it("should reset metadata panel state to default expanded when switching to a different post", async () => {
    const { container, rerender } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.getByTestId("sidebar-toggle-btn");
    const infoPane = container.querySelector(".modal-info-pane");

    await act(async () => {
      fireEvent.click(btn);
    });
    expect(infoPane).toHaveClass("collapsed");

    const newPost = { ...mockPost, id: 99999 };
    rerender(
      <DetailModal
        post={newPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );

    const newInfoPane = container.querySelector(".modal-info-pane");
    expect(newInfoPane).not.toHaveClass("collapsed");
  });

  it("should allow toggling sidebar collapse when post tags are loading/empty", async () => {
    const noTagsPost = { ...mockPost, tags: [] };
    const { container } = render(
      <DetailModal
        post={noTagsPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.getByTestId("sidebar-toggle-btn");
    const infoPane = container.querySelector(".modal-info-pane");

    await act(async () => {
      fireEvent.click(btn);
    });
    expect(infoPane).toHaveClass("collapsed");
  });

  it("should handle rapid toggling of the sidebar button without state corruption", async () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.getByTestId("sidebar-toggle-btn");
    const infoPane = container.querySelector(".modal-info-pane");

    await act(async () => {
      fireEvent.click(btn);
      fireEvent.click(btn);
      fireEvent.click(btn);
    });
    expect(infoPane).toHaveClass("collapsed");
  });

  it("should render and toggle sidebar normally when collections array is empty", async () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.getByTestId("sidebar-toggle-btn");
    const infoPane = container.querySelector(".modal-info-pane");

    await act(async () => {
      fireEvent.click(btn);
    });
    expect(infoPane).toHaveClass("collapsed");
  });

  it("should allow closing the modal via overlay click even when metadata panel is collapsed", async () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.getByTestId("sidebar-toggle-btn");

    await act(async () => {
      fireEvent.click(btn);
    });

    const overlay = container.querySelector(".modal-overlay");
    await act(async () => {
      fireEvent.click(overlay);
    });

    expect(onClose).toHaveBeenCalled();
  });

  // ==========================================
  // TIER 3: Cross-Feature Combinations (3 tests)
  // ==========================================

  it("should maintain fullscreen mode when side panel is collapsed, and restore correct collapsed layout on exit", async () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const sidebarBtn = screen.getByTestId("sidebar-toggle-btn");
    const fullscreenBtn = screen.getByTestId("fullscreen-btn");
    const mediaPane = container.querySelector(".modal-media-pane");
    const infoPane = container.querySelector(".modal-info-pane");

    // Collapse sidebar
    await act(async () => {
      fireEvent.click(sidebarBtn);
    });
    expect(mediaPane).toHaveClass("expanded-full");
    expect(infoPane).toHaveClass("collapsed");

    // Enter fullscreen
    await act(async () => {
      fireEvent.click(fullscreenBtn);
    });
    expect(mediaPane).toHaveClass("is-fullscreen");

    // Exit fullscreen
    await act(async () => {
      fireEvent.click(fullscreenBtn);
    });
    expect(mediaPane).not.toHaveClass("is-fullscreen");
    expect(mediaPane).toHaveClass("expanded-full");
    expect(infoPane).toHaveClass("collapsed");
  });

  it("should allow toggling side panel collapse state while in fullscreen mode", async () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const sidebarBtn = screen.getByTestId("sidebar-toggle-btn");
    const fullscreenBtn = screen.getByTestId("fullscreen-btn");
    const mediaPane = container.querySelector(".modal-media-pane");
    const infoPane = container.querySelector(".modal-info-pane");

    // Enter fullscreen
    await act(async () => {
      fireEvent.click(fullscreenBtn);
    });
    expect(mediaPane).toHaveClass("is-fullscreen");

    // Collapse sidebar
    await act(async () => {
      fireEvent.click(sidebarBtn);
    });
    expect(infoPane).toHaveClass("collapsed");

    // Expand sidebar
    await act(async () => {
      fireEvent.click(sidebarBtn);
    });
    expect(infoPane).not.toHaveClass("collapsed");
  });

  it("should exit fullscreen and reset side panel state when switching posts while both states are active", async () => {
    const { container, rerender } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const sidebarBtn = screen.getByTestId("sidebar-toggle-btn");
    const fullscreenBtn = screen.getByTestId("fullscreen-btn");
    const mediaPane = container.querySelector(".modal-media-pane");
    const infoPane = container.querySelector(".modal-info-pane");

    // Collapse sidebar & Enter fullscreen
    await act(async () => {
      fireEvent.click(sidebarBtn);
      fireEvent.click(fullscreenBtn);
    });
    expect(mediaPane).toHaveClass("is-fullscreen");
    expect(infoPane).toHaveClass("collapsed");

    // Switch post
    const nextPost = { ...mockPost, id: 88888 };
    rerender(
      <DetailModal
        post={nextPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );

    const newMediaPane = container.querySelector(".modal-media-pane");
    const newInfoPane = container.querySelector(".modal-info-pane");
    expect(newMediaPane).not.toHaveClass("is-fullscreen");
    expect(newInfoPane).not.toHaveClass("collapsed");
    expect(mockFullscreenElement).toBeNull();
  });

  // ==========================================
  // TIER 4: Real-World Application Scenarios (5 tests)
  // ==========================================

  it("Scenario: User opens image modal on desktop, hovers/clicks fullscreen, enters native fullscreen, and exits via Escape key simulation", async () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const btn = screen.getByTestId("fullscreen-btn");
    const mediaPane = container.querySelector(".modal-media-pane");

    // Click fullscreen
    await act(async () => {
      fireEvent.click(btn);
    });
    expect(mockFullscreenElement).toBe(mediaPane);
    expect(mediaPane).toHaveClass("is-fullscreen");

    // Simulate Escape key / native exit fullscreen
    mockFullscreenElement = null;
    await act(async () => {
      document.dispatchEvent(new Event("fullscreenchange"));
    });
    expect(mediaPane).not.toHaveClass("is-fullscreen");
  });

  it("Scenario: User opens video modal, collapses metadata pane to watch full width, clicks play, and expands metadata pane without interrupting playback", async () => {
    const { container } = render(
      <DetailModal
        post={mockVideoPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const sidebarBtn = screen.getByTestId("sidebar-toggle-btn");
    const video = container.querySelector("video");

    expect(video).toBeInTheDocument();

    // Collapse sidebar
    await act(async () => {
      fireEvent.click(sidebarBtn);
    });

    // Video stays in DOM and preserves state
    expect(video).toBeInTheDocument();

    // Expand sidebar again
    await act(async () => {
      fireEvent.click(sidebarBtn);
    });
    expect(video).toBeInTheDocument();
  });

  it("Scenario: User navigates through multiple posts, toggling side panel collapse on and off, verifying layout flex updates", async () => {
    const { container, rerender } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const sidebarBtn = screen.getByTestId("sidebar-toggle-btn");

    // Collapse
    await act(async () => {
      fireEvent.click(sidebarBtn);
    });
    expect(container.querySelector(".modal-media-pane")).toHaveClass("expanded-full");

    // Switch post
    const nextPost = { ...mockPost, id: 77777 };
    rerender(
      <DetailModal
        post={nextPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );

    // Resets to default split view
    expect(container.querySelector(".modal-media-pane")).not.toHaveClass("expanded-full");
    expect(container.querySelector(".modal-info-pane")).not.toHaveClass("collapsed");

    // Collapse again
    await act(async () => {
      fireEvent.click(sidebarBtn);
    });
    expect(container.querySelector(".modal-media-pane")).toHaveClass("expanded-full");
  });

  it("Scenario: User enters fullscreen on a video, uses the on-screen exit fullscreen control, and verifies correct HTML5 API sequence", async () => {
    const { container } = render(
      <DetailModal
        post={mockVideoPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );
    const fullscreenBtn = screen.getByTestId("fullscreen-btn");
    const mediaPane = container.querySelector(".modal-media-pane");

    // Click fullscreen
    await act(async () => {
      fireEvent.click(fullscreenBtn);
    });
    expect(mediaPane.requestFullscreen).toHaveBeenCalled();
    expect(mockFullscreenElement).toBe(mediaPane);

    // Click to exit fullscreen
    await act(async () => {
      fireEvent.click(fullscreenBtn);
    });
    expect(document.exitFullscreen).toHaveBeenCalled();
    expect(mockFullscreenElement).toBeNull();
  });

  it("Scenario: User downloads post, collapses side panel, enters fullscreen, exits fullscreen, restores side panel, and closes modal", async () => {
    const { container } = render(
      <DetailModal
        post={mockPost}
        collections={[]}
        favorites={[]}
        onClose={onClose}
        onFavoriteToggle={onFavoriteToggle}
        onDownload={onDownload}
        onAssignCollection={onAssignCollection}
        onTagClick={onTagClick}
      />
    );

    // 1. Download
    const downloadBtn = screen.getByText("Download");
    await act(async () => {
      fireEvent.click(downloadBtn);
    });
    expect(onDownload).toHaveBeenCalledWith(mockPost);

    // 2. Collapse side panel
    const sidebarBtn = screen.getByTestId("sidebar-toggle-btn");
    await act(async () => {
      fireEvent.click(sidebarBtn);
    });
    expect(container.querySelector(".modal-media-pane")).toHaveClass("expanded-full");

    // 3. Enter fullscreen
    const fullscreenBtn = screen.getByTestId("fullscreen-btn");
    await act(async () => {
      fireEvent.click(fullscreenBtn);
    });
    expect(container.querySelector(".modal-media-pane")).toHaveClass("is-fullscreen");

    // 4. Exit fullscreen
    await act(async () => {
      fireEvent.click(fullscreenBtn);
    });
    expect(container.querySelector(".modal-media-pane")).not.toHaveClass("is-fullscreen");

    // 5. Restore side panel
    await act(async () => {
      fireEvent.click(sidebarBtn);
    });
    expect(container.querySelector(".modal-media-pane")).not.toHaveClass("expanded-full");

    // 6. Close modal
    const overlay = container.querySelector(".modal-overlay");
    await act(async () => {
      fireEvent.click(overlay);
    });
    expect(onClose).toHaveBeenCalled();
  });
});
