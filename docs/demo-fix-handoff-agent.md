# Demo / MVP fix handoff (agent v1)

**Branch:** `integration/l1-l2-l3`  
**Date:** 2026-07-26  
**Audience:** Code agents continuing this work  
**Companion:** human-readable summary in [`demo-fix-handoff.md`](./demo-fix-handoff.md)

This document is the complete pickup brief: what was broken, what was changed, how to verify, and every remaining gap with enough detail to implement without re-deriving context.

---

## 1. Goal and constraints

Hackathon / demo MVP. Prefer working and non-breaking over perfect. Product constraints from `AGENTS.md` / Layer 2 PRD still apply:

- Preserve Layer 1 packages as received; Layer 2 owns canonical IDs.
- Keep conflicting / disputed claims; do not collapse them.
- Conservative entity/event resolution.
- Distinguish epistemic statuses in retrieval output.
- Layer 3 must not leak real-world labels into story artifacts.

Verification baseline after these changes:

```bash
docker compose up -d db
uv run alembic upgrade head
PYTHONPATH=backend uv run pytest backend/tests -q   # expected: 78 passed
uv run ruff check backend audio_generator_service blueprint_assembler_service
uv run mypy backend/app
```

---

## 2. Files touched in this session

| Path | Change |
|------|--------|
| `backend/app/services/canonicalization.py` | Entity candidate retrieval rewritten; `_canonical_entity_names` removed |
| `backend/app/api/retrieval.py` | Null temporal end; dispute prose; `asserted_by` on claims; dispute parties |
| `backend/app/services/layer1.py` | Partial delivery + per-object fact skip |
| `audio_generator_service/audio.py` | Voice list cache no longer stores failures |
| `blueprint_assembler_service/assembler.py` | Synthesized event labels; prose fictionalization helper |
| `fixtures/demo/*` | New richer demo corpus (does **not** replace `fixtures/` golden regression) |
| `backend/tests/test_ingestions.py` | Candidate window + open-ended event tests |
| `backend/tests/test_layer1_integration.py` | Partial delivery + dangling-ref tests |
| `backend/tests/test_layer3_contract.py` | Dispute description must quote claims |
| `backend/tests/test_layer3_pipeline.py` | Title leak assertion + demo corpus ensemble tests |

**Not committed / not part of this fix set:** untracked `AGENTS.md` (repo bootstrap; leave alone unless asked).

---

## 3. Completed fixes (implementations)

### 3.1 Entity reconciliation past ~10 entities per type

**Symptom:** Re-ingesting N identical organizations with `N > CANDIDATE_LIMIT` (10) created duplicates for entities that sorted late by `CanonicalEntity.id`.

**Root cause:** `_entity_candidates` loaded an arbitrary window of 10 entities ordered by UUID, then matched in Python. Exact matches outside that window were invisible.

**Fix:** Replaced `_entity_candidates` + per-candidate `_canonical_entity_names` with `_entity_name_index(session, topic_id, entity_type)`:

- Joins `CanonicalEntity` → `LocalIdMapping` → `RawPackage` → outer `EntityMention` for the topic + type.
- Builds `{entity_id → (entity, set of normalized names)}` including canonical label and all mention aliases.
- `_matching_entity` / `_possible_entity_match` consume that index (no arbitrary row limit on retrieval).

**Note:** `CANDIDATE_LIMIT` remains in `policy.py` and is still used for other candidate queries (claims, events, etc.). Only entity name matching was unblocked.

**Test:** `test_resolves_exact_entity_matches_beyond_the_candidate_window` in `test_ingestions.py`.

**Still open under this area:** Event / claim / relationship candidate paths still use `.limit(CANDIDATE_LIMIT)`. Same class of bug can recur for those object types at scale. Not demo-blocking for the new corpus.

---

### 3.2 `/topics/{id}/context` 500 on open-ended temporal end

**Symptom:** `ValueError: Invalid isoformat string: 'None'` when `time_start` / `time_end` filters applied and `temporal.end` was JSON `null`.

**Root cause:** `_in_time_range` used `temporal.get("end", value)`. Key present with value `None` skips the default; `str(None)` → `"None"`.

**Fix:** `str(temporal.get("end") or value)`.

**Endpoint note:** `/timeline` does **not** take `time_start`/`time_end`. The bug is on `/context` (and graph-expansion paths that call `_in_time_range` on relationships).

**Test:** `test_filters_an_open_ended_event_by_time_without_failing`.

---

### 3.3 ElevenLabs voice cache poisoning

**Symptom:** One failed `/v2/voices` call cached `[]` forever; every later character fell back to `ELEVENLABS_FALLBACK_VOICE_ID`.

**Fix:** Cache only non-empty success. On failure return `[]` without writing the cache. Treat empty cache as “not ready” (`if _voices_cache:`).

**File:** `audio_generator_service/audio.py` → `_voices()`.

