# Project Instructions

## Current State
- Full Layers 1–3 MVP: Layer 1 research pipeline + Layer 2 knowledge graph + Layer 3 storytelling services + operator dashboard.
- Branch of record for the integrated demo: `integration/l1-l2-l3`.
- Session handoffs for the latest demo fixes: `docs/demo-fix-handoff.md` (human) and `docs/demo-fix-handoff-agent.md` (agent).

## Product Constraints
- Preserve every incoming Layer 1 research snapshot exactly as received; canonical graph data is derived and may change.
- Layer 2 owns canonical IDs. Never promote Layer 1 local IDs directly to canonical IDs.
- Preserve conflicting, corrected, superseded, and retracted claims with provenance. Do not collapse them into a single asserted fact.
- Keep entity and event resolution conservative and reversible. Prefer separate graph objects over an incorrect merge.
- Distinguish reported, attributed, inferred, interpretive, disputed, and observed information in data models and retrieval output.
- Do not infer causality from temporal sequence alone.
- Retain source-to-claim-to-graph-object provenance and label sensitive or uncertain information for downstream consumers.
- Layer 3 blueprints/episodes must not leak real-world entity labels or unmapped place names.

## Working Style
- Make surgical changes and match the established style.
- Do not reformat unrelated files.
- Do not edit secrets, generated files, or the PRD without an explicit request.
- Ask before destructive database, filesystem, or Git operations.

## Verification
- Start PostgreSQL: `docker compose up -d db`.
- Apply database migrations: `uv run alembic upgrade head`.
- Run backend tests: `PYTHONPATH=backend:. uv run pytest backend/tests -q`.
- Run the local API: `PYTHONPATH=backend uv run uvicorn app.main:app --reload`.
- Run the operator dashboard: `npm run dev --prefix frontend`.
- Build the operator dashboard: `npm run build --prefix frontend`.
- Check Layer 3: `uv run ruff check <service dirs>` and `PYTHONPATH=. uv run mypy <service dirs>`.
- Run the narrowest relevant check first.

## Layer 3 services
- One `uv` environment covers every layer; there are no per-service requirements files.
- Ports: Layer 2 API 8000, world builder 8001, blueprint assembler 8002, story generator 8003, translator 8004, audio generator 8005, orchestrator 8006.
- Start one with `uv run uvicorn <service>.main:app --port <port>` from the **repository root**.
- Artefact dirs resolve via `artifact_paths.py` under the repo root (`world_bible/`, `blueprints/`, `episodes/`, `audio/`, `runs/`).
- Only the world builder and blueprint assembler call Layer 2; the rest chain through files.
- `prds/fixture-topic-context.json` is the agreed shape of `GET /topics/{id}/context`. `backend/tests/test_layer3_contract.py` enforces it; change both together.
- Multi-character demo packages: `fixtures/demo/` (do not replace the UK golden under `fixtures/`).

## Session Docs
- `handoffs/*` — dated local session handoffs, when present (gitignored).
- `backlog.md` — living TODO. Tags: `[active]`, `[next]`, `[blocked: <reason>]`, no tag = someday.
