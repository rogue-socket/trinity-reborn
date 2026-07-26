# Trinity Reborn: Implemented Architecture

This document describes the checked-in implementation, not the intended PRD design. It is grounded in route decorators, Pydantic models, database migrations, and runtime configuration in this repository as of 2026-07-26. Source locations are included so each statement can be verified directly.

## 1. System overview

Trinity Reborn is a current-affairs-to-fiction pipeline. Layer 1 discovers, extracts, deduplicates, and optionally fact-extracts article material into a research package; Layer 2 stores that package and reconciles it into a provenance-aware PostgreSQL graph; Layer 3 consumes Layer 2's topic-context API to create a fictional world bible, deterministic story blueprint, English character episodes, translations, and optional narrated audio. The split lets the graph preserve real-world evidence and uncertainty while the downstream storytelling services work from an explicit context contract and persist separate fictional artifacts. The combined Layer 1+2 FastAPI application is [`backend/main.py`](../backend/main.py); the Layer 3 services are separate FastAPI applications.

## 2. Service inventory

| Service | Directory | Port | Purpose | Entrypoint |
| --- | --- | ---: | --- | --- |
| Layer 1 + Layer 2 API | `backend/` | 8000 (documented launch port) | Research tools, package ingestion, canonical graph retrieval, and operator-facing APIs | [`backend/main.py`](../backend/main.py) |
| World builder | `backend/layer3/world_builder_service/` | 8001 | Fetches a topic context and creates/extends a fictional World Bible | [`backend/layer3/world_builder_service/main.py`](../backend/layer3/world_builder_service/main.py) |
| Blueprint assembler | `backend/layer3/blueprint_assembler_service/` | 8002 | Deterministically turns context plus World Bible into a Story Blueprint | [`backend/layer3/blueprint_assembler_service/main.py`](../backend/layer3/blueprint_assembler_service/main.py) |
| Story generator | `backend/layer3/story_generator_service/` | 8003 | Produces one English episode per blueprint character | [`backend/layer3/story_generator_service/main.py`](../backend/layer3/story_generator_service/main.py) |
| Translator | `backend/layer3/translator_service/` | 8004 | Adds cached Gemini translations to an episode | [`backend/layer3/translator_service/main.py`](../backend/layer3/translator_service/main.py) |
| Audio generator | `backend/layer3/audio_generator_service/` | 8005 | Assigns a voice and creates ElevenLabs MP3 narration | [`backend/layer3/audio_generator_service/main.py`](../backend/layer3/audio_generator_service/main.py) |
| Orchestrator | `backend/layer3/orchestrator_service/` | 8006 | Calls the Layer 3 services in order and records run outcomes | [`backend/layer3/orchestrator_service/main.py`](../backend/layer3/orchestrator_service/main.py) |
| Operator dashboard | `frontend/` | Vite default (normally 5173) | React UI for Layer 2 topics, context, raw export, reports, and replay | [`frontend/src/main.jsx`](../frontend/src/main.jsx) |

The Layer 3 port map is defined in [`AGENTS.md`](../AGENTS.md), the root README, and [`backend/layer3/orchestrator_service/README.md`](../backend/layer3/orchestrator_service/README.md); the backend does not set a port in code.

## 3. Per-service detail

### Backend: Layer 1 + Layer 2

`backend/main.py` creates one FastAPI application, adds CORS for `http://localhost:5173` and `http://127.0.0.1:5173`, and includes the topics, ingestions, retrieval, and Layer 1 routers. The API has **no `/health` route**.

#### HTTP endpoints

