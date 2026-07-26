import React, { useEffect, useMemo, useState } from "react";
import { buildPresetSeed, presets } from "./presets";

const apiUrl = import.meta.env.VITE_API_URL || "/api";
const orchestratorUrl = import.meta.env.VITE_ORCHESTRATOR_URL || "/orchestrator";
const audioUrl = import.meta.env.VITE_AUDIO_URL || "/audio-service";

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

async function get(baseUrl, path) {
  const response = await fetch(`${baseUrl}${path}`);
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
    <div className="architecture-canvas" role="img" aria-label="Echoes architecture from research to story episodes">
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

export function DemoPage({ onLaunchpad }) {
  const components = [
    ["01", "Layer 1", "Signal intake", "Finds source material, extracts evidence, and bundles a research package before anything creative starts.", "yellow"],
    ["02", "Layer 2", "Knowledge graph", "Stores canonical entities, events, claims, provenance, and unresolved disputes in PostgreSQL.", "pink"],
    ["03", "World builder", "Fictional cast", "Turns source entities into fictional places, factions, and characters without using real-world names.", "blue"],
    ["04", "Blueprint", "Shared story contract", "Builds one deterministic, self-contained plan for every downstream narrative module.", "lime"],
    ["05", "Episodes + voice", "Audience-ready output", "Generates character perspectives, translations, and optional multilingual narration.", "white"],
  ];
  const layers = [
    ["LAYER 1", "Collect without deciding the truth.", "Discovery and extraction preserve source material and turn it into a structured research package. The creative system does not start from a headline or a single summary.", "#ffd84e"],
    ["LAYER 2", "Model what is known—and what is contested.", "The graph keeps entities, events, claims, relationships, provenance, and disputes separate. A disputed claim remains a disputed claim instead of becoming a convenient plot fact.", "#ff9fcb"],
    ["LAYER 3", "Create from a bounded fictional brief.", "The World Bible fictionalizes the cast. The Blueprint turns evidence into guardrails. Stories, translations, and audio only read that prepared artifact.", "#8ed2ff"],
  ];

  return (
    <section className="demo-page">
      <section className="demo-hero">
        <p className="section-kicker">THE ECHOES DEMO / 01</p>
        <h1>Stories need<br /><em>more than a headline.</em></h1>
        <p>Echoes is a safety-first story pipeline for transforming fast-moving public information into fictional, multilingual narrative experiences—without flattening uncertainty into fake certainty.</p>
        <div className="demo-hero-tags"><span>PROVENANCE FIRST</span><span>FICTIONAL OUTPUT</span><span>HUMAN-SCALE STORIES</span></div>
      </section>

      <section className="demo-section demo-problem" aria-labelledby="problem-heading">
        <div className="demo-section-heading"><p className="section-kicker">02 / THE PROBLEM</p><h2 id="problem-heading">Current events move fast.<br />Context gets lost faster.</h2></div>
        <div className="demo-problem-grid">
          <article><span>01</span><h3>Information arrives fragmented.</h3><p>Articles, public statements, and eyewitness accounts name overlapping people and events without agreeing on what happened.</p></article>
          <article><span>02</span><h3>Uncertainty gets erased.</h3><p>Most content pipelines collapse allegations, evidence, and conclusions into one smooth—but misleading—narrative.</p></article>
          <article><span>03</span><h3>Stories become inaccessible.</h3><p>Nuanced context rarely travels across languages or formats, leaving audiences with either a wall of facts or an oversimplified take.</p></article>
        </div>
      </section>

      <section className="demo-section demo-stakes" aria-labelledby="stakes-heading">
        <div><p className="section-kicker">03 / WHY IT MATTERS</p><h2 id="stakes-heading">When ambiguity disappears, trust goes with it.</h2></div>
        <div className="stakes-copy"><p>Public-interest stories often contain competing accounts. Treating one account as settled fact can harm people, distort the issue, and make audiences less confident in every story that follows.</p><p>Echoes keeps the tension visible. It makes room for character, emotion, and imagination while preserving the difference between evidence, interpretation, and dispute.</p></div>
      </section>

      <section className="demo-section demo-solution" aria-labelledby="solution-heading">
        <div className="demo-solution-stamp">FIX<br />THE<br />FLOW</div>
        <div><p className="section-kicker">04 / OUR FIX</p><h2 id="solution-heading">One factual spine.<br /><em>Many human stories.</em></h2><p>We separate evidence work from creative work. The first two layers create an inspectable knowledge graph. The final layer only receives a controlled Story Blueprint, so every story inherits its boundaries as well as its drama.</p><div className="solution-rules"><span>KEEP PROVENANCE</span><span>FLAG DISPUTES</span><span>FICTIONALIZE PEOPLE + PLACES</span><span>LOCALIZE THE EXPERIENCE</span></div></div>
      </section>

      <section className="demo-section" aria-labelledby="components-heading">
        <div className="demo-section-heading"><p className="section-kicker">05 / COMPONENTS</p><h2 id="components-heading">A small chain with<br />clear hand-offs.</h2></div>
        <div className="component-grid">
          {components.map(([number, title, eyebrow, description, tone]) => <article className={tone} key={title}><span>{number}</span><p>{eyebrow}</p><h3>{title}</h3><div className="component-divider" /><small>{description}</small></article>)}
        </div>
      </section>

      <section className="demo-section demo-layers" aria-labelledby="layers-heading">
        <div className="demo-section-heading"><p className="section-kicker">06 / LAYER BY LAYER</p><h2 id="layers-heading">The pipeline has a job<br />at every boundary.</h2></div>
        <div className="layer-list">
          {layers.map(([label, title, description, color], index) => <article key={label}><div className="layer-index" style={{ backgroundColor: color }}><span>{label}</span><strong>0{index + 1}</strong></div><div><h3>{title}</h3><p>{description}</p></div><span className="layer-arrow" aria-hidden="true">→</span></article>)}
        </div>
        <aside className="demo-orchestrator"><span>CONTROL PLANE</span><strong>The orchestrator calls each service in order, records a run report, and lets audio remain opt-in.</strong><p>Every module can be inspected on its own; the full demo still runs with a single click.</p></aside>
      </section>

      <section className="demo-closing">
        <p className="section-kicker">07 / THE POINT</p><h2>Evidence first.<br /><em>Imagination second.</em></h2>
        <p>Echoes makes it possible to turn complicated signals into engaging stories without pretending the world is simpler than it is.</p>
        <button className="primary-button" type="button" onClick={onLaunchpad}>Try the live demo <span aria-hidden="true">→</span></button>
      </section>
    </section>
  );
}

const finalDemoStories = [
  ["student-en", "EN", "The Notice Board", "Student organiser", "English", "pink"],
  ["guardian-hi", "हि", "अधूरी खबर", "Parent waiting for clarity", "Hindi", "yellow"],
  ["reporter-ta", "த", "கேள்விகளின் வரைபடம்", "Local reporter", "Tamil", "blue"],
  ["official-bn", "ব", "আলোর ঘর", "Examination official", "Bengali", "lime"],
];

export function FinalDemoPage({ onLaunchpad }) {
  const [audio, setAudio] = useState({});
  async function playStory(storyId) {
    setAudio((items) => ({ ...items, [storyId]: { state: "loading" } }));
    try {
      await request(audioUrl, `/final-demo/audio/${storyId}`, {});
      setAudio((items) => ({ ...items, [storyId]: { state: "ready", src: `${audioUrl}/final-demo/audio/${storyId}` } }));
    } catch (reason) {
      setAudio((items) => ({ ...items, [storyId]: { state: "failed", error: reason.message } }));
    }
  }
  return (
    <section className="final-demo-page">
      <section className="final-demo-hero"><p className="section-kicker">FINAL DEMO / CASE FILE 01</p><h1>One exam.<br /><em>Four competing signals.</em></h1><p>A curated walkthrough of the NEET-UG 2026 case: Echoes keeps the investigation, official response, and later disputed online claims visible before turning the human stakes into fictional, multilingual perspectives.</p><span>NEET-UG 2026 CASE FILE · OFFICIAL SOURCES, JULY 2026</span></section>
      <section className="final-demo-section"><p className="section-kicker">01 / THE SIGNAL</p><h2>What happened—and why one headline was not enough.</h2><div className="source-lenses">
        <article className="yellow"><span>CBI FIR / 12 MAY</span><h3>Alleged pre-exam circulation</h3><p>After a Higher Education Department complaint, the CBI registered an FIR over alleged irregularities and the reported unauthorized circulation of material before the 3 May examination.</p><a href="https://www.pib.gov.in/PressReleasePage.aspx?PRID=2260410&lang=2&reg=48" target="_blank" rel="noreferrer">Read the PIB release ↗</a></article>
        <article className="pink"><span>RE-EXAM / 21 JUNE</span><h3>Process moved into public view</h3><p>NTA published dedicated NEET-UG 2026 re-examination updates, candidate notices, and channels for reporting suspicious claims.</p><a href="https://neet.nta.nic.in/" target="_blank" rel="noreferrer">Read NTA updates ↗</a></article>
        <article className="blue"><span>FRESH VIRAL CLAIMS / JULY</span><h3>Not every post is evidence</h3><p>NTA later rejected fresh social-media claims of a re-exam leak or advance access, and asked candidates to use official communication rather than viral material.</p><a href="https://newsonair.gov.in/nta-denies-claims-of-neet-ug-2026-paper-leak-or-advance-access/" target="_blank" rel="noreferrer">Read the NTA response ↗</a></article>
      </div></section>
      <section className="final-demo-section final-demo-flow"><p className="section-kicker">02 / HOW ECHOES HANDLES IT</p><h2>We do not choose a side.<br />We structure the uncertainty.</h2><ol><li><b>01</b><span><strong>Collect</strong> Keep the FIR, NTA notices, later denials, reporting, and human accounts as distinct signals.</span></li><li><b>02</b><span><strong>Connect</strong> Map entities, events, claims, and their provenance into the knowledge graph.</span></li><li><b>03</b><span><strong>Bound</strong> Carry unresolved disputes into the Blueprint as tension—not settled fact.</span></li><li><b>04</b><span><strong>Humanise</strong> Generate fictional perspectives that feel the stakes without naming real people.</span></li></ol></section>
      <section className="final-demo-section final-stories"><div><p className="section-kicker">03 / FOUR PERSPECTIVES</p><h2>Listen to the same tension<br /><em>from four different rooms.</em></h2></div><p>Each story is fictional. The voices are deliberately fixed for the final demo, avoiding dynamic voice selection and keeping each language consistent.</p><div className="final-story-grid">{finalDemoStories.map(([id, mark, title, role, language, tone]) => { const item = audio[id]; return <article className={tone} key={id}><span className="language-mark">{mark}</span><p>{language.toUpperCase()} / FICTIONAL PERSPECTIVE</p><h3>{title}</h3><strong>{role}</strong>{item?.state === "ready" ? <audio controls src={item.src}>Audio unavailable.</audio> : <button className="launch-button" type="button" onClick={() => playStory(id)} disabled={item?.state === "loading"}>{item?.state === "loading" ? "Preparing narration..." : `Play ${language}`}</button>}{item?.error && <small>{item.error}</small>}</article>; })}</div></section>
      <section className="final-demo-close"><p className="section-kicker">THE ECHOES PROMISE</p><h2>Evidence stays inspectable.<br /><em>Stories stay human.</em></h2><button className="primary-button" type="button" onClick={onLaunchpad}>Explore the full product <span aria-hidden="true">→</span></button></section>
    </section>
  );
}

function graphNodeId(node) {
  // Claims also carry event_id, so their own ID must win or they collide with
  // the event node and overwrite its position in the SVG graph.
  return node.entity_id || node.claim_id || node.event_id;
}

function graphNodeLabel(node) {
  const label = node.label || node.title || node.text || "Untitled node";
  return label.length > 22 ? `${label.slice(0, 22)}...` : label;
}

export function KnowledgeGraphCanvas({ context }) {
  const events = useMemo(() => (context.events || []).slice(0, 4).map((node) => ({ ...node, graphKind: "event" })), [context.events]);
  const entities = useMemo(() => (context.entities || []).slice(0, 12).map((node) => ({ ...node, graphKind: "entity" })), [context.entities]);
  const claims = useMemo(() => (context.claims || []).slice(0, 8).map((node) => ({ ...node, graphKind: "claim" })), [context.claims]);
  const nodes = useMemo(() => [...entities, ...claims, ...events], [entities, claims, events]);
  const initialPositions = useMemo(() => {
    const positions = {};
    events.forEach((node, index) => { positions[graphNodeId(node)] = { x: 600 + (index - (events.length - 1) / 2) * 225, y: 310 }; });
    entities.forEach((node, index) => {
      const angle = (-Math.PI / 2) + (index / Math.max(entities.length, 1)) * Math.PI * 2;
      positions[graphNodeId(node)] = { x: 600 + Math.cos(angle) * 430, y: 310 + Math.sin(angle) * 225 };
    });
    claims.forEach((node, index) => { positions[graphNodeId(node)] = { x: 170 + index * 150, y: 595 }; });
    return positions;
  }, [entities, events, claims]);
  const [positions, setPositions] = useState(initialPositions);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [gesture, setGesture] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const visibleIds = new Set(nodes.map(graphNodeId));
  const links = [];
  const addLink = (source, target, type, status = "active") => {
    if (!visibleIds.has(source) || !visibleIds.has(target) || source === target) return;
    const key = [source, target].sort().join(":");
    if (!links.some((link) => link.key === key)) links.push({ key, source, target, type, status });
  };
  (context.relationships || []).forEach((relationship) => addLink(relationship.subject?.id, relationship.object?.id, relationship.type, relationship.status));
  events.forEach((event) => {
    (event.participant_entity_ids || []).forEach((entityId) => addLink(graphNodeId(event), entityId, "participant"));
    (event.location_entity_ids || []).forEach((entityId) => addLink(graphNodeId(event), entityId, "location"));
  });
  claims.forEach((claim) => {
    addLink(graphNodeId(claim), claim.event_id, "claim");
    addLink(graphNodeId(claim), claim.subject_ref, "subject");
    addLink(graphNodeId(claim), claim.asserted_by, "reported by");
  });
  const colors = { event: "#d5ff4e", entity: "#8ed2ff", claim: "#ff9fcb" };
  const selected = nodes.find((node) => graphNodeId(node) === selectedId);
  const pointerPoint = (event) => {
    const svg = event.currentTarget.ownerSVGElement || event.currentTarget;
    const bounds = svg.getBoundingClientRect();
    return { x: event.clientX * 1200 / bounds.width, y: event.clientY * 720 / bounds.height };
  };
  const handleMove = (event) => {
    if (!gesture) return;
    const point = pointerPoint(event);
    const dx = point.x - gesture.start.x;
    const dy = point.y - gesture.start.y;
    if (gesture.kind === "node") setPositions((items) => ({ ...items, [gesture.id]: { x: gesture.origin.x + dx, y: gesture.origin.y + dy } }));
    else setPan({ x: gesture.origin.x + dx, y: gesture.origin.y + dy });
  };
  const details = selected && [
    [selected.graphKind === "entity" ? "TYPE" : selected.graphKind === "event" ? "STATUS" : "EPISTEMIC STATUS", selected.type || selected.status || selected.epistemic_status || "reported"],
    ["SUMMARY", selected.description || selected.title || selected.text || selected.label || "No additional narrative detail returned."],
    ["TIME", selected.temporal?.start || selected.temporal_scope?.start || "Not specified"],
    ["LINKS", links.filter((link) => link.source === selectedId || link.target === selectedId).length],
  ];

  return (
    <div className="graph-explorer-wrap">
      <div className="graph-legend"><span><i className="entity" /> Entity</span><span><i className="event" /> Event</span><span><i className="claim" /> Claim</span><b>DRAG NODES · DRAG SPACE TO PAN · CLICK TO INSPECT</b></div>
      <div className="graph-canvas-wrap interactive">
      <svg className="knowledge-graph-canvas" viewBox="0 0 1200 720" role="img" aria-label="Interactive stored topic knowledge graph" onPointerMove={handleMove} onPointerUp={() => setGesture(null)} onPointerLeave={() => setGesture(null)} onPointerDown={(event) => { if (event.target === event.currentTarget) setGesture({ kind: "pan", start: pointerPoint(event), origin: pan }); }}>
        <defs><marker id="graph-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#16120d" /></marker></defs>
        <g transform={`translate(${pan.x}, ${pan.y})`}>
        {links.map((link) => {
          const start = positions[link.source];
          const end = positions[link.target];
          if (!start || !end) return null;
          return (
            <g className={`knowledge-edge ${link.status || "active"}`} key={link.key}>
              <line x1={start.x} y1={start.y} x2={end.x} y2={end.y} markerEnd="url(#graph-arrow)" />
              <text x={(start.x + end.x) / 2} y={(start.y + end.y) / 2 - 8}>{link.type}</text>
            </g>
          );
        })}
        {nodes.map((node) => {
          const id = graphNodeId(node);
          const position = positions[id];
          return (
            <g className={`knowledge-node ${node.graphKind} ${node.status || "active"} ${selectedId === id ? "selected" : ""}`} key={id} transform={`translate(${position.x}, ${position.y})`} onPointerDown={(event) => { event.stopPropagation(); event.currentTarget.setPointerCapture(event.pointerId); setGesture({ kind: "node", id, start: pointerPoint(event), origin: position }); }} onClick={(event) => { event.stopPropagation(); setSelectedId(id); }}>
              <rect x="-88" y="-32" width="176" height="64" rx="4" fill={colors[node.graphKind]} stroke="#16120d" strokeWidth="3" />
              <text className="knowledge-kind" y="-7" fill="#16120d">{node.graphKind.toUpperCase()}</text>
              <text className="knowledge-label" y="14" fill="#16120d">{graphNodeLabel(node)}</text>
            </g>
          );
        })}
        </g>
      </svg>
      </div>
      {selected ? <aside className="node-inspector" aria-live="polite"><div><p className="section-kicker">NODE INSPECTOR</p><h3>{graphNodeLabel(selected)}</h3></div><button type="button" onClick={() => setSelectedId(null)} aria-label="Close node details">×</button><dl>{details.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{String(value)}</dd></div>)}</dl></aside> : <p className="graph-hint">Click any node to inspect its full returned context.</p>}
      {nodes.length === 0 && <p className="empty-graph">This topic does not have any returned graph nodes yet.</p>}
    </div>
  );
}

