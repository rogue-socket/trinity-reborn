// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { GraphView, ResolutionDecisionList } from "./App";
import { demoScenario } from "./demo";


describe("operator dashboard acceptance", () => {
  test("replays the committed real-topic fixtures", () => {
    expect(demoScenario.topic.topic_key).toBe("uk-general-election-2024");
    expect(demoScenario.deltas.map((delta) => delta.package_id)).toEqual([
      "11111111-1111-4111-8111-111111111111",
      "22222222-2222-4222-8222-222222222222",
      "33333333-3333-4333-8333-333333333333",
    ]);
  });

  test("renders connected possible matches with distinct graph styling", () => {
    const { container } = render(
      <GraphView
        nodes={[
          { entity_id: "entity-a", label: "Alpha", type: "organization", status: "active" },
          { entity_id: "entity-b", label: "Beta", type: "organization", status: "active" },
        ]}
        relationships={[
          {
            relationship_id: "relationship-1",
            subject: { type: "entity", id: "entity-a" },
            object: { type: "entity", id: "entity-b" },
            type: "POSSIBLY_SAME_AS",
            status: "possible_match",
          },
        ]}
        onInspect={vi.fn()}
      />,
    );

    expect(screen.getByRole("img", { name: "Connected canonical knowledge graph" })).toBeVisible();
    expect(container.querySelector(".graph-edge.possible_match line")).toBeInTheDocument();
  });

  test("shows decision rationale, signals, and processing versions", () => {
    render(
      <ResolutionDecisionList
        decisions={[
          {
            decision_id: "decision-1",
            incoming_type: "entity",
            incoming_id: "ent-1",
            outcome: "RESOLVE_TO_EXISTING",
            rationale: "Normalized alias matched.",
            signals: { candidates: [{ score: 1 }] },
            processing_version: "kg-pipeline-0.2",
            ontology_version: "kg-ontology-0.2",
          },
        ]}
      />,
    );

    expect(screen.getByText("Normalized alias matched.")).toBeVisible();
    expect(screen.getByText(/kg-pipeline-0.2/)).toBeVisible();
    expect(screen.getByText(/"score":1/)).toBeVisible();
  });
});
