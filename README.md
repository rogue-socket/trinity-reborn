# Trinity Reborn — Current Affairs → Story Pipeline

End-to-end MVP that turns researched current-affairs into a provenance-aware knowledge graph (Layers 1–2) and a multi-character fictional story with optional narration (Layer 3).

| Layer | Role | Default port |
|-------|------|--------------|
| Layer 1 | Discover / extract / dedupe / build research packages | via Layer 2 API |
| Layer 2 | Ingest packages, reconcile graph, serve topic context | `8000` |
| Operator dashboard | Inspect topics, replay seeded demo | Vite (see console) |
| World builder | Fictionalize entities into a world bible | `8001` |
| Blueprint assembler | Assemble story blueprint from world + context | `8002` |
| Story generator | Per-character episodes | `8003` |
| Translator | Localize episodes | `8004` |
| Audio generator | ElevenLabs narration | `8005` |
| Orchestrator | Run the Layer 3 chain | `8006` |

## Prerequisites

- Python 3.14+, [uv](https://github.com/astral-sh/uv), Node 24+, Docker
- Copy `.env.example` → `.env` and set keys as needed:
  - `GEMINI_API_KEY` — Layer 1 fact extraction (optional; packages still build without it)
  - `OPENAI_API_KEY` — world builder / story / voice profiles
  - `ELEVENLABS_API_KEY` (+ optional `ELEVENLABS_FALLBACK_VOICE_ID`) — narration
  - `DEMO_MODE=true` — orchestrator defaults `narrate` to on when the field is omitted

Artefact directories (`world_bible/`, `blueprints/`, `episodes/`, `audio/`, `runs/`) resolve under the **repository root** unless you set absolute paths in `.env`.

## Run locally

```sh
docker compose up -d db
uv sync --group dev
uv run alembic upgrade head

# Layer 2 API
PYTHONPATH=. uv run uvicorn backend.main:app --reload --port 8000

# Operator dashboard
npm install --prefix frontend
npm run dev --prefix frontend
```

OpenAPI: `http://localhost:8000/docs`.

### Layer 3 (needs `.env` keys)

From the repo root:

```sh
uv run uvicorn backend.layer3.world_builder_service.main:app --port 8001
uv run uvicorn backend.layer3.blueprint_assembler_service.main:app --port 8002
uv run uvicorn backend.layer3.story_generator_service.main:app --port 8003
uv run uvicorn backend.layer3.translator_service.main:app --port 8004
uv run uvicorn backend.layer3.audio_generator_service.main:app --port 8005
uv run uvicorn backend.layer3.orchestrator_service.main:app --port 8006
```

Then `POST http://localhost:8006/run-topic` with `{"topic_id": "<uuid>"}` (add `"narrate": true` if not using `DEMO_MODE`).

## Demo paths

### A. Operator dashboard (Layer 2 golden)

1. Select **Replay seeded demo** (UK election reconciliation fixture).
2. Confirm entity/event match across the first two deltas.
3. Confirm the third delta keeps both conflicting claims and a dispute.
4. Use **Run context query** / **Load raw export** as in the acceptance checklist below.

### B. Multi-character Layer 3 demo corpus

Rich India student-protest packages live under [`fixtures/demo/`](fixtures/demo/) (separate from the UK golden used by regression tests).

```sh
# Register topic + ingest the three deltas in order against a running Layer 2 API,
# then run world builder → blueprint → orchestrator on the returned topic_id.
# Offline proof without API keys:
PYTHONPATH=. uv run pytest backend/layer3/tests/test_layer3_pipeline.py -k demo -q
```

## Layer 1 → Layer 2 handoff

Layer 1 endpoints on the Layer 2 API: `GET /discover`, `POST /extract`, `POST /deduplicate`, `POST /build-package`. Deliver the package unchanged to `POST /ingestions` for a pre-registered topic. Layer 2 owns canonical IDs. Layer 3 must read **topic context**, not raw Layer 1 packages.

Details: [`docs/layer1-layer2-integration.md`](docs/layer1-layer2-integration.md).

## Documentation

| Doc | Audience |
|-----|----------|
| [`docs/demo-fix-handoff.md`](docs/demo-fix-handoff.md) | Short human summary of recent demo fixes |
| [`docs/demo-fix-handoff-agent.md`](docs/demo-fix-handoff-agent.md) | Full agent pickup brief (fixes, gaps, verify steps) |
| [`docs/layer1-layer2-integration.md`](docs/layer1-layer2-integration.md) | L1↔L2 integration notes |
| [`docs/implementation-audit.md`](docs/implementation-audit.md) | Layer 2 vs PRD audit |
| `*/README.md` under each Layer 3 service | Per-service run notes |

## Verify

```sh
uv run alembic upgrade head
uv run alembic check
uv run ruff check backend
PYTHONPATH=. uv run mypy backend
PYTHONPATH=. uv run pytest backend -q
npm run lint --prefix frontend
npm run typecheck --prefix frontend
npm test --prefix frontend
npm run build --prefix frontend
```

CI runs the same checks on every push/PR (Postgres service + Node 24).

## Demo acceptance checklist (Layer 2)

1. In the dashboard, select **Replay seeded demo**.
2. Confirm one entity and event are reconciled across the first two deltas.
3. Confirm the third delta leaves both conflicting claims visible and creates a dispute.
4. Confirm the timeline is ordered by the event timestamp.
5. Use **Run context query** and verify returned-node / relationship coverage.
6. Use **Load raw export** and verify original claim wording without URLs, publishers, Layer 1 IDs, or package metadata.
7. Inspect the latest ingestion report for reconciliation decisions and processing versions.

## Ops notes

- `GET /topics?limit=50&offset=0` is paginated; total count is in the `X-Total-Count` header.
- Local DBs accumulate test topics quickly. Prefer deleting known test prefixes, or `docker compose down -v` on a disposable machine before a live demo.
- Do not commit `.env` or generated artefacts under `world_bible/`, `blueprints/`, `episodes/`, `audio/`, `runs/`.
