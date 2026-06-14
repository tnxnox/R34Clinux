import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeAll, afterAll } from "vitest";
import { ErrorBoundary } from "./ErrorBoundary";

const ProblematicComponent = ({ shouldThrow }) => {
  if (shouldThrow) {
    throw new Error("Test Error");
  }
  return <div>Normal Content</div>;
};

describe("ErrorBoundary Component", () => {
  // Suppress console.error during throwing tests to keep test output clean
  let originalError;
  beforeAll(() => {
    originalError = console.error;
    console.error = vi.fn();
  });

  afterAll(() => {
    console.error = originalError;
  });

  it("renders children when no error occurs", () => {
    render(
      <ErrorBoundary>
        <ProblematicComponent shouldThrow={false} />
      </ErrorBoundary>
    );

    expect(screen.getByText("Normal Content")).toBeInTheDocument();
    expect(screen.queryByText("View Crashed")).not.toBeInTheDocument();
  });

  it("catches errors and renders fallback UI", () => {
    render(
      <ErrorBoundary>
        <ProblematicComponent shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText("View Crashed")).toBeInTheDocument();
    expect(screen.getByText("Error: Test Error")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reset view/i })).toBeInTheDocument();
  });

  it("resets state when Reset View is clicked", () => {
    const onResetMock = vi.fn();
    
    // We render with shouldThrow true initially
    const { rerender } = render(
      <ErrorBoundary onReset={onResetMock}>
        <ProblematicComponent shouldThrow={true} />
      </ErrorBoundary>
    );

    expect(screen.getByText("View Crashed")).toBeInTheDocument();

    // Rerender with shouldThrow false so that when we click reset, it renders successfully
    rerender(
      <ErrorBoundary onReset={onResetMock}>
        <ProblematicComponent shouldThrow={false} />
      </ErrorBoundary>
    );

    fireEvent.click(screen.getByRole("button", { name: /reset view/i }));

    expect(onResetMock).toHaveBeenCalled();
    expect(screen.getByText("Normal Content")).toBeInTheDocument();
    expect(screen.queryByText("View Crashed")).not.toBeInTheDocument();
  });
});