function KnowledgeGraphsPage({ topics, context, selectedTopicId, loading, error, onSelect }) {
  return (
    <section className="knowledge-page">
      <div className="section-heading architecture-heading">
        <div><p className="section-kicker">LAYER 2 / STORED GRAPHS</p><h1>Knowledge<br /><em>graphs.</em></h1></div>
        <p>Explore the canonical entities, events, claims, and relationships stored in PostgreSQL for every created topic.</p>
      </div>
      <div className="graph-panel">
        <div className="graph-toolbar">
          <label>CHOOSE A STORED TOPIC
            <select value={selectedTopicId} onChange={(event) => onSelect(event.target.value)} disabled={!topics?.length}>
              {!topics?.length && <option>Loading stored topics...</option>}
              {topics?.map((topic) => <option key={topic.topic_id} value={topic.topic_id}>{topic.display_name}</option>)}
            </select>
          </label>
          <span>GRAPH EXPLORER</span>
        </div>
        <div className="graph-detail">
          {error && <p className="run-error">{error}</p>}
          {loading && <p className="graph-loading">Loading graph context...</p>}
          {context && !loading && (
            <>
              <div className="graph-detail-heading">
                <div><p className="section-kicker">CANONICAL CONTEXT</p><h2>{context.topic.display_name}</h2></div>
                <span>{context.coverage.returned_nodes} NODES</span>
              </div>
              <KnowledgeGraphCanvas context={context} key={context.topic.topic_id} />
              <div className="graph-metrics">
                <div><span>ENTITIES</span><strong>{context.entities.length}</strong></div>
                <div><span>EVENTS</span><strong>{context.events.length}</strong></div>
                <div><span>CLAIMS</span><strong>{context.claims.length}</strong></div>
                <div><span>LINKS</span><strong>{context.relationships.length}</strong></div>
                <div><span>DISPUTES</span><strong>{context.disputes.length}</strong></div>
              </div>
            </>
          )}
          {!context && !loading && !error && <p className="empty-graph">Select a topic to load its stored graph.</p>}
        </div>
      </div>
    </section>
  );
}

