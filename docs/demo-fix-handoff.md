# Demo / MVP fixes (human summary)

**Branch:** `integration/l1-l2-l3` · **Date:** 2026-07-26  
**Full agent brief:** [`demo-fix-handoff-agent.md`](./demo-fix-handoff-agent.md)

---

## What we fixed

1. **Entity matching no longer drops matches after ~10 entities** — re-ingesting the same organizations no longer creates random duplicates.
2. **Topic context no longer 500s** when filtering by time and an event has no end date.
3. **Voice selection recovers** after a temporary ElevenLabs failure (it used to stick on the fallback forever).
4. **Layer 1 keeps good facts** when one object is invalid — it drops the bad object (or single bad fact), not the whole package/article.
5. **Story conflicts read as real disputes** — e.g. two opposing claims quoted — instead of internal pipeline jargon.
6. **Blueprints no longer ship real event titles** (e.g. “UK general election results”). Labels are built from fictional cast + event type.
7. **New demo corpus** under `fixtures/demo/` — India student protests / exam-leak story with a full cast (students, police, ministry, opposition, press + city). The old UK golden fixtures are unchanged for regression tests.

**Checks:** `PYTHONPATH=backend uv run pytest backend/tests -q` → **78 passed**.

---

## What you get for the demo

| Piece | Result |
|-------|--------|
| Cast | 5 characters + 1 place |
| Arc | Allegations → organising → march met by police |
| Conflict | Ministry denial vs leak claim (confirmed contradiction) |
| Roles | Students = protagonist, ministry = antagonist (stable) |

---

## Still to do (priority)

| Priority | Gap | Status |
|----------|-----|--------|
| Done | Orchestrator `DEMO_MODE` + explicit downstream timeouts | Shipped |
| Done | Paginate `GET /topics` (+ `X-Total-Count`, dashboard `limit=50`) | Shipped |
| Done | Pin Layer 3 artefact dirs to repo root (`artifact_paths.py`) | Shipped |
| Done | Scrub demo claim prose (`Parliament` / entrance-test wording) | Shipped |
| Should | Same candidate-limit bug for events/claims | Open — fine for demo size |
| Should | Ingestion locking under concurrency | Open — only if parallel ingest |
| Blocked | API keys in `.env` | Still required for a live L3 run |
| Later | Audio unit tests, dashboard polish | Nice-to-have |

Ops: preview/delete test topics with [`scripts/purge_test_topics.sql`](../scripts/purge_test_topics.sql), or `docker compose down -v` on a disposable machine.

---

## Decisions to keep

- Don’t replace the UK golden fixtures with the India demo — keep both.
- Don’t put real event titles into blueprints — synthesize labels.
- Don’t reverse the dispute-description change — Layer 3 needs readable conflict text.

---

## How to run the new demo data

1. Start DB + Layer 2 API (`docker compose up -d db`, then uvicorn on 8000).
2. Create the topic from `fixtures/demo/topic.json` (use a unique `topic_key` if re-running).
3. Ingest the three deltas in order (`delta-01` → `delta-02` → `delta-03`).
4. With `.env` keys set, run world builder → blueprint → orchestrator on that `topic_id`.

Offline proof without keys: the pytest file `test_layer3_pipeline.py` already seeds this corpus and asserts cast + blueprint shape.
