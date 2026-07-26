# Trinity Reborn bug audit

Audit date: 2026-07-26. Scope: `integration/l1-l2-l3`; no files or directories will be moved, renamed, or restructured in this pass.

## Baseline before changes

The repository had two pre-existing local-environment blockers. A PostgreSQL 16 container from an older `layer2_mock` workspace already occupied host port 5432 with different credentials, preventing this repository's Compose database from starting. To validate the repository schema without altering that container, the equivalent Alembic commands were run against an isolated PostgreSQL 17 audit container on port 5433 using a process-local `DATABASE_URL` override. Windows Application Control also blocked mypy's compiled import path and `selectolax`'s native `lexbor` module.

| README Verify command | Baseline result |
| --- | --- |
| `uv run alembic upgrade head` | **Failed at default port 5432**: password authentication failed for `trinity`; **passed against isolated port 5433 audit DB**. |
| `uv run alembic check` | **Failed at default port 5432** for the same reason; **passed against isolated port 5433 audit DB** (`No new upgrade operations detected`). |
| `uv run ruff check backend` | **Passed**. |
| `PYTHONPATH=. uv run mypy backend` | **Failed before analysis**: Windows Application Control blocked mypy while importing `base64`. |
| `PYTHONPATH=. uv run mypy backend/layer3` | **Passed**: 32 source files. |
| `PYTHONPATH=. uv run pytest backend -q` | **Failed during collection**: importing `googlenewsdecoder` imported blocked native `selectolax.lexbor`. |
| `npm run lint --prefix frontend` | **Passed**. |
| `npm run typecheck --prefix frontend` | **Passed**. |
| `npm test --prefix frontend` | **Passed**: 1 file, 3 tests. |
| `npm run build --prefix frontend` | **Passed**. |

The backend mypy failure is environmental (the executable fails before it can inspect repository source). The backend pytest failure exposes a repository robustness bug because an optional URL decoder is imported eagerly by the entire backend application.

## Confirmed bugs to fix

| ID | Severity | Location | Incorrect behavior | Planned verification |
| --- | --- | --- | --- | --- |
| B1 | High | `backend/main.py` | The backend exposes no `GET /health`, while `backend/layer3/orchestrator_service/main.py` always probes `{LAYER2_BASE_URL}/health`. A healthy Layer 2 API is therefore reported unreachable. | Add `GET /health` returning `{"status":"ok"}` and test it with FastAPI `TestClient`; exercise orchestrator health with a mocked downstream. |
| B2 | High | `backend/layer1/service.py` | Importing `googlenewsdecoder` at module load imports an optional native dependency. If that dependency cannot load, **all** backend routes fail to import—even routes unrelated to extraction. | Defer/fail-soft the decoder import; test that the app imports and non-Google-News extraction remains available when the decoder is unavailable. |
| B3 | High | `backend/layer2/services/canonicalization.py` (`_matching_event`, `_contradicted_claim`, `_progressed_claim`) | Each search reads only the first `CANDIDATE_LIMIT` rows ordered by UUID, then applies the decisive temporal/participant/value predicate in Python. A matching event, contradiction, or progression after that arbitrary window is missed at scale, producing duplicate events or wrong claim classification. | Remove the arbitrary window from deterministic match scans and add regression tests with more than `CANDIDATE_LIMIT` candidates where the valid candidate sorts later. |
| B4 | Medium | Layer 3 atomic writers: `backend/layer3/world_builder_service/world_builder.py`, `backend/layer3/blueprint_assembler_service/assembler.py`, `backend/layer3/story_generator_service/generator.py`, `backend/layer3/translator_service/translator.py`, `backend/layer3/audio_generator_service/audio.py`, `backend/layer3/orchestrator_service/orchestrator.py` | Every writer uses one predictable `*.tmp` name. Concurrent requests for the same artifact can overwrite or replace each other's temporary file, yielding failed writes or mismatched content. Crash safety for a single writer is good (the previous destination remains until `replace`), but multi-writer safety is not. | Use unique same-directory temporary files and `replace`; add a focused writer test where practical, plus retain the full suite. |
| B5 | Low | `docs/full-architecture.md` | The newly added architecture document says `.env.example` is missing. It exists at repository root (it is ignored by Git, so ordinary `rg --files` did not show it). The root README's copy instruction is accurate. | Correct the architecture document and verify `.env.example` is present and documents the actual configuration names. |

## Investigated leads that are not bugs in the current code