const narrationLanguages = [
  ["en", "English"], ["hi", "Hindi"], ["ta", "Tamil"], ["bn", "Bengali"], ["pa", "Punjabi"], ["gu", "Gujarati"],
];

export function AudioDeck({ run, audioByCharacter, selectedLanguages, onSelectLanguage, onNarrate }) {
  const characterIds = Object.keys(run.report?.characters || {});
  if (run.phase !== "complete" || !characterIds.length) return null;
  return (
    <section className="audio-deck">
      <div className="audio-deck-heading">
        <div><p className="section-kicker">OPTIONAL NARRATION</p><h2>Press play on a perspective.</h2></div>
        <span>6 LANGUAGE OPTIONS</span>
      </div>
      <div className="audio-grid">
        {characterIds.map((characterId, index) => {
          const language = selectedLanguages[characterId] || "en";
          const item = audioByCharacter[characterId]?.[language];
          return (
            <article className="audio-card" key={characterId}>
              <span>CHARACTER {String(index + 1).padStart(2, "0")}</span>
              <strong>Perspective {String(index + 1).padStart(2, "0")}</strong>
              <div className="language-picker" aria-label={`Narration language for character ${index + 1}`}>
                {narrationLanguages.map(([code, label]) => <button className={code === language ? "selected" : ""} key={code} type="button" title={label} onClick={() => onSelectLanguage(characterId, code)}>{code.toUpperCase()}</button>)}
              </div>
              {item?.state === "ready" ? (
                <audio controls preload="none" src={item.src} aria-label={`${language} narration`}>Your browser does not support audio playback.</audio>
              ) : (
                <button className="launch-button" type="button" onClick={() => onNarrate(characterId, language)} disabled={item?.state === "generating"}>
                  {item?.state === "generating" ? "Generating audio..." : `Generate ${narrationLanguages.find(([code]) => code === language)[1]} audio`}
                </button>
              )}
              {item?.error && <p className="audio-error">{item.error}</p>}
            </article>
          );
        })}
      </div>
    </section>
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
            <div><span>AUDIO</span><strong>ON DEMAND</strong></div>
          </div>
        )}
      </div>
    </section>
  );
}

