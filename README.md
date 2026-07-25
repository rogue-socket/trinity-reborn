# Trinity Reborn

Trinity Reborn is a three-layer current-affairs storytelling pipeline:

1. **Layer 1 — research and ingestion:** gathers source material and sends structured, self-contained research deltas.
2. **Layer 2 — knowledge graph:** preserves incoming packages, reconciles them into a canonical, provenance-aware graph, and provides retrieval APIs.
3. **Layer 3 — storytelling:** queries Layer 2 and turns its context into narratives, podcasts, or other creative outputs.

This repository contains the Layer 2 hackathon MVP specification and the current FastAPI backend scaffold.

## Product documents

- [`prds/Current Affairs Knowledge Graph Layer PRD.pdf`](prds/Current%20Affairs%20Knowledge%20Graph%20Layer%20PRD.pdf) — original product requirements.
- [`prds/current-affairs-knowledge-graph-layer.md`](prds/current-affairs-knowledge-graph-layer.md) — implementation-ready Layer 2 specification.

The Markdown specification is the development reference. It defines the Layer 1 delta contract, immutable raw storage, canonical graph model, reconciliation policy, PostgreSQL data model, Layer 3 APIs, operator dashboard, and test plan.

## MVP boundaries

- Layer 1 sends independent deltas for a Layer 2-registered topic; it does not need prior canonical IDs.
- Layer 2 owns canonical IDs and preserves every input package exactly as received.
- Conflicting, corrected, retracted, and superseded claims remain queryable with explicit status.
- Layer 3 talks only to Layer 2 APIs. It receives graph context and permitted raw story material, never Layer 1 source URLs, local IDs, or delivery metadata.
- The MVP runs locally with FastAPI, PostgreSQL, and a small React operator dashboard.

## Planned local development

The implementation specification calls for:

- a FastAPI ingestion and retrieval service;
- PostgreSQL for raw package and graph storage;
- a React dashboard for graph evolution and Layer 3-style query inspection;
- a three-delta seeded scenario covering initial population, an update, and a conflict or correction.

See the Markdown specification for API contracts, schema requirements, reconciliation rules, and acceptance criteria.

## Backend development

### Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

### Run locally

```powershell
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

The health check is available at `GET /health`.

## Layer 1 service ownership and API contract

The following folders under `backend/app/services/` belong to the Research Engine
Layer 1 team:

- `discovery/`
- `extraction/`
- `deduplication/`
- `package_builder/`

Layer 2 Knowledge Graph work must live in a separate service folder, such as
`backend/app/services/knowledge_graph/` or `backend/app/services/graph_engine/`.
It should not modify Layer 1 service files.

Layer 1 exposes these API endpoints:

- `GET /discover` — retrieves current-affairs article metadata for a topic.
- `POST /extract` — extracts article text and metadata from discovered URLs.
- `POST /deduplicate` — groups extracted articles by underlying story.
- `POST /build-package` — deduplicates articles and builds a Layer 2 research package.