**Test gap:** No automated test file for audio service yet; verified with a mocked `httpx.get` probe. Adding a unit test under `backend/tests/` or a service-local test is still open.

---

### 3.4 Layer 1 delivery: drop rejected objects instead of failing the package

**Symptom:** `_validate_for_delivery` raised `PackageValidationError` if **any** object was rejected by `validate_objects`, discarding an entire otherwise-good package.

**Fix:** If report status is fully `"rejected"`, still raise. Otherwise filter each collection using `LOCAL_TYPES` / `REQUIRED_FIELDS` and return `package.model_copy(update=retained)`. Log dropped IDs.

**Important:** `validate_objects` already transitively rejects dependents of rejected objects, so filtering on its report does not leave dangling refs.

**Test:** `test_one_rejected_object_is_dropped_rather_than_failing_the_package` (ontology-violating `LOCATED_AT` between two entities).

---

### 3.5 Layer 1 normalization: skip bad facts, keep the article

**Symptom:** One invalid claim/relationship/evidence in a Gemini payload caused `_normalize_facts` to raise; caller logged and skipped **all** facts for that article.

**Fix:**

- Duplicate local IDs → omit that ID from remap maps (all claimants skipped).
- Bad evidence offsets / wrong article → skip that evidence, rebuild surviving evidence map.
- Claims/relationships with missing endpoints → `_skipped(...)` + continue.
- Soft `remap` keeps only surviving IDs instead of raising.

**Still fatal:** Pydantic `FactPayload.model_validate` shape failures (caller still excludes that article).

**Test:** `test_a_dangling_reference_drops_one_fact_not_the_whole_article`.

---

### 3.6 Dispute descriptions for Layer 3 storytelling

**Symptom:** Dispute `description` was the internal `RelationshipAssertion.rationale` (e.g. “Same structured subject, predicate, and temporal scope with incompatible values.”). Blueprint uses this as `central_conflict`.

**Fix:** `_dispute_description(claim_texts)` quotes conflicting claim texts:

```text
Accounts conflict: “…” versus “…”.
```

**Also:** Claims in context now expose `asserted_by` (canonical entity ID of Layer 1 `asserted_by_entity_id`). Dispute `related_entity_ids` = subject ∪ asserted_by for related claims (needed so world-builder antagonist assignment works when both sides share the same subject).

**Tests:**

- `test_dispute_descriptions_quote_the_conflicting_claims`
- Demo pipeline tests below exercise two-party dispute → antagonist.

**Leak follow-on:** Assembler now runs `_fictionalize(...)` on `central_conflict` and disputed-thread descriptions (case-insensitive entity-label swap). Real nouns never extracted as entities can still leak.

---

### 3.7 Event titles must not enter blueprints

**Symptom:** `_fictional_event_label` only substring-replaced entity labels inside the real title. Titles like `"UK general election results"` contain no entity label → real title shipped unchanged.

**Fix:** Ignore real title. Synthesize:

```text
{EventType}: {fictional participant names}
```

or just capitalized type if no mapped participants.

**Test:** Extended `test_the_blueprint_never_repeats_the_real_topic` to assert `"uk general election results"` absent from blueprint JSON. Confirmed fails on old assembler, passes on new.

---

### 3.8 Richer demo corpus (separate fixtures)

**Problem:** Existing `fixtures/{topic,delta-0*}.json` is a minimal UK-election reconciliation fixture (one castable entity). Layer 3 needs a multi-character cast. Expanding in place would break `test_golden_demo.py` expectations under `fixtures/expected/`.

**Solution:** New corpus under `fixtures/demo/`:

| File | Role |
|------|------|
| `topic.json` | `india-student-protests-2026` |
| `delta-01-initial.json` | Allegations + organising; students, ministry, capital city |
| `delta-02-escalation.json` | March, police, opposition, press; corroborates leak; extra student claim for role tie-break |
| `delta-03-denial.json` | Ministry denial (`exam_leak_occurred` = `false` vs prior `true`) → `confirmed_contradiction` |

Design constraints discovered while building:

1. Contradiction matching requires **identical** canonical subject, `predicate_candidate`, and `temporal_scope`, with conflicting `object_ref_or_value` (`claim_values_conflict` for literals).
2. Role assignment (`calculate_roles`) picks protagonist by claim subject count; ties break on entity UUID → **non-deterministic** cast. Demo corpus gives students more claim subjects than the ministry so protagonist is stable.
3. Antagonist requires protagonist ∈ dispute `related_entity_ids` and another party present → needed `asserted_by` in dispute parties.

**Tests:**

- `test_the_demo_corpus_casts_an_ensemble_with_opposed_leads`
- `test_the_demo_blueprint_does_not_name_the_real_actors`

**Probe expectations (after ingest of demo corpus):**

- 6 entities (5 castable + capital city place)
- 3 events, 1 confirmed contradiction
- Blueprint: 5 perspectives, protagonist = students side, antagonist = ministry side

---

## 4. Remaining gaps

### Gaps A–D — **done in follow-up commit**