- **Entity candidate window:** fixed already. `_entity_name_index()` scans every entity of the requested type in the topic; `test_resolves_exact_entity_matches_beyond_the_candidate_window` covers this.
- **Relationship candidate window:** `_matching_relationship()` applies all comparison fields (topic, endpoint types/IDs, relation type, and temporal JSON) in SQL. Any row in its bounded result is equivalent for the exact-match decision, so the limit does not cause a false no-match. The limit remains a performance bound, not a correctness window.
- **Exact claim wording window:** `_matching_claim()` currently limits rows, but its SQL predicate already requires identical case-folded text; any returned row is an exact claim match. Its behavior does not depend on a later candidate. (The structured contradiction/progression scans are separately buggy as B3.)
- **Ingestion advisory lock:** after `pg_advisory_xact_lock()` is acquired in `backend/layer2/api/ingestions.py`, the normal ingestion path does not commit until after `materialize_new_canonical_objects()`. The only post-lock early commit is the idempotent retry/closed-topic reopen path, which does no reconciliation after the commit. The lock is not released before normal reconciliation finishes.
- **Retry/backoff loops:** Translator and ElevenLabs TTS each make one initial attempt plus three retries, sleeping 1, 2, and 4 seconds only for their intended retryable failures (Gemini 429; ElevenLabs 429/5xx). The OpenAI loops make one initial attempt plus two transient-error retries. Layer 1 discovery/extraction currently has no retry loop; it reports a failed discovery or failed article instead of retrying. No off-by-one error was found in an implemented loop.
- **File caches and crash consistency:** world/character reuse validates Pydantic JSON before reuse; successful Episode cache states exclude `failed`; and the current replace-based writes preserve a pre-existing destination if a single process crashes before replacement. B4 covers the remaining concurrent-writer race. Voice-list failures are intentionally not cached, so a transient failed list fetch does not poison later voice selection.
- **Frontend/backend signatures:** `frontend/src/App.jsx` uses the current query/body names for `/topics`, `/topics/{id}/context`, `/raw-export`, `/ingestions/{id}`, entity context, claim evidence, and demo ingestion. No mismatch was found.

## After-fix results

The full README verification sequence was rerun after every fix. The default
port-5432 Compose commands remain blocked by an unrelated pre-existing local
PostgreSQL container, so the identical Alembic and backend-test commands used
the isolated audit database at port 5433 via `DATABASE_URL`; no repository
configuration was changed to work around that host conflict.

| README Verify command | Before | After |
| --- | --- | --- |
| `uv run alembic upgrade head` | Failed at occupied default port; passed on the audit DB. | **Passed** on the audit DB. |
| `uv run alembic check` | Failed at occupied default port; passed on the audit DB. | **Passed** on the audit DB (`No new upgrade operations detected`). |
| `uv run ruff check backend` | 0 violations. | **0 violations**. |
| `PYTHONPATH=. uv run mypy backend` | Blocked before analysis by host Application Control. | **Passed: 19 source files**. |
| `PYTHONPATH=. uv run mypy backend/layer3` | Passed: 32 source files. | **Passed: 32 source files**. |
| `PYTHONPATH=. uv run pytest backend -q` | Collection failed before any test ran because the optional decoder was imported eagerly. | **Passed: 88 tests** (2 non-failing `newspaper4k` warnings). |
| `npm run lint --prefix frontend` | Passed. | **Passed**. |
| `npm run typecheck --prefix frontend` | Passed. | **Passed**. |
| `npm test --prefix frontend` | Passed: 1 file, 3 tests. | **Passed: 1 file, 3 tests**. |
| `npm run build --prefix frontend` | Passed. | **Passed**. |

Focused regression coverage added in this pass:

- backend `/health` response for the orchestrator's Layer 2 probe;
- fail-soft unavailable Google News decoder behavior;
- matching a later event, contradiction, and claim progression after the former 10-row window; and
- concurrent artifact writes using unique temporary paths.

## Follow-up

The port-5432 conflict has been resolved. The confirmed old
`layer2_mock-postgres-1` Compose container was removed with
`docker compose -f layer2_mock/docker-compose.yml down` without `-v`, so its
`layer2_mock_layer2_mock_postgres` volume was preserved. The repository's
default `docker compose up -d db` path now publishes port 5432 and accepts the
configured `trinity` / `trinity_reborn` credentials. With no `DATABASE_URL`
override, `uv run alembic upgrade head`, `uv run alembic check`, and the
README's backend pytest command all completed successfully: **88 tests passed**.
