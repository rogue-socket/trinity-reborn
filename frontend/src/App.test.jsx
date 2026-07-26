// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import App, { ArchitectureCanvas, AudioDeck, DemoPage, KnowledgeGraphCanvas, PresetCard } from "./App";
import { buildPresetSeed, presets } from "./presets";

afterEach(cleanup);

describe("Echoes demo launchpad", () => {
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

  test("uses one stable stored-topic key per preset", () => {
    expect(buildPresetSeed(presets[0]).topic.topic_key).toBe("demo-neet-leak");
    expect(buildPresetSeed(presets[1]).topic.topic_key).toBe("demo-fifa-governance");
    expect(buildPresetSeed(presets[2]).topic.topic_key).toBe("demo-europe-fires");
  });

  test("shows the downloadable architecture view", () => {
    render(<ArchitectureCanvas />);

    expect(screen.getByRole("img", { name: /echoes architecture/i })).toBeVisible();
    expect(screen.getByText("World Bible")).toBeVisible();
    expect(screen.getByText("Episodes")).toBeVisible();
  });

  test("renders stored entities, events, claims, and links as a knowledge graph", () => {
    render(
      <KnowledgeGraphCanvas
        context={{
          entities: [{ entity_id: "entity-1", label: "Example collective", status: "active" }],
          events: [{ event_id: "event-1", title: "Example event", status: "active" }],
          claims: [{ claim_id: "claim-1", text: "Example claim", status: "disputed" }],
          relationships: [{ relationship_id: "relationship-1", subject: { id: "entity-1" }, object: { id: "event-1" }, type: "PARTICIPATED_IN", status: "active" }],
        }}
      />,
    );

    expect(screen.getByRole("img", { name: /stored topic knowledge graph/i })).toBeVisible();
    expect(screen.getByText("Example collective")).toBeVisible();
    expect(screen.getByText("Example event")).toBeVisible();
  });

  test("offers every supported narration language for a completed character perspective", () => {
    render(
      <AudioDeck
        run={{ phase: "complete", report: { characters: { "character-1": {} } } }}
        audioByCharacter={{}}
        selectedLanguages={{}}
        onSelectLanguage={vi.fn()}
        onNarrate={vi.fn()}
      />,
    );

    ["EN", "HI", "TA", "BN", "PA", "GU"].forEach((language) => {
      expect(screen.getByRole("button", { name: language })).toBeVisible();
    });
    expect(screen.getByRole("button", { name: /generate english audio/i })).toBeVisible();
  });

  test("explains the problem, solution, components, and layers on the demo page", () => {
    render(<DemoPage onLaunchpad={vi.fn()} />);

    expect(screen.getByRole("heading", { name: /stories need more than a headline/i })).toBeVisible();
    expect(screen.getByRole("heading", { name: /current events move fast/i })).toBeVisible();
    expect(screen.getByRole("heading", { name: /one factual spine/i })).toBeVisible();
    expect(screen.getByRole("heading", { name: /a small chain with/i })).toBeVisible();
    expect(screen.getByText("LAYER 1")).toBeVisible();
    expect(screen.getByText("LAYER 2")).toBeVisible();
    expect(screen.getByText("LAYER 3")).toBeVisible();
  });
});