| Gap | Resolution |
|-----|------------|
| A Narrate / timeouts | `DEMO_MODE` env; `_post(..., timeout=client.timeout)`; documented in README / `.env.example` |
| B Topic pagination | `GET /topics?limit=&offset=` + `X-Total-Count`; dashboard uses `limit=50`; `display_name` on topic responses; `scripts/purge_test_topics.sql` |
| C Artefact dirs | Shared `artifact_paths.py`; all Layer 3 `config.py` files use it |
| D Demo noun scrub | `fixtures/demo` claim/evidence prose no longer uses Parliament / national-entrance wording; pipeline deny-list extended |

### Gap E — Event / claim candidate limits still truncate `[should fix]`

Same pattern as 3.1 for `_contradicted_claim`, event matching, etc. (`CANDIDATE_LIMIT = 10`). Demo corpus is small enough; large live L1 packages can miss contradictions/matches.

**Work:** Name/structure-keyed queries or raise limit with tests mirroring `test_resolves_exact_entity_matches_beyond_the_candidate_window`.

---

### Gap F — Ingestion concurrency / advisory locks `[should fix]`

Earlier review: mid-handler `session.commit()` can release transaction-scoped advisory locks before reconciliation finishes, weakening same-topic mutual exclusion.

**Where:** `backend/app/api/ingestions.py` (+ any nested commits in materialization).

**Work:** Hold one transaction for the critical section, or use session-level locks. Add/extend `test_serializes_concurrent_same_topic_entity_ingestion` under load.

**Demo impact:** Low if demo is single-threaded ingest; higher if parallel packages.

---

### Gap G — Environment / keys for live L3 demo `[blocked: secrets]`

No committed `.env`. Need at minimum:

- `GEMINI_API_KEY` (L1 facts)
- `OPENAI_API_KEY` (world builder, story, voice profile)
- `ELEVENLABS_API_KEY` (+ optional `ELEVENLABS_FALLBACK_VOICE_ID`)
- Service URLs if not default localhost ports (8000–8006)

Copy from `.env.example`. Do not commit secrets.

---

### Gap H — Golden UK fixtures vs PRD fixture mismatch `[someday / product]`

- `fixtures/` + `test_golden_demo.py` = UK election reconciliation golden.
- `prds/fixture-topic-context.json` = India protests shape Layer 3 contracts against.
- `fixtures/demo/` now implements the India shape as ingestible packages.

Do **not** silently replace the UK golden without regenerating `fixtures/expected/*` and updating golden demo tests. Prefer keeping both.

---

### Gap I — Audio / assembler unit tests sparse `[nit]`

Pipeline tests cover the L2→L3 seam with faked OpenAI. Still missing:

- Direct unit tests for `_voices()` retry/cache
- Direct unit tests for `_fictional_event_label` / `_fictionalize`

---

### Gap J — Dashboard demo replay / inspectNode `[nit]`

Earlier analysis flagged frontend `inspectNode` / `replayDemo` edge cases. Not touched this session. Revisit if operator dashboard is part of the live demo path.

---

## 5. How to demo with the new corpus

```bash
# Terminal A — Layer 2
docker compose up -d db
uv run alembic upgrade head
PYTHONPATH=backend uv run uvicorn app.main:app --reload --port 8000

# Seed demo topic (example)
# POST /topics with fixtures/demo/topic.json (unique topic_key if re-running)
# POST /ingestions for delta-01, delta-02, delta-03 in order

# Terminal B+ — Layer 3 (requires .env)
uv run uvicorn world_builder_service.main:app --port 8001
uv run uvicorn blueprint_assembler_service.main:app --port 8002
# … story 8003, translator 8004, audio 8005, orchestrator 8006

# Then POST orchestrator /run with topic_id
```

Or rely on `test_the_demo_corpus_casts_an_ensemble_with_opposed_leads` as the offline proof the graph→cast→blueprint path works without API keys.

---

## 6. Decision log (do not silently reverse)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Entity candidates | Full topic name index, not SQL `LIMIT 10` | Correctness over bounded scan; demo corpus needs reliable merges |
| Event labels | Synthesize from type + fictional names | Real titles leak nouns not present as entities |
| Demo corpus | New `fixtures/demo/`, keep UK golden | Avoid rewriting four expected JSON files / blunting reconciliation regression |
| Dispute prose | Quote claim texts | Layer 3 needs story-usable central conflict |
| Dispute parties | subject ∪ asserted_by | Antagonist assignment requires both sides |

---

## 7. Suggested next agent work

1. Gap E (event/claim candidate windows) if live L1 packages get large.
2. Gap F (ingestion advisory locks) if the demo script parallelizes ingest.
3. Gap G (operator `.env` keys) before any live narration demo.
4. Keep CI green: contradiction status assertions must `.order_by(id)` (Postgres row order is not insertion order).

When closing a gap: update this file and [`demo-fix-handoff.md`](./demo-fix-handoff.md).