export default function App() {
  const [page, setPage] = useState("launchpad");
  const [selectedId, setSelectedId] = useState(presets[0].id);
  const [graphTopics, setGraphTopics] = useState(null);
  const [selectedGraphId, setSelectedGraphId] = useState("");
  const [graphContext, setGraphContext] = useState(null);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState("");
  const [audioByCharacter, setAudioByCharacter] = useState({});
  const [selectedAudioLanguages, setSelectedAudioLanguages] = useState({});
  const [run, setRun] = useState({
    phase: "idle",
    label: "STANDING BY",
    message: "Pick a briefing card. We will seed Layer 2, then hand the topic to the orchestrator.",
    report: null,
    error: "",
  });

  const selectedPreset = useMemo(() => presets.find((preset) => preset.id === selectedId), [selectedId]);
  const running = run.phase !== "idle" && run.phase !== "complete" && run.phase !== "failed";

  useEffect(() => {
    if (page !== "graphs" || graphTopics !== null) return;
    get(apiUrl, "/topics?limit=200")
      .then((topics) => {
        setGraphTopics(topics);
        if (topics.length) setSelectedGraphId(topics[0].topic_id);
      })
      .catch((reason) => setGraphError(`Could not load stored topics: ${reason.message}`));
  }, [page, graphTopics]);

  useEffect(() => {
    if (page !== "graphs" || !selectedGraphId) return;
    setGraphLoading(true);
    setGraphError("");
    get(apiUrl, `/topics/${selectedGraphId}/context?max_nodes=50&max_relationships=80`)
      .then((context) => setGraphContext(context))
      .catch((reason) => setGraphError(`Could not load graph context: ${reason.message}`))
      .finally(() => setGraphLoading(false));
  }, [page, selectedGraphId]);

  async function launchPreset(preset) {
    setSelectedId(preset.id);
    setRun({ phase: "1", label: "SEEDING", message: "Registering the topic and preserving its evidence package in Layer 2.", report: null, error: "" });
    try {
      const seed = buildPresetSeed(preset);
      let topic;
      try {
        topic = await request(apiUrl, "/topics", seed.topic);
        await request(apiUrl, "/ingestions", seed.package);
      } catch (reason) {
        if (!String(reason.message).startsWith("409:")) throw reason;
        const topics = await get(apiUrl, "/topics?limit=200");
        topic = topics.find((candidate) => candidate.topic_key === seed.topic.topic_key);
        if (!topic) throw new Error(`The saved ${preset.title} topic could not be found.`, { cause: reason });
      }
      setRun({ phase: "3", label: "BUILDING", message: "Layer 2 is ready. World Bible, blueprint, episodes, and translations are running now.", report: null, error: "" });
      const report = await request(orchestratorUrl, "/run-topic", {
        topic_id: topic.topic_id,
        narrate: false,
      });
      setGraphTopics(null);
      setAudioByCharacter({});
      setSelectedAudioLanguages({});
      setRun({ phase: "complete", label: "COMPLETE", message: "Text pipeline complete. Generate English narration below whenever you want to hear a character's perspective.", report, error: "" });
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

  function selectAudioLanguage(characterId, language) {
    setSelectedAudioLanguages((languages) => ({ ...languages, [characterId]: language }));
  }

  async function narrateCharacter(characterId, language) {
    if (!run.report) return;
    setAudioByCharacter((items) => ({ ...items, [characterId]: { ...items[characterId], [language]: { state: "generating" } } }));
    try {
      const episode = await request(audioUrl, "/narrate", {
        topic_id: run.report.topic_id,
        character_id: characterId,
        languages: [language],
      });
      if (!episode.audio?.[language]) {
        throw new Error(episode.audio_errors?.[language] || `Audio generation did not return ${language} narration`);
      }
      setAudioByCharacter((items) => ({
        ...items,
        [characterId]: { ...items[characterId], [language]: { state: "ready", src: `${audioUrl}/audio/${run.report.topic_id}/${characterId}/${language}` } },
      }));
    } catch (reason) {
      setAudioByCharacter((items) => ({
        ...items,
        [characterId]: { ...items[characterId], [language]: { state: "failed", error: reason.message } },
      }));
    }
  }

  return (
    <main className="app-shell">
      <header className="masthead">
        <button className="brand" type="button" onClick={() => setPage("launchpad")} aria-label="Go to launchpad">
          <span>EC</span>
          <strong>ECHOES<br />STUDIO</strong>
        </button>
        <nav aria-label="Primary navigation">
          <button className={page === "launchpad" ? "active" : ""} type="button" onClick={() => setPage("launchpad")}>Launchpad</button>
          <button className={page === "graphs" ? "active" : ""} type="button" onClick={() => setPage("graphs")}>Knowledge graphs</button>
          <button className={page === "architecture" ? "active" : ""} type="button" onClick={() => setPage("architecture")}>Architecture</button>
          <button className={page === "demo" ? "active" : ""} type="button" onClick={() => setPage("demo")}>About Echoes</button>
          <button className={page === "final-demo" ? "active" : ""} type="button" onClick={() => setPage("final-demo")}>Final demo</button>
        </nav>
        <div className="live-mark"><i /> SYSTEM DEMO</div>
      </header>

      {page === "launchpad" ? (
        <>
          <section className="hero">
            <div className="hero-copy">
              <p className="section-kicker">CURRENT AFFAIRS → FICTION</p>
              <h1>Turn a live signal<br /><em>into a story world.</em></h1>
              <p className="hero-lede">Choose a briefing. Echoes preserves the evidence, maps the uncertainty, then builds a fictional universe around competing perspectives.</p>
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
          <AudioDeck run={run} audioByCharacter={audioByCharacter} selectedLanguages={selectedAudioLanguages} onSelectLanguage={selectAudioLanguage} onNarrate={narrateCharacter} />
        </>
      ) : page === "graphs" ? (
        <KnowledgeGraphsPage
          topics={graphTopics}
          context={graphContext}
          selectedTopicId={selectedGraphId}
          loading={graphLoading}
          error={graphError}
          onSelect={setSelectedGraphId}
        />
      ) : page === "architecture" ? (
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
      ) : page === "final-demo" ? (
        <FinalDemoPage onLaunchpad={() => setPage("launchpad")} />
      ) : (
        <DemoPage onLaunchpad={() => setPage("launchpad")} />
      )}

      <footer><span>ECHOES / HACKATHON DEMO</span><span>Evidence first. Imagination second.</span></footer>
    </main>
  );
}
