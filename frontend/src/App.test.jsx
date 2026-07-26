// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import App, { ArchitectureCanvas, PresetCard } from "./App";
import { presets } from "./presets";

afterEach(cleanup);

describe("Trinity Reborn demo launchpad", () => {
  test("presents the current-affairs preset topics", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: /turn a live signal/i })).toBeVisible();
    expect(screen.getByRole("heading", { level: 3, name: "NEET leak protests" })).toBeVisible();
    expect(screen.getByRole("heading", { level: 3, name: "FIFA World Cup corruption" })).toBeVisible();
    expect(screen.getByRole("heading", { level: 3, name: "Europe forest fires" })).toBeVisible();
  });

  test("selects and launches a briefing card", () => {
    const onSelect = vi.fn();
    const onLaunch = vi.fn();
    render(<PresetCard preset={presets[0]} selected={false} onSelect={onSelect} onLaunch={onLaunch} disabled={false} />);

    fireEvent.click(screen.getByRole("button", { name: /preview/i }));
    fireEvent.click(screen.getByRole("button", { name: /launch/i }));

    expect(onSelect).toHaveBeenCalledWith("neet-leak");
    expect(onLaunch).toHaveBeenCalledWith(presets[0]);
  });

  test("shows the downloadable architecture view", () => {
    render(<ArchitectureCanvas />);

    expect(screen.getByRole("img", { name: /trinity reborn architecture/i })).toBeVisible();
    expect(screen.getByText("World Bible")).toBeVisible();
    expect(screen.getByText("Episodes")).toBeVisible();
  });
});
