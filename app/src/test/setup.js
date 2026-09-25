import "@testing-library/jest-dom";
import { vi } from "vitest";

// Mock Tauri core invoke
vi.mock("@tauri-apps/api/core", () => ({
  invoke: vi.fn().mockImplementation(() => Promise.resolve(null)),
  convertFileSrc: (path) => path,
}));

// Provide stubs for HTMLMediaElement methods not implemented in JSDOM
if (typeof window !== "undefined" && window.HTMLMediaElement) {
  window.HTMLMediaElement.prototype.load = () => {};
  window.HTMLMediaElement.prototype.play = () => Promise.resolve();
  window.HTMLMediaElement.prototype.pause = () => {};
}
