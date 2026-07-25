# Current Affairs Knowledge Graph - Layer 2

Local FastAPI, PostgreSQL, and React MVP for receiving immutable Layer 1 research deltas and serving a canonical, provenance-aware graph to Layer 3.

## Run locally

```sh
docker compose up -d db
uv run alembic upgrade head
PYTHONPATH=backend uv run uvicorn app.main:app --reload
npm run dev --prefix frontend
```

The API exposes OpenAPI at `http://localhost:8000/docs`; the dashboard runs on the Vite URL printed by the final command.

## Demo acceptance checklist

1. In the dashboard, select **Replay seeded demo**.
2. Confirm one entity and event are reconciled across the first two deltas.
3. Confirm the third delta leaves both conflicting claims visible and creates a dispute.
4. Confirm the timeline is ordered by the event timestamp.
5. Use **Run context query** and verify the returned-node and relationship coverage.
6. Use **Load raw export** and verify original claim wording is present without URLs, publishers, Layer 1 IDs, or package metadata.
7. Inspect the latest ingestion report to view the reconciliation decisions and processing versions.

## Verify

```sh
uv run alembic upgrade head
uv run alembic check
uv run ruff check backend
PYTHONPATH=backend uv run mypy backend/app
PYTHONPATH=backend uv run pytest backend/tests -q
npm run lint --prefix frontend
npm run typecheck --prefix frontend
npm test --prefix frontend
npm run build --prefix frontend
```
