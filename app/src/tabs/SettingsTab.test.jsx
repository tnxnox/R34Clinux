import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { SettingsTab } from "./SettingsTab";

const mockSettings = {
  user_id: "123",
  api_key: "abc",
  website_username: "",
  website_password: "",
  download_directory: "/downloads",
  download_naming_template: "{id}",
  download_sidecar_enabled: false,
  download_use_sample: false,
  flaresolverr_enabled: false,
  flaresolverr_url: "",
  page_size: 50,
  sync_conflict_strategy: "remote_wins",
};

const mockSyncStatus = {
  is_running: false,
  debug: "",
  error: "",
};

describe("SettingsTab component", () => {
  it("renders settings sections", () => {
    render(
      <SettingsTab
        settings={mockSettings}
        setSettings={vi.fn()}
        syncStatus={mockSyncStatus}
        saveSettings={vi.fn()}
      />
    );

    expect(screen.getByText("Rule34 API Credentials")).toBeInTheDocument();
    expect(screen.getByText("Rule34 Website Login (for Sync)")).toBeInTheDocument();
    expect(screen.getByText("Sync Conflict Strategy")).toBeInTheDocument();
    expect(screen.getByText("Download Preferences")).toBeInTheDocument();
  });

  it("renders and manages blacklist tags when callbacks are provided", () => {
    const onAddBlacklistTag = vi.fn();
    const onRemoveBlacklistTag = vi.fn();

    render(
      <SettingsTab
        settings={mockSettings}
        setSettings={vi.fn()}
        syncStatus={mockSyncStatus}
        saveSettings={vi.fn()}
        blacklistedTags={["gore", "explicit"]}
        onAddBlacklistTag={onAddBlacklistTag}
        onRemoveBlacklistTag={onRemoveBlacklistTag}
      />
    );

    expect(screen.getByText("Tag Blacklist")).toBeInTheDocument();
    expect(screen.getByText("gore")).toBeInTheDocument();
    expect(screen.getByText("explicit")).toBeInTheDocument();

    // Test adding a tag
    const input = screen.getByPlaceholderText("e.g. gore, scat...");
    fireEvent.change(input, { target: { value: "scat" } });
    
    // The settings tab has standard form submit or a button named Add
    const addButton = screen.getByRole("button", { name: "Add" });
    fireEvent.click(addButton);

    expect(onAddBlacklistTag).toHaveBeenCalledWith("scat");
  });

  it("updates settings when changing conflict strategy", () => {
    const setSettings = vi.fn();
    render(
      <SettingsTab
        settings={mockSettings}
        setSettings={setSettings}
        syncStatus={mockSyncStatus}
        saveSettings={vi.fn()}
      />
    );

    const select = screen.getByLabelText("Conflict Resolution Strategy");
    fireEvent.change(select, { target: { value: "merge" } });
    expect(setSettings).toHaveBeenCalled();
  });
});