| Method/path | Request schema | Response schema / construction |
| --- | --- | --- |
| `GET /topics` | Query: `limit: int = 50` (`1..200`), `offset: int = 0` (`>=0`) | `list[TopicResponse]`; `X-Total-Count` header. |
| `POST /topics` | `CreateTopicRequest` | `TopicResponse`, HTTP 201. |
| `POST /topics/{topic_id}/lifecycle` | Path `topic_id: UUID`; `TopicLifecycleRequest` | `TopicResponse`. |
| `POST /ingestions` | Raw JSON parsed as `Layer1Package` | Untyped ingestion-report object, HTTP 201 (or HTTP 200 for an exact retry; HTTP 422 when validation status is rejected). |
| `GET /discover` | Query `topic: str` (nonempty), `limit: int = 10` (`1..100`) | `list[DiscoveredArticle]`. |
| `POST /extract` | `ExtractionRequest` | `ExtractionResponse`. |
| `POST /deduplicate` | `DeduplicationRequest` | `DeduplicationResponse`. |
| `POST /build-package` | `PackageBuildRequest` | `ResearchPackage`. |
| `GET /topics/{topic_id}/timeline` | Path UUID; optional query `as_of: datetime` | `{ "topic_id": string, "timeline": Event[] }`. |
| `GET /topics/{topic_id}/context` | Path UUID; query `max_nodes=200 (1..200)`, `max_relationships=500 (1..500)`, `include_disputed=true`, `include_interpretations=true`, `minimum_confidence?: float (0..1)`, `time_start?: datetime`, `time_end?: datetime`, `cursor?: string`, `as_of?: datetime` | Untyped topic-context object shown in [Data schemas](#4-data-schemas). |
| `POST /graph/expand` | `GraphExpansionRequest` | Untyped graph expansion object. |
| `GET /topics/{topic_id}/raw-export` | Path UUID; query `status?: comma-separated string`, `event_id?: UUID`, `claim_id?: UUID`, `limit=100 (1..100)`, `cursor?: string` | `{items, active, disputed, superseded, retracted, next_cursor, truncated}`. |
| `GET /entities/{entity_id}/context` | Path UUID; required query `topic_id: UUID` | `{entity, claims, relationships}`. |
| `GET /claims/{claim_id}/evidence` | Path UUID | `{claim_id, text, status, epistemic_status, evidence}`. |
| `GET /ingestions/{ingestion_id}` | Path UUID | `{ingestion_id, package_id, topic_id, status, input_schema_version, pipeline_version, graph_model_version, ontology_version, received_delta, report, resolution_decisions}`. |

The route decorators and signatures are in [`backend/layer2/api/topics.py`](../backend/layer2/api/topics.py), [`ingestions.py`](../backend/layer2/api/ingestions.py), [`layer1.py`](../backend/layer1/api.py), and [`retrieval.py`](../backend/layer2/api/retrieval.py). These important request models are implemented exactly as follows:

```jsonc
// POST /topics
{
  "topic_key": "string; ^[a-z0-9]+(?:-[a-z0-9]+)*$; max 128",
  "display_name": "string; max 255",
  "scope": {
    "description": "string",
    "geography": ["string"], // defaults to []
    "start": "date",
    "end": "date | null" // defaults to null
  }
}

// POST /topics/{topic_id}/lifecycle
{ "status": "active|monitoring|closed|archived", "reason": "string" }

// POST /graph/expand
{
  "topic_id": "UUID",
  "seed_ids": ["UUID"],
  "relationship_types": ["string"] | null,
  "max_depth": 1, // 1..2
  "max_nodes": 100, // 1..100
  "max_relationships": 250, // 1..500
  "include_disputed": true,
  "statuses": ["string"] | null,
  "minimum_confidence": 0.0 | null,
  "time_start": "datetime | null",
  "time_end": "datetime | null",
  "as_of": "datetime | null"
}
```

The Layer 1 endpoint models live in [`backend/layer1/service.py`](../backend/layer1/service.py):

```jsonc
// GET /discover response item
{ "title": "string", "publisher": "string", "published_date": "string | null", "url": "string" }

// POST /extract
{ "urls": ["string"] } // 1..50
// response
{ "articles": [{
  "url": "string", "canonical_url": "string | null", "title": "string",
  "publisher": "string | null", "published_date": "string | null", "body": "string",
  "extraction_method": "trafilatura|newspaper4k", "success": "boolean", "error": "string | null"
}] }

// POST /deduplicate
{ "articles": ["ExtractedArticle"] }
// response
{ "groups": [{
  "representative": { "url": "string", "canonical_url": "string | null", "title": "string", "publisher": "string | null", "published_date": "string | null", "body": "string", "duplicate_of": "string | null" },
  "duplicates": ["DeduplicatedArticle"]
}] }

// POST /build-package
{ "topic_key": "string", "articles": ["ExtractedArticle"] }
```

`ResearchPackage` is the response from `/build-package`; the independently defined `Layer1Package` in [`backend/layer2/contracts/layer1.py`](../backend/layer2/contracts/layer1.py) is the body accepted by `/ingestions`. Its `package_id` is a UUID there (but a plain string in `ResearchPackage`), and it requires `schema_version`, `topic_key`, `metadata {title, generated_at}`, `sources`, `articles`, `evidence`, `entities`, `events`, and `claims`; `relationships`, `timeline`, `uncertainties`, `themes`, and `sentiment` default to arrays. This type distinction is an implementation fact, not an inferred compatibility guarantee.

```jsonc
// POST /ingestions: Layer1Package (all nested arrays are list[dict[str, Any]] in the accepting model)
{
  "schema_version": "string; must equal 1.0 at runtime", "package_id": "UUID", "topic_key": "string",
  "metadata": { "title": "string", "generated_at": "datetime" },
  "sources": [{}], "articles": [{}], "evidence": [{}], "entities": [{}], "events": [{}], "claims": [{}],
  "relationships": [], "timeline": [], "uncertainties": [], "themes": [], "sentiment": []
}

// POST /build-package response: ResearchPackage's fully typed Layer 1 envelope
{
  "schema_version": "1.0", "package_id": "string", "topic_key": "string", "metadata": { "title": "string", "generated_at": "datetime" },
  "sources": [{ "source_id": "string", "publisher": "string", "url": "string", "published_at": "string | null" }],
  "articles": [{ "article_id": "string", "source_id": "string", "canonical_url": "string", "discovery_url": "string | null", "publisher": "string", "published_at": "string | null", "content_hash": "string", "content": "string" }],
  "evidence": [{ "evidence_id": "string", "article_id": "string", "excerpt": "string", "start_offset": "integer >= 0", "end_offset": "integer >= 0", "language": "string | null" }],
  "entities": [{ "entity_id": "string", "name": "string", "type": "string", "aliases": ["string"], "evidence_ids": ["string"] }],
  "events": [{ "event_id": "string", "type": "string", "title": "string", "description": "string | null", "temporal": { "start": "datetime", "precision": "exact|approximate|day|month|range|unknown", "basis": "reported|inferred", "end": "datetime | null" }, "participant_entity_ids": ["string"], "location_entity_ids": ["string"], "evidence_ids": ["string"], "related_claim_ids": ["string"] }],
  "claims": [{ "claim_id": "string", "text": "string", "evidence_ids": ["string"], "event_id": "string", "subject_ref": "string", "predicate_candidate": "string", "object_ref_or_value": "string", "temporal_scope": "TemporalScope", "asserted_by_entity_id": "string | null", "epistemic_status": "observed|reported|attributed|corroborated|disputed|inferred|interpretive|unknown|retracted|superseded" }],
  "relationships": [{ "relationship_id": "string", "subject_ref": "string", "object_ref": "string", "source_relation_label": "string", "evidence_ids": ["string"], "extraction_confidence": "number 0..1" }],
  "timeline": [{}], "uncertainties": [{}], "themes": [{}], "sentiment": [{}]
}
```

The dictionary responses with no declared `response_model` are constructed with these exact top-level keys in the route code:

```jsonc
// POST /ingestions (report_for())
{
  "ingestion_id": "string", "package_id": "string", "topic_id": "string", "status": "string",
  "input_schema_version": "string", "pipeline_version": "string", "graph_model_version": "string", "ontology_version": "string",
  "processing_duration_ms": "integer | null", "summary": {}, "object_results": {}, "warnings": [], "errors": []
}

// GET /topics/{topic_id}/timeline
{ "topic_id": "string", "timeline": [{ "event_id": "string", "title": "string", "type": "string", "status": "string", "temporal": {}, "participant_entity_ids": ["string"], "location_entity_ids": ["string"], "confidence": [], "support": {} }] }

// POST /graph/expand
{
  "topic_id": "string",
  "nodes": [{ "id": "string", "node_type": "entity|event|claim", "label?": "string", "entity_type?": "string", "title?": "string", "text?": "string", "status": "string", "temporal": {}, "confidence": [], "support": {} }],
  "relationships": [{ "relationship_id": "string", "subject_id": "string", "object_id": "string", "type": "string", "status": "string", "temporal": {}, "confidence": [], "support": {} }],
  "coverage": { "truncated": "boolean", "returned_nodes": "integer", "returned_relationships": "integer", "max_depth": "integer" }
}

// GET /topics/{topic_id}/raw-export
{
  "items": ["RawExportItem"], "active": ["RawExportItem"], "disputed": ["RawExportItem"], "superseded": ["RawExportItem"], "retracted": ["RawExportItem"],
  "next_cursor": "string | null", "truncated": "boolean"
}
// RawExportItem = { "claim_id": "string", "status": "string", "event_id": "string | null", "temporal": {}, "raw_text": "string", "evidence": [{"excerpt":"string"}], "support": {} }

// GET /entities/{entity_id}/context
{
  "entity": { "entity_id": "string", "label": "string", "type": "string", "status": "string" },
  "claims": [{ "claim_id": "string", "text": "string", "status": "string" }],
  "relationships": [{ "relationship_id": "string", "type": "string", "status": "string", "subject_id": "string", "object_id": "string" }]
}

// GET /claims/{claim_id}/evidence
{ "claim_id": "string", "text": "string", "status": "string", "epistemic_status": "string", "evidence": [{ "excerpt": "string" }] }

// GET /ingestions/{ingestion_id}
{
  "ingestion_id": "string", "package_id": "string", "topic_id": "string", "status": "string",
  "input_schema_version": "string", "pipeline_version": "string", "graph_model_version": "string", "ontology_version": "string",
  "received_delta": {}, "report": {},
  "resolution_decisions": [{ "decision_id": "string", "incoming_type": "string", "incoming_id": "string", "outcome": "string", "rationale": "string", "signals": {}, "input_schema_version": "string", "graph_model_version": "string", "processing_version": "string", "ontology_version": "string", "supersedes_decision_id": "string | null" }]
}
```

#### External calls and persistence

- `discover()` in `backend/layer1/service.py` calls Google News RSS through `httpx.get`; it parses RSS with `feedparser`. `/discover` persists its request/result metadata through `_persist_discovery()` in `backend/layer1/api.py`.
- `extract()` uses `googlenewsdecoder` for Google News URLs, then `trafilatura` and `newspaper4k` in `_extract_one()`; these libraries retrieve article pages. There is no OpenAI call in the backend.
- `build_full_package()` imports `google.genai`, creates `genai.Client(api_key=GEMINI_API_KEY)`, and calls `client.models.generate_content()` only when `GEMINI_API_KEY` is set and no injected fact generator is supplied. The call is in `backend/layer1/service.py`.
- `/ingestions` persists raw package bytes/JSON, accepted mentions, derived canonical graph rows, validation reports, and reconciliation decisions through `backend/layer2/api/ingestions.py`, `services/mentions.py`, and `services/canonicalization.py`.
- All backend persistence is PostgreSQL through SQLAlchemy. `backend/shared/db.py` reads `DATABASE_URL`, defaulting to `postgresql+psycopg://trinity:trinity@localhost:5432/trinity_reborn`.

### World builder service

`POST /build-world` is defined in [`backend/layer3/world_builder_service/main.py`](../backend/layer3/world_builder_service/main.py).

| Method/path | Request | Response |
| --- | --- | --- |
| `GET /health` | none | `{ "status": "ok" }` |
| `POST /build-world` | `{ "topic_id": "UUID" }` (`BuildWorldRequest`) | `BuildWorldResponse`: `{ "world": World, "characters": { "<UUID>": Character } }` |

```jsonc
World = {
  "topic_id": "string", "world_id": "UUID", "name": "string",
  "entity_map": { "<source entity id>": {
    "fictional_name": "string",
    "fictional_type": "institution|place|faction|person",
    "description": "string"
  }}
}
Character = {
  "source_entity_id": "string | null",
  "role": "protagonist|supporting|antagonist",
  "name": "string", "goals": ["string"], "fears": ["string"],
  "personality": ["string"],
  "emotion_state": { "primary": "string", "secondary": "string" }
}
```

`fetch_context()` in [`backend/layer3/world_builder_service/world_builder.py`](../backend/layer3/world_builder_service/world_builder.py) calls `GET {LAYER2_BASE_URL}/topics/{topic_id}/context` through HTTPX and requires `entities`, `events`, `claims`, and `disputes` arrays. `generate_fictional_content()` calls `OpenAI(...).chat.completions.parse()` with `GenerationPayload` as the structured response schema. It reads `OPENAI_API_KEY` and optional `OPENAI_BASE_URL` directly; configuration reads `LAYER2_BASE_URL` (default `http://localhost:8000`) and `WORLD_BIBLE_DIR` (repo-rooted `world_bible` default) through `artifact_paths.artifact_dir()`. `OPENAI_MODEL` is hard-coded to `gpt-5.6-sol`, not read from the environment.

`build_world()` atomically writes `WORLD_BIBLE_DIR/<topic_id>/world.json` and `characters.json`. On later calls it reads them and only calls OpenAI for missing entity-map or character entries; it retains the existing `world_id` and world name. There is no history, revision directory, database write-back, or callback to Layer 2 in this service.

### Blueprint assembler service

Routes are in [`backend/layer3/blueprint_assembler_service/main.py`](../backend/layer3/blueprint_assembler_service/main.py).

| Method/path | Request | Response |
| --- | --- | --- |
| `GET /health` | none | `{ "status": "ok" }` |
| `POST /build-blueprint` | `{ "topic_id": "UUID" }` | `Blueprint` |

It calls only `GET {LAYER2_BASE_URL}/topics/{topic_id}/context` in `fetch_context()` in [`backend/layer3/blueprint_assembler_service/assembler.py`](../backend/layer3/blueprint_assembler_service/assembler.py), then reads `WORLD_BIBLE_DIR/<topic_id>/world.json` and `characters.json`. It makes no LLM call. It reads `LAYER2_BASE_URL` (default `http://localhost:8000`), `WORLD_BIBLE_DIR` (repo-rooted `world_bible` default), and `BLUEPRINT_DIR` (repo-rooted `blueprints` default), then atomically writes `BLUEPRINT_DIR/<topic_id>/blueprint.json` in `write_blueprint()`.

The current `Blueprint` model is shown in [Story Blueprint](#story-blueprint). `assemble_blueprint()` derives `blueprint_id` deterministically as UUIDv5 of a hash of context/world/characters and derives `generated_at` from that hash; this differs from a normal run-time timestamp.

### Story generator service

Routes are in [`backend/layer3/story_generator_service/main.py`](../backend/layer3/story_generator_service/main.py).

| Method/path | Request | Response |
| --- | --- | --- |
| `GET /health` | none | `{ "status": "ok" }` |
| `POST /episodes` | `{ "topic_id": "UUID", "character_id": "UUID", "force": false }` | `Episode` on success; a failed generated episode is returned with HTTP 502 by the `GenerationFailed` exception handler. |

`create_episode()` in [`backend/layer3/story_generator_service/generator.py`](../backend/layer3/story_generator_service/generator.py) reads `BLUEPRINT_DIR/<topic_id>/blueprint.json`. `generate_narrative()` calls `OpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL or None).chat.completions.parse()` with `GeneratedNarrative {title: string, story_text: string}`. The Pydantic validator requires 500–800 whitespace-separated words. It reads `OPENAI_API_KEY`, optional `OPENAI_BASE_URL`, plus config `BLUEPRINT_DIR` and `EPISODE_DIR` (both repo-rooted defaults); `OPENAI_MODEL` is the hard-coded `gpt-5.6-sol`.

It atomically persists `EPISODE_DIR/<topic_id>/<character_id>.json`. A cached episode whose status is `story_generated`, `translated`, or `audio_ready` is returned without an OpenAI call unless `force=true`. On a generation error it writes a `failed` Episode before returning HTTP 502.

### Translator service

Routes are in [`backend/layer3/translator_service/main.py`](../backend/layer3/translator_service/main.py).

| Method/path | Request | Response |
| --- | --- | --- |
| `GET /health` | none | `{ "status": "ok" }` |
| `POST /translate` | `{ "topic_id": "UUID", "character_id": "UUID", "target_languages": ["string"] | null, "force": false }` | Updated `Episode` |

`translate_episode()` in [`backend/layer3/translator_service/translator.py`](../backend/layer3/translator_service/translator.py) loads the Episode JSON and blueprint JSON. `select_gemini_model()` calls `genai.Client(api_key=GEMINI_API_KEY).models.list()` to select a non-Pro Flash model; `translate_language()` calls `client.models.generate_content()`. It reads `GEMINI_API_KEY`, `GEMINI_MODEL` (default `gemini-3.5-flash-lite`), `BLUEPRINT_DIR`, and `EPISODE_DIR`. The glossary is built from the target character name plus every `world.entity_map.*.fictional_name`.

Translations are immediately and atomically written back into the same `EPISODE_DIR/<topic_id>/<character_id>.json` after each language. Existing `story_text[language]` is reused unless forced. The service retries only Gemini HTTP 429 errors (initial attempt plus up to three waits of 1, 2, and 4 seconds).

### Audio generator service

Routes are in [`backend/layer3/audio_generator_service/main.py`](../backend/layer3/audio_generator_service/main.py).

| Method/path | Request | Response |
| --- | --- | --- |
| `GET /health` | none | `{ "status": "ok", "elevenlabs_key_valid": true, "characters_used": int, "character_limit": int }`; the handler calls ElevenLabs live. |
| `POST /narrate` | `{ "topic_id": "UUID", "character_id": "UUID", "languages": ["string"] | null, "force": false }` | Updated `Episode` |

The app lifespan runs `validate_elevenlabs_key()` before startup; a validation error raises and prevents startup. In [`backend/layer3/audio_generator_service/audio.py`](../backend/layer3/audio_generator_service/audio.py):

- `validate_elevenlabs_key()` calls `GET https://api.elevenlabs.io/v1/user` with `ELEVENLABS_API_KEY`.
- `infer_voice()` calls OpenAI structured parsing with `OPENAI_API_KEY` and the hard-coded `gpt-5.6-sol` model.
- `_voices()` calls `GET https://api.elevenlabs.io/v2/voices?page_size=100`; successful nonempty lists are cached in memory.
- `synthesize()` calls `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}` with model `eleven_multilingual_v2` and output format `mp3_44100_128`; HTTP 429 and 5xx responses retry with 1, 2, and 4 second delays.

It reads `ELEVENLABS_API_KEY`, optional `ELEVENLABS_FALLBACK_VOICE_ID`, `OPENAI_API_KEY`, and repo-rooted `BLUEPRINT_DIR`, `EPISODE_DIR`, and `AUDIO_DIR`. It persists `AUDIO_DIR/<topic_id>/<character_id>/voice_profile.json`, `AUDIO_DIR/<topic_id>/<character_id>/<language>.mp3`, and updates the Episode JSON atomically after every language outcome.

### Orchestrator service

Routes are in [`backend/layer3/orchestrator_service/main.py`](../backend/layer3/orchestrator_service/main.py).

| Method/path | Request | Response |
| --- | --- | --- |
| `GET /health` | none | `{ "status": "ok", "services": { "layer2": {"reachable": boolean}, "world_builder": {"reachable": boolean}, "blueprint_assembler": {"reachable": boolean}, "story_generator": {"reachable": boolean}, "translator": {"reachable": boolean}, "audio_generator": {"reachable": boolean} } }` |
| `POST /run-topic` | `{ "topic_id": "UUID", "character_ids": ["UUID"] | null, "languages": ["string"] | null, "narrate": false }` | `RunReport` shown below. |

`run_topic()` in [`backend/layer3/orchestrator_service/orchestrator.py`](../backend/layer3/orchestrator_service/orchestrator.py) calls the world builder, blueprint assembler, story generator, translator, and optionally audio service with HTTPX. It reads `LAYER2_BASE_URL`, `WORLD_BUILDER_URL`, `BLUEPRINT_URL`, `STORY_GEN_URL`, `TRANSLATOR_URL`, and `AUDIO_URL` (defaults `http://localhost:8000` through `:8005`), `RUN_HISTORY_DIR` (repo-rooted `runs` default), `DOWNSTREAM_TIMEOUT_SECONDS` (default `180`), and `DEMO_MODE` (truthy values `1`, `true`, `yes`, `on`). In demo mode only, an omitted `narrate` field becomes true; an explicit false remains false.

It atomically writes `RUN_HISTORY_DIR/<topic_id>/<run_id>.json`. It makes no LLM provider call itself.

### Frontend

The frontend is a Vite/React application (React 19) with entrypoint [`frontend/src/main.jsx`](../frontend/src/main.jsx) and UI in [`frontend/src/App.jsx`](../frontend/src/App.jsx). It reads `import.meta.env.VITE_API_URL`, defaulting to `http://localhost:8000`. It has no backend HTTP routes and no disk/DB persistence of its own.

The UI calls the backend endpoints `/topics`, `/topics/{id}/context`, `/topics/{id}/raw-export`, `/ingestions/{id}`, `/topics`, `/ingestions`, `/entities/{id}/context`, and `/claims/{id}/evidence`. `replayDemo()` creates a topic and ingests fixture deltas from `fixtures/`; it does not call any Layer 3 service.

## 4. Data schemas

### Layer 2 topic-context response

`GET /topics/{topic_id}/context` returns an untyped dictionary constructed in [`backend/layer2/api/retrieval.py`](../backend/layer2/api/retrieval.py), not a Pydantic response model. Its actual shape is:

```jsonc
{
  "topic": { "topic_id": "UUID string", "topic_key": "string", "display_name": "string", "status": "string" },
  "summary": {
    "text": "string", "claim_ids": ["UUID string"],
    "claims": [{ "claim_id": "UUID string", "text": "string", "status": "string" }]
  },
  "timeline": [{ "event_id": "UUID string", "order": "integer", "title": "string", "status": "string", "temporal": {} }],
  "entities": [{
    "entity_id": "UUID string", "label": "string", "type": "string", "status": "string",
    "confidence": [{ "dimension": "string", "value": "number", "method": "string" }],
    "support": { "package_count": "integer", "assessment": "corroborated|single_package" }
  }],
  "events": [{
    "event_id": "UUID string", "title": "string", "type": "string", "status": "string", "temporal": {},
    "participant_entity_ids": ["UUID string"], "location_entity_ids": ["UUID string"],
    "confidence": ["Confidence"], "support": "Support"
  }],
  "claims": [{
    "claim_id": "UUID string", "text": "string", "epistemic_status": "string", "status": "string",
    "event_id": "UUID string | null", "subject_ref": "UUID string | null", "asserted_by": "UUID string | null",
    "temporal": {}, "confidence": ["Confidence"], "support": "Support"
  }],
  "relationships": [{
    "relationship_id": "UUID string", "subject": { "type": "string", "id": "UUID string" },
    "object": { "type": "string", "id": "UUID string" }, "type": "string", "status": "string",
    "temporal": {}, "confidence": ["Confidence"], "support": "Support"
  }],
  "disputes": [{ "dispute_id": "UUID string", "description": "string", "status": "string", "related_entity_ids": ["UUID string"], "related_claim_ids": ["UUID string"] }],
  "actors": [{ "entity_id": "UUID string", "label": "string", "roles": ["string"] }],
  "uncertainties": [{ "text": "string", "status": "uncertain" }],
  "themes": [{ "label": "string", "interpretive": true }],
  "sentiment": [{ "label": "string", "interpretive": true }],
  "interpretations": [{ "interpretation_id": "string", "text": "string", "labelled": "interpretive" }],
  "coverage": { "returned_nodes": "integer", "returned_relationships": "integer", "omitted_nodes": "integer", "truncated": "boolean", "next_cursor": "string | null" },
  "query_hints": { "available_expansions": [{ "seed_id": "UUID string", "relationship_types": ["string"] }], "raw_export_available": true }
}
```

The historical fixture/earlier Layer 3 contract contains only the core arrays and `interpretations`; the current backend additionally returns `summary.claims`, `actors`, `uncertainties`, `themes`, and `sentiment`. Conversely, the World Builder validates only `entities`, `events`, `claims`, and `disputes`; Blueprint Assembler validates only `entities`, `events`, `claims`, `timeline`, and `disputes`.

### World Bible

`world.json` and `characters.json` use the `World`, `EntityMapEntry`, `Character`, and `Characters` Pydantic models in [`backend/layer3/world_builder_service/contracts.py`](../backend/layer3/world_builder_service/contracts.py):

```jsonc
// world_bible/<topic_id>/world.json
{
  "topic_id": "string", "world_id": "UUID", "name": "string",
  "entity_map": {
    "<source entity id>": {
      "fictional_name": "string", "fictional_type": "institution|place|faction|person", "description": "string"
    }
  }
}

// world_bible/<topic_id>/characters.json
{
  "<character UUID>": {
    "source_entity_id": "string | null", "role": "protagonist|supporting|antagonist", "name": "string",
    "goals": ["string"], "fears": ["string"], "personality": ["string"],
    "emotion_state": { "primary": "string", "secondary": "string" }
  }
}
```

### Story Blueprint

The persisted `Blueprint` model in [`backend/layer3/blueprint_assembler_service/contracts.py`](../backend/layer3/blueprint_assembler_service/contracts.py) is:

```jsonc
{
  "blueprint_id": "UUID", "topic_id": "string", "generated_at": "datetime",
  "world": "World",
  "characters": [{
    "character_id": "UUID", "source_entity_id": "string | null", "role": "protagonist|supporting|antagonist",
    "name": "string", "goals": ["string"], "fears": ["string"], "personality": ["string"],
    "emotion_state": { "primary": "string", "secondary": "string" }
  }],
  "timeline": [{
    "event_id": "string", "fictional_label": "string", "order": "integer", "status": "string",
    "participant_character_ids": ["string"], "epistemic_note": "string"
  }],
  "central_conflict": "string", "themes": ["string"],
  "disputed_threads": [{ "description": "string", "related_character_ids": ["string"], "use_as": "plot tension, not resolved fact" }],
  "perspectives_to_generate": ["string"],
  "target_languages": ["en", "hi", "ta", "bn", "pa", "gu"] // exact order required
}
```

### Episode

`Episode` is shared by the story, translator, and audio services in [`backend/layer3/story_generator_service/contracts.py`](../backend/layer3/story_generator_service/contracts.py):

```jsonc
{
  "episode_id": "UUID", "blueprint_id": "string", "topic_id": "string", "character_id": "string",
  "title": "string", "status": "story_generated|translated|audio_ready|failed",
  "story_text": { "<language>": "string" },
  "audio": { "<language>": "any JSON value; generated entries are {path, voice_id}" },
  "target_languages": ["string"], "created_at": "datetime", "updated_at": "datetime", "error": "string | null",
  "translation_errors": { "<language>": "string" },
  "audio_errors": { "<language>": "string" },
  "voice_id": "string | null"
}
```

`translation_errors`, `audio_errors`, and top-level `voice_id` are present in code although they were absent from the original story-generator-only contract. `audio` is typed as `dict[str, Any]`, not the more specific `{path, voice_id}` shape used by the audio writer.

### Orchestrator run report

`RunReport` and `CharacterRunOutcome` are Pydantic models in [`backend/layer3/orchestrator_service/contracts.py`](../backend/layer3/orchestrator_service/contracts.py):

```jsonc
{
  "run_id": "UUID", "topic_id": "string", "narrate_requested": "boolean",
  "started_at": "datetime", "finished_at": "datetime",
  "world_status": "ok|failed", "blueprint_status": "ok|failed",
  "characters": {
    "<character id>": {
      "story_status": "ok|failed",
      "translation_status": "ok|partial|failed",
      "translation_errors": { "<key>": "string" },
      "audio_status": "ok|partial|failed|skipped",
      "audio_errors": { "<key>": "string" }
    }
  }
}
```

## 5. Database schema

The PostgreSQL schema is defined by the Alembic chain under [`backend/layer2/migrations/versions/`](../backend/layer2/migrations/versions/), beginning with `712caca27763_initial_schema.py`. This is the current migrated schema, including later additions:

| Table | Key columns and relationships from migrations |
| --- | --- |
| `topics` | `id` PK; unique `topic_key`; `display_name`, `scope_json`, `status`, `created_at`. |
| `topic_lifecycle_transitions` | `id` PK; `topic_id → topics`; nullable `ingestion_id → ingestion_runs`; from/to status, reason, timestamp. |
| `raw_packages` | `id` PK; `topic_id → topics`; package/schema/revision, JSONB payload, raw bytes, checksum, received time; unique `(package_id, schema_version, revision)`. |
| `rejected_packages` | `id` PK; nullable package/schema/topic identifiers; raw bytes, checksum, JSONB rejection report, timestamp. |
| `ingestion_runs` | `id` PK; `raw_package_id → raw_packages`; status, schema/pipeline/graph/ontology versions, JSONB report, timestamps. |
| `source_mentions`, `entity_mentions`, `event_mentions`, `claim_mentions`, `relationship_mentions` | Each has `id` PK, `raw_package_id → raw_packages`, local ID, payload; local IDs are unique per package. Entity/event/claim mention tables also store source label/title/text fields. |
| `article_versions` | `id` PK; `raw_package_id → raw_packages`, `source_mention_id → source_mentions`, self-FKs `previous_version_id` and `duplicate_of_id`; canonical URL, fingerprint, content hash/content/payload. |
| `evidence_mentions` | `id` PK; `raw_package_id → raw_packages`, `article_version_id → article_versions`; excerpt and offsets. |
| `canonical_entities` | `id` PK; canonical label, type, status, global-eligible flag, timestamp. |
| `canonical_events` | `id` PK; `topic_id → topics`; display title, type, status, timestamp. |
| `event_resolution_contexts` | `event_id` PK/FK → `canonical_events`; JSONB temporal, participant IDs, location IDs. |
| `claims` | `id` PK; `topic_id → topics`; optional `canonical_event_id → canonical_events`; text, epistemic status, status, timestamp. |
| `claim_assertions` | `id` PK; `claim_id → claims`; subject/predicate/object and temporal JSON; status plus derivation/provenance columns and optional `resolution_decision_id → resolution_decisions`. |
| `claim_status_history` | `id` PK; `claim_id → claims`; `ingestion_id → ingestion_runs`; status and effective time. |
| `graph_relationships` | `id` PK; `topic_id → topics`; typed subject/object IDs, relationship type, status, temporal JSON, timestamp. |
| `relationship_assertions` | `id` PK; `relationship_id → graph_relationships`; assertion/status/rationale plus derivation/provenance columns and optional `resolution_decision_id`. |
| `relationship_status_history` | `id` PK; `relationship_id → graph_relationships`; nullable `ingestion_id → ingestion_runs`; status, reason, effective time. |
| `resolution_decisions` | `id` PK; `ingestion_id → ingestion_runs`; incoming object/result/rationale/signals, all version fields, optional self-FK `supersedes_decision_id`. |
| `local_id_mappings` | `id` PK; `raw_package_id → raw_packages`, `decision_id → resolution_decisions`; local type/id to canonical type/id; unique per package/type/local ID. |
| `mapping_revisions` | `id` PK; `mapping_id → local_id_mappings`, `decision_id → resolution_decisions`, optional self-FK `supersedes_revision_id`; canonical target and timestamp. |
| `provenance_links` | `id` PK; `raw_package_id → raw_packages`, optional `evidence_mention_id → evidence_mentions`, optional `claim_id → claims`; graph object type/id. |
| `confidence_assessments` | `id` PK; polymorphic subject type/id; dimension/value, assessment method/version, support IDs, rationale, timestamp. |
| `topic_annotations` | `id` PK; `topic_id → topics`, `raw_package_id → raw_packages`; kind, JSONB payload, timestamp. |
| `discovery_requests` | `id` PK; Layer 1 topic query, Google News URL, requested limit, status, timestamps. |
| `discovered_articles` | `id` PK; `discovery_request_id → discovery_requests` with `ON DELETE CASCADE`; title/publisher/date/URL. |

The later migrations add the history, confidence, annotation, discovery, lineage, mapping-revision, and provenance columns/tables. The table description above follows those migration operations rather than the PRD.

## 6. End-to-end call sequence

1. `POST /run-topic` invokes `run_topic_endpoint()` in `backend/layer3/orchestrator_service/main.py`. It converts UUIDs to strings and applies the `DEMO_MODE` default only when `narrate` was omitted.
2. `run_topic()` creates an HTTPX client with `DOWNSTREAM_TIMEOUT_SECONDS` and calls `_post()` to `POST {WORLD_BUILDER_URL}/build-world`.
3. World Builder's `build_world_endpoint()` calls `build_world()`, which calls `fetch_context()` → `GET {LAYER2_BASE_URL}/topics/{topic_id}/context`. The backend's `get_topic_context()` queries PostgreSQL and assembles the response. World Builder either reads its existing Bible or calls `generate_fictional_content()` → OpenAI, then writes `world.json` and `characters.json`.
4. The orchestrator calls `POST {BLUEPRINT_URL}/build-blueprint`. Blueprint Assembler's `assemble_blueprint()` independently fetches the same context and reads the World Bible. It derives/validates a Blueprint; `write_blueprint()` writes `blueprint.json`.
5. The orchestrator takes `perspectives_to_generate` and `target_languages` from the Blueprint response if the caller omitted characters/languages.
6. For each character, `_run_character()` calls `POST {STORY_GEN_URL}/episodes`. Story Generator loads the Blueprint, reuses a successful cache or calls OpenAI through `generate_narrative()`, then writes an Episode JSON.
7. `_run_character()` calls `POST {TRANSLATOR_URL}/translate`. Translator loads that Episode and the Blueprint glossary, calls Gemini per missing requested language, and writes the Episode JSON after each language result.
8. If narration was requested, `_run_character()` calls `POST {AUDIO_URL}/narrate`. Audio Generator loads/creates a cached voice profile (OpenAI plus ElevenLabs voice listing), calls ElevenLabs per missing language, writes each MP3 and updates the Episode JSON.
9. The orchestrator converts returned `translation_errors`/`audio_errors` to `ok` or `partial`, creates `RunReport`, and `_write_report()` writes it under `runs/`.

Failure handling is deliberately asymmetric. `_post()` propagates World Builder or Blueprint failures as an `OrchestratorError`, so no report is written for those aborted runs. Story failures are caught per character and result in `story_status=failed`, `translation_status=failed`, and audio `skipped`/`failed`; later characters continue. Translation and audio failures are caught independently per character and recorded as `_upstream` errors while later work proceeds. The Story Generator itself writes a failed Episode before raising its 502 response; Translator and Audio Generator preserve partial language progress in the Episode file.

## 7. Known gaps and discrepancies

### TODO/FIXME scan

`rg "TODO|FIXME"` finds no implementation TODO/FIXME comments. The only match is a documentation sentence in [`AGENTS.md`](../AGENTS.md) describing a possible `backlog.md`; no `backlog.md` file is present in the repository file list.

### Verified discrepancies and absent implementations

- **Orchestrator Layer 2 health mismatch:** `backend/layer3/orchestrator_service/main.py` probes `GET {LAYER2_BASE_URL}/health`; `backend/main.py` exposes no `/health` decorator. With the current backend at port 8000, the orchestrator health report will mark `layer2.reachable=false` even if `/topics/...` works.
- **`.env.example` exists at the repository root** and documents the environment variables used by the services. The root README's `cp .env.example .env` setup instruction is accurate. The template is a local configuration file, so tools that only enumerate tracked files may not list it. The current port-8000 API is “Layer 2” by purpose, and its actual entrypoint is `backend/main.py`, not a `layer2_mock` package.
- **No World Bible history/write-back:** only `world.json` and `characters.json` are written in `backend/layer3/world_builder_service/world_builder.py`. There is no revision/history artifact, endpoint, DB table, or Layer 2 write-back for a completed world/blueprint/run.
- **No Story Generator history/write-back:** it overwrites the one episode file per topic/character; no episode revision history or API writes to the backend exist.
- **Layer 3 is filesystem-coupled after context retrieval:** only World Builder and Blueprint Assembler call Layer 2; Story Generator, Translator, and Audio Generator read artifacts directly from disk. This is implemented in their `load_*` functions and is also stated in `AGENTS.md`.
- **Topic-context is richer than the older fixture-shaped contract:** the backend returns `actors`, `uncertainties`, `themes`, `sentiment`, and `summary.claims` in addition to the core fields. It has no response Pydantic model, so consumers rely on runtime dictionary construction.
- **The Blueprint event label does not follow an “event title with substitutions” description:** `_fictional_event_label()` deliberately ignores the Layer 2 event `title` and constructs a generic event type plus fictional participant names, to avoid leaking unmapped real names.
- **Audio voice-list caching is conditional:** `_voices()` reuses an in-memory cache only when it is nonempty; a failed/empty voice response is not retained, despite a simpler “cache full response for process life” description sometimes associated with this module.
- **No backend health endpoint and no Layer 3 routes in the dashboard:** frontend only operates Layer 1/2 APIs; there is no UI route or component for launching an orchestrated story run.

## 8. How to run and verify locally

The commands below are consolidated from the checked-in root README, `AGENTS.md`, and service READMEs, with paths and ports verified against source code.

```sh
# PostgreSQL + Python environment
docker compose up -d db
uv sync --group dev
uv run alembic upgrade head

# Backend (Layer 1 + Layer 2), from repository root
PYTHONPATH=. uv run uvicorn backend.main:app --reload --port 8000

# Operator dashboard, from repository root
npm install --prefix frontend
npm run dev --prefix frontend
```

Run each Layer 3 service from the repository root in a separate terminal:

```sh
uv run uvicorn backend.layer3.world_builder_service.main:app --port 8001
uv run uvicorn backend.layer3.blueprint_assembler_service.main:app --port 8002
uv run uvicorn backend.layer3.story_generator_service.main:app --port 8003
uv run uvicorn backend.layer3.translator_service.main:app --port 8004
uv run uvicorn backend.layer3.audio_generator_service.main:app --port 8005
uv run uvicorn backend.layer3.orchestrator_service.main:app --port 8006
```

The backend needs PostgreSQL. Layer 1 Gemini fact extraction is optional because `build_full_package()` returns a delivery-valid package when `GEMINI_API_KEY` is absent. World Builder and Story Generator require `OPENAI_API_KEY` only when generation is needed; Translator requires `GEMINI_API_KEY` only for uncached translations; Audio Generator validates `ELEVENLABS_API_KEY` at startup and needs `OPENAI_API_KEY` for an uncached voice profile.

Useful verified request forms from service READMEs:

```sh
# World and blueprint
curl -sX POST http://127.0.0.1:8001/build-world -H 'content-type: application/json' -d '{"topic_id":"<topic-uuid>"}'
curl -sX POST http://127.0.0.1:8002/build-blueprint -H 'content-type: application/json' -d '{"topic_id":"<topic-uuid>"}'

# One story, translation, and narration
curl -sX POST http://127.0.0.1:8003/episodes -H 'content-type: application/json' -d '{"topic_id":"<topic-uuid>","character_id":"<character-uuid>","force":false}'
curl -sX POST http://127.0.0.1:8004/translate -H 'content-type: application/json' -d '{"topic_id":"<topic-uuid>","character_id":"<character-uuid>","target_languages":["hi","ta"],"force":false}'
curl -sX POST http://127.0.0.1:8005/narrate -H 'content-type: application/json' -d '{"topic_id":"<topic-uuid>","character_id":"<character-uuid>","languages":["en"]}'

# Text-only orchestration (explicitly avoids audio)
curl -sX POST http://127.0.0.1:8006/run-topic -H 'content-type: application/json' -d '{"topic_id":"<topic-uuid>","narrate":false}'
```

The root README's validation commands are consistent with the repository layout:

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

For a live check, use an existing real backend route such as `GET /topics`; do not use `GET /health` on port 8000 until that endpoint is implemented. Layer 3 `GET /health` endpoints exist, while the Audio Generator health endpoint also performs a live ElevenLabs key validation.
