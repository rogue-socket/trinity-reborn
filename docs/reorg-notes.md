# Repository reorganization notes

This pass moves code and rewires paths only; it does not intentionally change
runtime behavior, API contracts, database schema, or service configuration.

## Layout choices

- `backend/layer1/` contains Layer 1's research API, discovery/extraction/
  deduplication/package-building service, and its tests.
- `backend/layer2/` contains ingestion, canonicalization, retrieval, data
  models, Layer 2 contracts, migrations, and Layer 2 tests. The root
  `alembic.ini` points to those migrations so standard Alembic commands work
  from a fresh repository checkout.
- `backend/layer3/` contains the six Layer 3 service packages and their
  integration tests.
- `backend/shared/` contains the database helper and artifact-path utilities.
  These are imported as `backend.shared.*`, which avoids copies while keeping
  Layer 1, Layer 2, and Layer 3 package boundaries explicit.
- `backend/main.py` remains the combined Layer 1 + Layer 2 FastAPI entrypoint.
  The launch path is now `backend.main:app`.

## Existing discrepancy noted, not fixed

`docs/full-architecture.md` still states that the combined backend has no
`/health` route. `backend/main.py` does expose that route. This is a stale
documentation claim from before the preceding audit pass; it is recorded here
rather than changed as part of this move-only pass.
