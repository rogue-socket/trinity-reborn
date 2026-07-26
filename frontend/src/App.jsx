import React, { useMemo, useState } from "react";
import { buildPresetSeed, presets } from "./presets";

const apiUrl = import.meta.env.VITE_API_URL || "/api";
const orchestratorUrl = import.meta.env.VITE_ORCHESTRATOR_URL || "/orchestrator";

const stages = [
  ["01", "Research package"],
  ["02", "Knowledge graph"],
  ["03", "World bible"],
  ["04", "Story episodes"],
  ["05", "Translations"],
];

async function request(baseUrl, path, body) {
  const response = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
  return response.json();
}

export function PresetCard({ preset, selected, onSelect, onLaunch, disabled }) {
  return (
    <article className={`topic-card ${preset.accent} ${selected ? "selected" : ""}`}>
      <div className="topic-card-topline">
        <span>#{preset.id.replaceAll("-", "_")}</span>
        <span className="ready-chip">READY TO SEED</span>
      </div>
      <h3>{preset.title}</h3>
      <p>{preset.summary}</p>
      <div className="topic-card-footer">
        <button className="text-button" type="button" onClick={() => onSelect(preset.id)}>
          {selected ? "Selected" : "Preview"} <span aria-hidden="true">↗</span>
        </button>
        <button className="launch-button" type="button" onClick={() => onLaunch(preset)} disabled={disabled}>
          Launch <span aria-hidden="true">→</span>
        </button>
      </div>
    </article>
  );
}

function PipelineStrip({ phase }) {
  const activeIndex = phase === "idle" ? -1 : phase === "complete" ? stages.length : Math.max(0, Number(phase) - 1);
  return (
    <ol className="pipeline-strip" aria-label="Pipeline status">
      {stages.map(([number, label], index) => (
        <li className={index < activeIndex ? "done" : index === activeIndex ? "running" : ""} key={number}>
          <span>{number}</span>
          <strong>{label}</strong>
        </li>
      ))}
    </ol>
  );
}

export function ArchitectureCanvas() {
  const nodes = [
    ["Layer 1", "RESEARCH", "Source discovery\n+Evidence package", "yellow"],
    ["Layer 2", "GRAPH", "Topic context\n+Provenance + disputes", "pink"],
    ["World Bible", "FICTION", "Fictional names\n+Character map", "blue"],
    ["Blueprint", "PLAN", "Conflict + themes\n+Perspective rules", "lime"],
    ["Episodes", "OUTPUT", "Story · language\n+Optional audio", "white"],
  ];

  return (
    <div className="architecture-canvas" role="img" aria-label="Trinity Reborn architecture from research to story episodes">
      <p className="canvas-note">EXCALIDRAW-READY SYSTEM MAP</p>
      <div className="architecture-flow">
        {nodes.map(([label, eyebrow, description, tone], index) => (
          <React.Fragment key={label}>
            <article className={`architecture-node ${tone}`}>
              <span>{eyebrow}</span>
              <h3>{label}</h3>
              <p>{description}</p>
            </article>
            {index < nodes.length - 1 && <div className="architecture-arrow" aria-hidden="true">→</div>}
          </React.Fragment>
        ))}
      </div>
      <div className="architecture-footnote">
        <span>Postgres</span><i /> <span>OpenAI</span><i /> <span>Gemini</span><i /> <span>ElevenLabs</span>
      </div>
    </div>
  );
}

function RunBoard({ run, selectedPreset }) {
  const characterCount = run.report ? Object.keys(run.report.characters || {}).length : 0;
  return (
    <section className="run-board" aria-live="polite">
      <div className="run-board-heading">
        <div>
          <p className="section-kicker">PIPELINE CONTROL</p>
          <h2>{selectedPreset ? selectedPreset.title : "Choose a signal to begin"}</h2>
        </div>
        <span className={`run-status stage-${run.phase}`}>{run.label}</span>
      </div>
      <PipelineStrip phase={run.phase} />
      <div className="run-board-body">
        <p>{run.message}</p>
        {run.error && <p className="run-error">{run.error}</p>}
        {run.report && (
          <div className="report-grid">
            <div><span>WORLD</span><strong>{run.report.world_status}</strong></div>
            <div><span>BLUEPRINT</span><strong>{run.report.blueprint_status}</strong></div>
            <div><span>CHARACTERS</span><strong>{characterCount}</strong></div>
            <div><span>AUDIO</span><strong>OFF</strong></div>
          </div>
        )}
      </div>
    </section>
  );
}

