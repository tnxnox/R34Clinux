import "@testing-library/jest-dom";
import { vi } from "vitest";

// Mock Tauri core invoke
vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn(),
  convertFileSrc: (path) => path,
}));
