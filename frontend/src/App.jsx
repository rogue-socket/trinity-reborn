import React, { useEffect, useState } from "react";
import { demoScenario } from "./demo";

const apiUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function get(path) {
  const response = await fetch(`${apiUrl}${path}`);
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
  return response.json();
}

async function post(path, body) {
  const response = await fetch(`${apiUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
  return response.json();
}

function Status({ value }) {
  return <span className={`status ${value || "active"}`}>{value || "active"}</span>;
}

function NodeList({ title, nodes, label }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      <ul className="node-list">
        {nodes.map((node) => (
          <li key={node[`${label}_id`]}>
            <div>
              <strong>{node.label || node.title || node.text}</strong>
              <small>{node.type || node.epistemic_status}</small>
            </div>
            <Status value={node.status} />
          </li>
        ))}
        {!nodes.length && <li className="empty">No canonical {title.toLowerCase()} yet.</li>}
      </ul>
    </section>
  );
}

export function GraphView({ nodes, relationships, onInspect }) {
  const columns = 4;
  const width = 960;
  const rowHeight = 150;
  const height = Math.max(260, Math.ceil(nodes.length / columns) * rowHeight + 40);
  const positions = new Map(
    nodes.map((node, index) => [
      node.entity_id || node.event_id || node.claim_id,
      {
        x: 130 + (index % columns) * 235,
        y: 80 + Math.floor(index / columns) * rowHeight,
      },
    ]),
  );

  return (
    <svg className="graph-canvas" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Connected canonical knowledge graph">
      {relationships.map((edge) => {
        const start = positions.get(edge.subject.id);
        const end = positions.get(edge.object.id);
        if (!start || !end) return null;
        return (
          <g className={`graph-edge ${edge.status || "active"}`} key={edge.relationship_id}>
            <line x1={start.x} y1={start.y} x2={end.x} y2={end.y} />
            <text x={(start.x + end.x) / 2} y={(start.y + end.y) / 2 - 8}>{edge.type}</text>
          </g>
        );
      })}
      {nodes.map((node) => {
        const id = node.entity_id || node.event_id || node.claim_id;
        const position = positions.get(id);
        const label = node.label || node.title || node.text;
        return (
          <g
            className={`graph-vertex ${node.status || "active"}`}
            key={id}
            transform={`translate(${position.x}, ${position.y})`}
            onClick={() => onInspect(node)}
            role="button"
            tabIndex={0}
          >
            <rect x="-92" y="-34" width="184" height="68" rx="10" />
            <text className="vertex-kind" y="-10">{node.type || "claim"}</text>
            <text className="vertex-label" y="13">{label.length > 28 ? `${label.slice(0, 28)}…` : label}</text>
          </g>
        );
      })}
    </svg>
  );
}

export function ResolutionDecisionList({ decisions }) {
  return (
    <ul className="node-list">
      {decisions.map((decision) => (
        <li key={decision.decision_id}>
          <div>
            <strong>{decision.incoming_type} · {decision.incoming_id}</strong>
            <small>{decision.outcome} · {decision.processing_version} · {decision.ontology_version}</small>
            <p>{decision.rationale}</p>
            <code>{JSON.stringify(decision.signals)}</code>
          </div>
          <code>{decision.decision_id}</code>
        </li>
      ))}
      {!decisions.length && <li className="empty">No resolution decisions for this ingestion.</li>}
    </ul>
  );
}

export default function App() {
  const [topics, setTopics] = useState([]);
  const [topicId, setTopicId] = useState("");
  const [context, setContext] = useState(null);
  const [error, setError] = useState("");
  const [ingestionId, setIngestionId] = useState("");
  const [report, setReport] = useState(null);
  const [detail, setDetail] = useState(null);
  const [replaying, setReplaying] = useState(false);
  const [maxNodes, setMaxNodes] = useState(200);
  const [includeDisputed, setIncludeDisputed] = useState(true);
  const [rawExport, setRawExport] = useState(null);
  const [replaySteps, setReplaySteps] = useState([]);

  useEffect(() => {
    get("/topics?limit=50")
      .then((items) => {
        setTopics(items);
        if (items.length) setTopicId(items[0].topic_id);
      })
      .catch((reason) => setError(`Could not load topics: ${reason.message}`));
  }, []);

  useEffect(() => {
    if (!topicId) return;
    get(`/topics/${topicId}/context?max_nodes=${maxNodes}&include_disputed=${includeDisputed}`)
      .then((body) => {
        setContext(body);
        setError("");
      })
      .catch((reason) => setError(`Could not load topic context: ${reason.message}`));
  }, [topicId, maxNodes, includeDisputed]);

  async function loadContext(event) {
    event?.preventDefault();
    try {
      setContext(await get(`/topics/${topicId}/context?max_nodes=${maxNodes}&include_disputed=${includeDisputed}`));
      setError("");
    } catch (reason) {
      setError(`Could not load topic context: ${reason.message}`);
    }
  }

  async function loadRawExport() {
    try {
      setRawExport(await get(`/topics/${topicId}/raw-export`));
      setError("");
    } catch (reason) {
      setError(`Could not load raw export: ${reason.message}`);
    }
  }

  async function loadReport(event) {
    event.preventDefault();
    try {
      setReport(await get(`/ingestions/${ingestionId}`));
      setError("");
    } catch (reason) {
      setError(`Could not load ingestion report: ${reason.message}`);
    }
  }

  async function replayDemo() {
    setReplaying(true);
    try {
      const topicKey = `${demoScenario.topic.topic_key}-${crypto.randomUUID().replaceAll("-", "")}`;
      const topic = await post("/topics", { ...demoScenario.topic, topic_key: topicKey });
      let latestReport;
      const steps = [];
      for (const [index, delta] of demoScenario.deltas.entries()) {
        latestReport = await post("/ingestions", {
          ...delta,
          schema_version: "1.0",
          package_id: crypto.randomUUID(),
          topic_key: topicKey,
        });
        const snapshot = await get(`/topics/${topic.topic_id}/context`);
        steps.push({
          label: `Delta ${index + 1}`,
          summary: latestReport.summary,
          coverage: snapshot.coverage,
          disputes: snapshot.disputes.length,
        });
      }
      setTopics((items) => [topic, ...items]);
      setTopicId(topic.topic_id);
      setReport(await get(`/ingestions/${latestReport.ingestion_id}`));
      setReplaySteps(steps);
      setError("");
    } catch (reason) {
      setError(`Could not replay demo: ${reason.message}`);
    } finally {
      setReplaying(false);
    }
  }

  async function inspectNode(node) {
    try {
      if (node.entity_id) setDetail(await get(`/entities/${node.entity_id}/context?topic_id=${topicId}`));
      if (node.claim_id) setDetail(await get(`/claims/${node.claim_id}/evidence`));
    } catch (reason) {
      setError(`Could not inspect node: ${reason.message}`);
    }
  }

  const graphNodes = context
    ? [...context.entities, ...context.events, ...context.claims]
    : [];
  const resolutionDecisions = report?.resolution_decisions || [];

  return (
    <main>
      <header>
        <div>
          <p className="eyebrow">Layer 2 operator console</p>
          <h1>Current-affairs knowledge graph</h1>
        </div>
        <label>
          Topic
          <select value={topicId} onChange={(event) => setTopicId(event.target.value)}>
            {!topics.length && <option>No registered topics</option>}
            {topics.map((topic) => (
              <option key={topic.topic_id} value={topic.topic_id}>
                {topic.display_name || topic.topic_key} · {topic.status}
              </option>
            ))}
          </select>
        </label>
        <button className="replay" type="button" onClick={replayDemo} disabled={replaying}>
          {replaying ? "Replaying…" : "Replay seeded demo"}
        </button>
      </header>

      {error && <p className="error">{error}</p>}
      {!context && !error && <p className="empty">Select a registered topic to inspect its graph.</p>}

      {context && (
        <>
          {replaySteps.length > 0 && (
            <section className="panel operator">
              <h2>Graph evolution</h2>
              <ol className="timeline">
                {replaySteps.map((step) => (
                  <li key={step.label}>
                    <strong>{step.label}</strong>
                    <span>{step.summary.created} created, {step.summary.matched} matched, {step.disputes} disputes · {step.coverage.returned_nodes} nodes</span>
                  </li>
                ))}
              </ol>
            </section>
          )}
          <section className="panel operator">
            <h2>Layer 3 retrieval</h2>
            <form onSubmit={loadContext}>
              <label>
                Maximum nodes
                <input type="number" min="1" max="200" value={maxNodes} onChange={(event) => setMaxNodes(Number(event.target.value))} />
              </label>
              <label>
                <input type="checkbox" checked={includeDisputed} onChange={(event) => setIncludeDisputed(event.target.checked)} />
                Include disputes
              </label>
              <button type="submit">Run context query</button>
              <button type="button" onClick={loadRawExport}>Load raw export</button>
            </form>
            <p className="query-coverage">Returned {context.coverage.returned_nodes} nodes and {context.coverage.returned_relationships} relationships{context.coverage.truncated ? "; more are available." : "."}</p>
            {rawExport && (
              <ul className="node-list">
                {rawExport.items.map((item, index) => (
                  <li key={`${item.claim_id}-${index}`}>
                    <div><strong>{item.raw_text}</strong><small>{item.evidence.map((evidence) => evidence.excerpt).join(" · ")}</small></div>
                    <Status value={item.status} />
                  </li>
                ))}
                {!rawExport.items.length && <li className="empty">No raw story material for this topic.</li>}
              </ul>
            )}
          </section>
          <section className="overview">
            <div><span>Nodes</span><strong>{context.coverage.returned_nodes}</strong></div>
            <div><span>Relationships</span><strong>{context.coverage.returned_relationships}</strong></div>
            <div><span>Disputes</span><strong>{context.disputes.length}</strong></div>
            <div><span>Truncated</span><strong>{context.coverage.truncated ? "Yes" : "No"}</strong></div>
          </section>

          <section className="panel graph">
            <h2>Canonical graph</h2>
            {graphNodes.length ? (
              <GraphView nodes={graphNodes} relationships={context.relationships} onInspect={inspectNode} />
            ) : (
              <p className="empty">No canonical graph objects yet.</p>
            )}
          </section>

          <section className="columns">
            <NodeList title="Entities" nodes={context.entities} label="entity" />
            <NodeList title="Events" nodes={context.events} label="event" />
            <NodeList title="Claims" nodes={context.claims} label="claim" />
          </section>

          <section className="panel">
            <h2>Timeline</h2>
            <ol className="timeline">
              {context.timeline.map((event) => (
                <li key={event.event_id}>
                  <time>{event.temporal.start || "Unknown time"}</time>
                  <strong>{event.title}</strong>
                  <Status value={event.status} />
                </li>
              ))}
            </ol>
          </section>
        </>
      )}

      <section className="panel operator">
        <h2>Ingestion report</h2>
        <form onSubmit={loadReport}>
          <input value={ingestionId} onChange={(event) => setIngestionId(event.target.value)} placeholder="Paste an ingestion UUID" required />
          <button type="submit">Inspect</button>
        </form>
        {report && <pre>{JSON.stringify(report, null, 2)}</pre>}
      </section>
      {report && (
        <section className="panel operator">
          <h2>Resolution decisions</h2>
          <ResolutionDecisionList decisions={resolutionDecisions} />
        </section>
      )}
      {detail && <section className="panel operator"><h2>Canonical inspection</h2><pre>{JSON.stringify(detail, null, 2)}</pre></section>}
    </main>
  );
}
