# Layer 1–Layer 2 integration handoff

## Purpose

This branch combines the external Layer 1 research prototype with the Layer 2
knowledge-graph service. Layer 1 gathers and normalizes research; Layer 2 stores
the incoming package immutably, assigns canonical IDs, and provides the retrieval
surface intended for Layer 3.

Layer 3 must consume Layer 2 retrieval endpoints. It must not read Layer 1 package
records directly.

## What changed

### Layer 1 research API

The FastAPI service now exposes these endpoints alongside the Layer 2 API:

| Endpoint | Responsibility |
| --- | --- |
| `GET /discover` | Query Google News RSS and persist discovery history. |
| `POST /extract` | Resolve Google News links and extract article text with Trafilatura, falling back to Newspaper4k. |
| `POST /deduplicate` | Group similar successful extractions while retaining the representative and duplicate records. |
| `POST /build-package` | Produce the Layer 1 research package accepted unchanged by `POST /ingestions`. |

Discovery attempts and their result metadata are persisted in the new
`discovery_requests` and `discovered_articles` tables. Persistence is best effort:
a successful discovery response is not discarded if writing its audit history fails.

### L1 package contract and provenance

- Layer 1 emits sources, articles, evidence, entities, events, claims, and
  relationship candidates in the existing Layer 2 ingestion envelope.
- Every successful source article is retained in the package. Deduplication only
  selects which representative receives fact extraction; it does not discard
  source provenance.
- Both the original discovery URL and the resolved publisher canonical URL are
  retained, as are publisher, publication date, content, and a SHA-256 content hash.
- Layer 1 local IDs remain package-local. Layer 2 creates and returns canonical IDs.
- Generated facts are checked against the Layer 2 object validator before Layer 1
  returns the package, so invalid model output is excluded rather than sent to
  ingestion.

### Fact extraction

When `GEMINI_API_KEY` is set, `POST /build-package` uses the current
`google-genai` SDK for structured, evidence-constrained extraction. It normalizes
the old Layer 1 `label` field to Layer 2's required entity `name` field, validates
temporal and epistemic values, and limits concurrent model calls to three.

Without the key, package building still succeeds with sources and articles so raw
research is preserved, but it contains no extracted graph facts.

### Dependencies and configuration

- Added RSS, URL resolution, extraction, similarity, and Gemini dependencies to
  `pyproject.toml` and `uv.lock`.
- Added `.env.example` with `GEMINI_API_KEY=`.
- Added migration `d2e4f6a8b0c2_add_layer1_discovery.py`.
- Updated the README with the L1→L2 API flow and the Gemini configuration note.

## Local setup

```bash
docker compose up -d db
uv run alembic upgrade head
export GEMINI_API_KEY=... # required for live fact extraction
PYTHONPATH=backend uv run uvicorn app.main:app --reload
npm run dev --prefix frontend
```

Register the topic in Layer 2 before posting a package for that topic to
`POST /ingestions`.

## Verification completed

- `PYTHONPATH=backend uv run pytest backend/tests -q` — 55 passed.
- `npm test --prefix frontend` — 3 passed.
- `npm run build --prefix frontend` — passed.
- `uv run ruff check backend`, `PYTHONPATH=backend uv run mypy backend/app`, and
  `uv run alembic check` — passed.
- Runtime audit verified live article extraction, deduplication, package creation,
  Layer 2 ingestion, timeline/context/entity retrieval, raw export, and CORS.

## Remaining work before a fully live Layer 3 flow

1. Fix the Layer 1 RSS client's Python SSL trust-store failure. During the runtime
   audit, Google News RSS was reachable with `curl`, but `feedparser` failed
   certificate verification and `GET /discover` returned 502.
2. Configure `GEMINI_API_KEY`, then repeat the live discovery → extraction →
   fact extraction → ingestion flow and inspect the resulting graph data.
3. Add or explicitly defer a Layer 1 operator workflow. The current dashboard is
   Layer 2-only; Layer 1 is currently operated through its API.
4. Before scale testing the dashboard, consider pagination or filtering for
   `GET /topics`; it currently returns the full topic list in one response.

## Deliberately unchanged

- Layer 2 ingestion remains the authority for topic registration and canonical ID
  ownership.
- No direct Layer 1 database access is exposed to Layer 3.
- No automatic entity/event merge policy was added; Layer 2 keeps resolution
  conservative and reversible.