export default function App() {
  const [page, setPage] = useState("launchpad");
  const [selectedId, setSelectedId] = useState(presets[0].id);
  const [run, setRun] = useState({
    phase: "idle",
    label: "STANDING BY",
    message: "Pick a briefing card. We will seed Layer 2, then hand the topic to the orchestrator.",
    report: null,
    error: "",
  });

  const selectedPreset = useMemo(() => presets.find((preset) => preset.id === selectedId), [selectedId]);
  const running = run.phase !== "idle" && run.phase !== "complete" && run.phase !== "failed";

  async function launchPreset(preset) {
    setSelectedId(preset.id);
    setRun({ phase: "1", label: "SEEDING", message: "Registering the topic and preserving its evidence package in Layer 2.", report: null, error: "" });
    try {
      const seed = buildPresetSeed(preset);
      const topic = await request(apiUrl, "/topics", seed.topic);
      await request(apiUrl, "/ingestions", seed.package);
      setRun({ phase: "3", label: "BUILDING", message: "Layer 2 is ready. World Bible, blueprint, episodes, and translations are running now.", report: null, error: "" });
      const report = await request(orchestratorUrl, "/run-topic", {
        topic_id: topic.topic_id,
        narrate: false,
      });
      setRun({ phase: "complete", label: "COMPLETE", message: "Text pipeline complete. Audio is intentionally off for this demo run.", report, error: "" });
    } catch (reason) {
      setRun({
        phase: "failed",
        label: "NEEDS ATTENTION",
        message: "The launch did not complete. Confirm Layers 1–3 are running and the required API keys are configured.",
        report: null,
        error: reason.message,
      });
    }
  }

  return (
    <main className="app-shell">
      <header className="masthead">
        <button className="brand" type="button" onClick={() => setPage("launchpad")} aria-label="Go to launchpad">
          <span>TR</span>
          <strong>TRINITY<br />REBORN</strong>
        </button>
        <nav aria-label="Primary navigation">
          <button className={page === "launchpad" ? "active" : ""} type="button" onClick={() => setPage("launchpad")}>Launchpad</button>
          <button className={page === "architecture" ? "active" : ""} type="button" onClick={() => setPage("architecture")}>Architecture</button>
        </nav>
        <div className="live-mark"><i /> SYSTEM DEMO</div>
      </header>

      {page === "launchpad" ? (
        <>
          <section className="hero">
            <div className="hero-copy">
              <p className="section-kicker">CURRENT AFFAIRS → FICTION</p>
              <h1>Turn a live signal<br /><em>into a story world.</em></h1>
              <p className="hero-lede">Choose a briefing. Trinity preserves the evidence, maps the uncertainty, then builds a fictional universe around competing perspectives.</p>
              <div className="hero-actions">
                <button className="primary-button" type="button" onClick={() => launchPreset(selectedPreset)} disabled={running}>
                  {running ? "Pipeline running…" : "Run selected topic"} <span aria-hidden="true">→</span>
                </button>
                <button className="secondary-button" type="button" onClick={() => setPage("architecture")}>View system map</button>
              </div>
            </div>
            <div className="hero-stamp">
              <span>LIVE</span>
              <strong>5</strong>
              <p>connected<br />stages</p>
            </div>
          </section>

          <section className="topic-section" aria-labelledby="topic-heading">
            <div className="section-heading">
              <div><p className="section-kicker">PRESET BRIEFINGS</p><h2 id="topic-heading">Pick a story signal</h2></div>
              <p>Each card seeds a compact, provenance-aware research package before the full pipeline begins.</p>
            </div>
            <div className="topic-grid">
              {presets.map((preset) => (
                <PresetCard key={preset.id} preset={preset} selected={preset.id === selectedId} onSelect={setSelectedId} onLaunch={launchPreset} disabled={running} />
              ))}
            </div>
          </section>

          <RunBoard run={run} selectedPreset={selectedPreset} />
        </>
      ) : (
        <section className="architecture-page">
          <div className="section-heading architecture-heading">
            <div><p className="section-kicker">HOW IT WORKS</p><h1>One factual spine.<br /><em>Many fictional futures.</em></h1></div>
            <p>The graph retains evidence and disagreements; the creative chain reads only the assembled blueprint.</p>
          </div>
          <ArchitectureCanvas />
          <div className="architecture-actions">
            <a className="primary-button" href="/trinity-reborn-architecture.excalidraw" download>Download Excalidraw <span aria-hidden="true">↓</span></a>
            <button className="secondary-button" type="button" onClick={() => setPage("launchpad")}>Back to launchpad</button>
          </div>
        </section>
      )}

      <footer><span>TRINITY REBORN / HACKATHON DEMO</span><span>Evidence first. Imagination second.</span></footer>
    </main>
  );
}
