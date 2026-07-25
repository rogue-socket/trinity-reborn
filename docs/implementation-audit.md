# Layer 2 Implementation Audit

**Audit date:** 2026-07-25  
**Scope:** Current working tree in `trinity-reborn`  
**Requirements baseline:** `prds/current-affairs-knowledge-graph-layer.md`

## 1. Executive assessment

The repository contains a working local MVP built with FastAPI, PostgreSQL, Alembic, and React. It implements the main vertical slice:

1. register a Layer 2 topic;
2. ingest immutable Layer 1 deltas;
3. retain source-derived objects;
4. create and reconcile canonical entities, events, claims, and relationships;
5. preserve contradictions, corrections, retractions, and possible matches;
6. retrieve topic context, timelines, graph expansions, evidence, and raw wording; and
7. inspect and replay the flow through a local dashboard.

The remediation pass is complete. All 15 gaps identified by the original audit were addressed, and all 11 explicit acceptance bullets in PRD section 22 are now met by implementation and automated evidence.

The verified implementation passes 45 backend tests and 3 frontend acceptance tests. Alembic upgrade and drift checks, backend lint and type checks, frontend lint and type checks, the production build, and both production-only and complete frontend dependency audits are clean.

## 2. Audit basis and limitations

The project instructions identify `prds/Current Affairs Knowledge Graph Layer PRD.pdf` as the source of truth, but that PDF is not present in the workspace or Git tree. The available requirements artifact is the Markdown restatement at `prds/current-affairs-knowledge-graph-layer.md`; this audit uses its current working-tree contents, including the uncommitted Layer 1 and Layer 3 integration-contract additions.

The audit covered:

- API routes and request contracts;
- ingestion, validation, mention persistence, and canonicalization services;
- SQLAlchemy models and all Alembic migrations;
- retrieval behavior and redaction;
- React dashboard behavior;
- golden fixtures and expected outputs;
- all backend tests;
- local startup and build configuration.

This was a requirements and implementation audit, not a penetration test, performance test, accessibility audit, or production-readiness review.

## 3. What was implemented

### 3.1 Local system shape

Implemented:

- FastAPI service with generated OpenAPI documentation.
- PostgreSQL as the authoritative store.
- Alembic migration chain covering the initial schema and subsequent integrity additions.
- React/Vite local operator dashboard.
- Docker Compose configuration for the local PostgreSQL dependency.
- README startup, verification, and demo instructions.

Primary evidence:

- `backend/app/main.py`
- `backend/app/db.py`
- `compose.yaml`
- `migrations/versions/`
- `frontend/`
- `README.md`

### 3.2 Topic registry and lifecycle

Implemented:

- Layer 2-owned UUID and unique `topic_key`.
- Bounded topic scope with description, geography, start, and optional end.
- Topic listing and registration.
- `active`, `monitoring`, `closed`, and `archived` lifecycle values.
- Audited manual lifecycle transitions.
- Automatic reopening of a closed topic when a new package arrives.
- Retrieval remains available regardless of lifecycle state.

Primary evidence:

- `backend/app/api/topics.py`
- `backend/app/models.py`: `Topic`, `TopicLifecycleTransition`
- `backend/tests/test_topics.py`

### 3.3 Layer 1 package intake and immutable storage

Implemented:

- Required envelope validation with schema version, UUID package ID, topic key, metadata, and required collections.
- Unsupported-schema and unknown-topic rejection.
- Exact request bytes in `payload_bytes`, parsed JSON in `payload`, and SHA-256 checksum.
- Separate immutable retention of invalid JSON and other envelope-level rejections.
- Revision numbering when a package ID is reused with changed bytes.
- HTTP 200 for an identical retry and 201 for a newly processed package.
- PostgreSQL triggers preventing updates or deletes of raw, rejected, and source-derived input rows.
- Transaction-scoped advisory locking by topic for same-topic ingestion serialization.
- Persisted input schema, graph model, pipeline, and ontology versions.
- Processing duration in the final ingestion report.

Primary evidence:

- `backend/app/api/ingestions.py`
- `backend/app/contracts/layer1.py`
- `backend/app/models.py`: `RawPackage`, `RejectedPackage`, `IngestionRun`
- migrations `6b5bd102e9f1`, `9d42be5170a3`, `b4c3d2e1f0a9`, and `9ae431b75c5d`
- ingestion and concurrency tests in `backend/tests/test_ingestions.py`

### 3.4 Object validation and source-derived storage

Implemented:

- Per-object required-field checks.
- Duplicate local-ID and ambiguous cross-type local-ID checks.
- Source-to-article, evidence-to-article, event, claim, and relationship local-reference checks.
- Evidence offset and excerpt verification.
- Temporal shape and ISO timestamp validation.
- Scalar claim-confidence range validation.
- Endpoint rules for the recognized relationship subset.
- Partial acceptance for independent valid objects.
- Source, article, evidence, entity, event, claim, and relationship mention storage.
- Article content hashing, canonical URL storage, and changed-content lineage.
- Topic-level uncertainty, theme, and sentiment annotation storage.

Primary evidence:

- `backend/app/services/validation.py`
- `backend/app/services/mentions.py`
- validation and provenance tests in `backend/tests/test_ingestions.py`

### 3.5 Canonical graph and reconciliation

Implemented:

- Layer 2-generated UUIDs for canonical entities, events, claims, and graph relationships.
- Immutable package-local-to-canonical mappings.
- Topic-scoped exact entity matching by normalized label and type.
- Conservative token-overlap entity candidates represented as separate nodes linked by `POSSIBLY_SAME_AS`.
- Strict event matching using topic, type, normalized title, exact start time, and a shared participant or location.
- Ambiguous same-title events retained separately as possible matches.
- Exact normalized claim-text deduplication.
- Structured claim assertions from subject, predicate, object/value, and temporal scope.
- Deterministic progression classification for later time scopes.
- Possible and confirmed contradiction assertion history.
- Explicit correction and retraction links with claim-status history.
- Recognized source-derived relationship creation.
- Resolution decisions, candidate lists, rationale, mappings, confidence assessments, and processing versions.
- Bounded deterministic candidate queries and supporting indexes.

Primary evidence:

- `backend/app/services/canonicalization.py`
- `backend/app/models.py`
- migrations `1a7fdbd3c310`, `a8a8205e2fe2`, and `ce6ac1db7402`
- reconciliation tests in `backend/tests/test_ingestions.py`

### 3.6 Provenance and explainability

Implemented:

- Immutable source-derived mention records linked to a raw package.
- Local-ID mappings linked to resolution decisions.
- Generic canonical-object-to-package provenance links.
- Evidence-level provenance links for recognized graph relationships.
- Resolution outcomes, rationale, candidate data, selected canonical ID, and processing versions.
- Typed resolution/support confidence records.
- Operator retrieval of the received delta and persisted ingestion report.

Primary evidence:

- `ProvenanceLink`, `ResolutionDecision`, `LocalIdMapping`, and `ConfidenceAssessment` in `backend/app/models.py`
- `_map_object` in `backend/app/services/canonicalization.py`
- `GET /ingestions/{ingestion_id}` in `backend/app/api/retrieval.py`

### 3.7 Layer 3 retrieval

Implemented:

- Topic context with entities, events, claims, relationships, disputes, actor roles, annotations, coverage, and query hints.
- Event-time-ordered topic timeline.
- Topic boundary enforcement for graph seeds.
- Bounded graph expansion with depth and node limits.
- Entity context and claim-evidence endpoints.
- Paginated raw claim/evidence export.
- Redaction of Layer 1 package IDs, local IDs, URLs, publishers, and source metadata from Layer 3-oriented responses.
- Opaque cursor-shaped pagination tokens with invalid-token rejection.
- Basic confidence, time, dispute, interpretation, and historical query parameters.

Primary evidence:

- `backend/app/api/retrieval.py`
- retrieval and redaction tests in `backend/tests/test_ingestions.py`
- golden response assertions in `backend/tests/test_golden_demo.py`

### 3.8 Operator dashboard and demo

Implemented:

- Topic selection.
- Canonical node and relationship display.
- Event timeline.
- Context-query controls and coverage display.
- Raw-export display.
- Received-delta and ingestion-report inspection.
- Resolution-result list.
- Three-step replay with graph-evolution counts.
- Canonical entity and claim inspection.

Primary evidence:

- `frontend/src/App.jsx`
- `frontend/src/demo.js`
- `frontend/src/styles.css`
- README demo checklist

### 3.9 Golden corpus and automated tests

Implemented:

- Three real-topic fixtures for the 2024 United Kingdom general election.
- Expected ingestion, context, timeline, and raw-export outputs.
- End-to-end golden scenario through the live FastAPI/PostgreSQL stack.
- Tests for idempotency, immutability, invalid-package retention, revisions, partial acceptance, reference validation, provenance, article lineage, concurrency, reconciliation, contradiction, progression, correction, retraction, retrieval, redaction, `as_of`, topic boundaries, lifecycle transitions, and reopening.

Primary evidence:

- `fixtures/`
- `backend/tests/test_golden_demo.py`
- `backend/tests/test_ingestions.py`
- `backend/tests/test_topics.py`

## 4. Acceptance-criteria matrix

| PRD section 22 criterion | Status | Evidence and caveat |
| --- | --- | --- |
| Registered topic receives self-contained packages | Met | Topic registration, unknown-topic rejection, and three independent golden deltas are tested. |
| Every package remains immutable and internally retrievable | Met | Exact bytes and JSON are stored; database triggers and mutation tests protect inputs. Rejected packages are retained in a separate internal table. |
| Layer 2 creates its own canonical IDs | Met | UUIDs, decisions, mappings, mapping revisions, and provenance cover accepted input and graph objects. |
| Identical retry creates no duplicate graph objects | Met | Same package ID, schema, and exact-byte checksum returns the existing report with HTTP 200. |
| Later packages reconcile high-confidence matches | Met | Entity, event, claim, and relationship paths reconcile under versioned policy; relationship confirmations aggregate assertions. |
| Ambiguous matches remain separate and visibly linked | Met | Entity and event possible-match tests assert separate canonical IDs and `POSSIBLY_SAME_AS`. |
| Conflicting and corrected claims remain available with status | Met | Contradiction, correction, retraction, status-history, and raw-export paths are tested. |
| Timeline uses event time rather than arrival time | Met | Timeline sorting and the golden expected order are tested. |
| Layer 3 gets self-contained context and bounded follow-up queries | Met | Context and expansion enforce topic, node, relationship, time, confidence, dispute, status, and pagination bounds and return details, coverage, and expansion hints. |
| Layer 3 gets complete redacted raw topic material | Met | Paginated raw wording is redacted and partitioned into active, disputed, superseded, and retracted material. |
| Dashboard shows graph evolution, decisions, and query responses | Met | The dashboard replays committed fixtures, renders connected and distinctly styled possible matches, and exposes decision rationale, signals, and versions. |

## 5. Gaps and incomplete requirements

This section preserves the original findings and their causes. Each status reflects the completed remediation; implementation evidence is summarized in section 10.

### G1. Dependency-aware partial validation can fail after validation

**Severity:** High  
**Status:** Remediated

The validator calculates the valid entity, event, and claim ID sets before all temporal, evidence, and other object checks have completed. A relationship can therefore be marked accepted while pointing to a claim or event that is later marked rejected.

For a recognized relationship, canonicalization assumes both endpoint mappings exist and indexes the mapping dictionary directly. This can turn an object-level validation problem into an ingestion-time exception instead of a deterministic partial-acceptance report.

Required correction:

- propagate rejected dependency state before finalizing dependent objects;
- reject the dependent relationship/event/claim with a readable error; and
- add an integration test proving valid independent objects still commit.

### G2. Relationship reconciliation and duplicate-edge prevention are absent

**Severity:** High  
**Status:** Remediated

Every recognized relationship mention creates a new `GraphRelationship`. There is no candidate lookup by topic, endpoints, normalized type, or temporal scope; no resolve-to-existing path; and no duplicate/confirmation classification for relationship assertions.

Consequences:

- independent packages can create duplicate canonical edges;
- relationship support is split across duplicate records;
- the ingestion report overstates created graph material;
- the acceptance guarantee is narrower than “no duplicate graph objects.”

The different-package/same-checksum rule is also not realizable as written because the checksum covers exact request bytes and those bytes include `package_id`. A new package ID necessarily changes the exact-byte checksum. Semantic deduplication currently relies on object resolvers, which do not cover relationships.

### G3. Historical `as_of` retrieval is only a partial projection

**Severity:** High  
**Status:** Remediated

`as_of` filters entity/event/relationship creation times and uses claim-status history. It does not reconstruct:

- topic lifecycle status at the requested time;
- relationship status history;
- resolution-decision or mapping reversals;
- confidence assessments as of the time;
- support counts excluding packages received later;
- annotation/support changes for every returned object.

The result is a mixed historical/current view, not the complete “graph as it was known” required by the PRD.

### G4. Quantity normalization and safe contradiction comparison are absent

**Severity:** High  
**Status:** Remediated

Structured claim objects store a raw ID or raw value. There is no normalized quantity model for value, unit/currency, bounds, approximation, population, measurement scope, or temporal scope.

Contradiction detection compares `object_json` for inequality after matching subject, predicate, and temporal JSON. It can therefore treat differing raw quantities as incompatible without applying the PRD safeguards.

Required correction:

- introduce typed normalized values;
- compare quantities only when units and scopes are compatible; and
- cover the PRD examples with unit tests.

### G5. Taxonomy, epistemic status, and normalization enforcement are incomplete

**Severity:** Medium  
**Status:** Remediated

- Unrecognized entity types are preserved directly as canonical entity types instead of becoming `unknown` while retaining the original label.
- Epistemic status is not checked against the PRD enum.
- Entity aliases are stored only inside the raw mention payload and are not used for candidate retrieval.
- The normalization layer is limited to case-folding and whitespace.
- Temporal validation does not reject an end earlier than the start.

### G6. Canonical mappings and provenance are incomplete for non-graph inputs and derived fields

**Severity:** Medium  
**Status:** Remediated

Source, article, and evidence objects receive Layer 2 database UUIDs, but their accepted report entries do not receive canonical IDs, mappings, or decisions. An unrecognized relationship label is retained as a mention and classified as `retained_candidate`, but it also receives no canonical mapping or decision ID.

Canonical entity, event, and claim provenance generally points to the raw package rather than directly to evidence. The evidence chain is recoverable through mention payloads, but the generic provenance record does not express the full graph-object-to-claim-to-evidence-to-article path described by the PRD.

Derived claim and relationship assertions do not persist their derivation method, input IDs, confidence, or processing versions. Confidence assessments omit the specified model/rule version and supporting IDs.

### G7. Reconciliation policy is hard-coded and narrower than the normative policy

**Severity:** Medium  
**Status:** Remediated

- No versioned threshold configuration exists.
- The code uses exact matching plus a hard-coded 0.5 token-overlap threshold and a candidate limit of 25.
- The PRD’s initial entity, event, possible-match, and contradiction thresholds are not represented.
- Candidate retrieval does not use aliases, article/evidence fingerprints, compatible temporal ranges, or global eligibility.
- The persisted contradiction outcome is `CONFIRM_CONTRADICTION`, which does not match the specified `CREATE_CONFIRMED_CONTRADICTION` outcome catalogue.
- Resolution decisions are not created for every accepted input object.

No LLM is used. That is acceptable because LLM scoring is optional.

### G8. Controlled relationship ontology is only a small label map

**Severity:** Medium  
**Status:** Remediated

Only seven source labels are canonicalized. The remainder of the initial PRD ontology, inverse/symmetry/transitivity metadata, inference permissions, evidence requirements, and temporal behavior are not modeled as a versioned catalogue.

Unknown labels are safely kept out of the canonical ontology, which is correct, but their retained-candidate result lacks a decision, mapping, and operator-visible rationale.

The implementation does not infer causality from temporal order, satisfying the core safety constraint.

### G9. Retrieval filters, prioritization, and expansion output are incomplete

**Severity:** Medium  
**Status:** Remediated

- `include_disputed=false` filters some contradiction relationships but still returns disputed claims and confirmed contradiction relationships.
- `time_start` and `time_end` filter events only, not scoped claims and relationships.
- `minimum_confidence` uses any qualifying assessment without dimension-aware policy.
- Graph expansion lacks relationship-count, time-range, confidence, and broader status limits described in PRD section 17.
- Expanded nodes contain IDs only, not self-contained node details.
- Context ordering does not implement the required deterministic prioritization of defining/recent events, connected actors, disputes, and supporting context.
- `available_expansions` is always empty.
- Raw export returns a flat item list rather than explicit `active`, `disputed`, `superseded`, and `retracted` partitions.

### G10. Article fingerprinting is narrower than specified

**Severity:** Medium  
**Status:** Remediated

Article lineage is keyed by canonical URL and changed content hash. Publisher and published timestamp are not part of a canonical article fingerprint. The same content can be stored repeatedly without a duplicate-version link, while changed content at the same URL is correctly linked to a previous version.

### G11. Warning outcomes are not implemented

**Severity:** Medium  
**Status:** Remediated

The report schema includes `warnings`, but validation always returns an empty list and never emits `accepted_with_warnings`.

Evidence-free claims and relationships can be accepted silently even though the PRD requires a warning and excludes them from high-confidence promotion.

### G12. Topic transition provenance is incomplete

**Severity:** Low  
**Status:** Remediated

Lifecycle transitions have topic, old/new status, reason, and timestamp, but no `ingestion_id`. Automatic reopening is auditable by time and reason but is not linked directly to the ingestion run that caused it.

### G13. Reversible merge mechanics are absent

**Severity:** Medium  
**Status:** Remediated at the data/service layer; human-review UI remains intentionally deferred

The implementation is conservative about merges and retains mentions and decisions, but it has no decision-supersession or mapping-version mechanism to reverse an incorrect merge without rewriting a mapping. Human review is intentionally deferred, yet the underlying reversible data operation described by the PRD is also absent.

This aligns with the backlog items:

- add a human-review workflow for identity merge reversals;
- define stable external-identity and global-resolution policy.

### G14. Dashboard acceptance details are incomplete

**Severity:** Medium  
**Status:** Remediated

- The committed golden fixtures use a real bounded topic, but the dashboard replay uses a separate synthetic “Example Group” scenario.
- `possible_match` has no distinct visual style and appears like `active`.
- The decision panel displays object classification and decision ID, not stored candidate signals, confidence, rationale, or processing versions.
- The canonical graph is represented as node cards plus an edge list rather than a connected graph view.
- There are no automated frontend tests or committed results from the manual dashboard checklist.

### G15. Test-plan coverage is incomplete

**Severity:** Medium  
**Status:** Remediated

The existing suite is valuable and integration-heavy, but it does not cover:

- dependency rejection propagation;
- quantity normalization;
- versioned threshold policy;
- relationship deduplication and confirmation;
- entity-type fallback and epistemic enum rejection;
- evidence-free warnings;
- complete `as_of` support/provenance behavior;
- disputed/time/confidence filter semantics;
- raw-export status partitions;
- complete graph-expansion bounds and node content;
- merge reversal;
- frontend/dashboard behavior.

There is no configured lint, type-check, frontend-test, or CI workflow.

## 6. Intentionally left out

The following omissions agree with the PRD’s non-goals or deferred-work section and should not be counted as MVP defects:

- production deployment and autoscaling;
- queue-based or streaming ingestion;
- authentication, user accounts, RBAC, and fine-grained authorization;
- manual graph editing and a human-review UI;
- multilingual translation and cross-lingual identity resolution;
- global graph traversal;
- advanced ontology governance;
- automated causal reasoning;
- automated misinformation classification;
- deterministic replay of LLM outputs;
- safety-flag policy enforcement beyond preserving extension room;
- web search, crawling, primary research, or publisher fact-checking;
- story, script, podcast, translation, or audio generation;
- a graph database;
- LLM-based matching or normalization.

The backlog also defers:

- stable external-identity and global-resolution policy;
- production deployment, queues, and observability.

## 7. Verification results

The completed remediation ran the project-prescribed and newly configured checks against PostgreSQL 17:

| Check | Result |
| --- | --- |
| `docker compose up -d db` | Passed |
| `uv run alembic upgrade head` | Passed |
| `uv run alembic check` | Passed; no new upgrade operations detected |
| `uv run ruff check backend` | Passed |
| `PYTHONPATH=backend uv run mypy backend/app` | Passed; 16 source files |
| `PYTHONPATH=backend uv run pytest backend/tests -q` | Passed; 45 tests |
| `npm run lint --prefix frontend` | Passed |
| `npm run typecheck --prefix frontend` | Passed |
| `npm test --prefix frontend` | Passed; 3 acceptance tests |
| `npm run build --prefix frontend` | Passed; Vite production build completed |
| `npm audit --prefix frontend --omit=dev` | Passed; 0 vulnerabilities |
| `npm audit --prefix frontend` | Passed; 0 vulnerabilities |
| CI workflow dependency sync and YAML parsing | Passed locally |

## 8. Completion order used

1. Fix dependency-aware validation so partial acceptance cannot become a server error.
2. Add relationship candidate retrieval, deduplication, assertion aggregation, and tests.
3. Define the exact historical-projection contract and make `as_of` consistent across status, support, confidence, relationships, and lifecycle.
4. Add typed quantity normalization and safe contradiction comparison.
5. Implement controlled entity/epistemic enums, warnings, and versioned resolution thresholds.
6. Complete provenance/version fields for derived assertions and accepted input objects.
7. Finish retrieval filter semantics, graph-expansion content/bounds, query hints, and raw-export partitions.
8. Point the dashboard replay at the committed real-topic fixtures and expose full resolution-decision details with distinct possible-match styling.
9. Add the missing backend cases, frontend tests, lint/type checks, and CI.
10. Design reversible mapping/decision supersession before adding human review or global identity resolution.

## 9. Bottom line

The local hackathon MVP now meets all 11 explicit PRD section 22 acceptance criteria and closes G1–G15 with automated evidence. It preserves immutable Layer 1 input, applies conservative and reversible canonicalization, retains conflicting knowledge with provenance, serves bounded redacted Layer 3 views, and exposes graph evolution and decisions to operators.

Production deployment, authentication, queues, observability, global identity policy, and the human-review UI remain deliberately deferred under the PRD and backlog.

## 10. Remediation evidence

| Gap | Completed behavior | Primary evidence |
| --- | --- | --- |
| G1 | Validation reaches a dependency fixed point and rejects transitive dependents without losing independent objects. | `validation.py`; dependency rejection integration tests |
| G2 | Canonical relationship candidates match on endpoints, type, topic, and time; confirmations aggregate assertions instead of duplicating edges. | `canonicalization.py`; relationship reconciliation test |
| G3 | Historical views reconstruct lifecycle, claim and relationship status, support, confidence, creation time, and entity mapping revisions as known at `as_of`. | retrieval service; lifecycle, relationship-status, and mapping-revision tests |
| G4 | Quantities normalize values, units/currencies, bounds, approximation, population, measurement scope, and temporal scope; only compatible non-overlapping values contradict. | `normalization.py`; unit and ingestion tests |
| G5 | Entity and epistemic taxonomies, Unicode/alias normalization, unknown-type fallback, alias matching, and temporal ordering are enforced. | `policy.py`, validation/canonicalization services; taxonomy test |
| G6 | Sources, articles, evidence, graph objects, and retained relationship candidates receive Layer 2 IDs, decisions, mappings, revisions, provenance, and derivation metadata. | models/migrations; accepted-mention and retained-candidate tests |
| G7 | Thresholds, candidate bounds, versions, and decision outcomes are centralized in versioned policy. | `policy.py`; policy and ambiguous-match tests |
| G8 | The initial controlled relationship catalogue includes endpoint, inverse, symmetry, transitivity, inference, evidence, and temporal metadata. | `policy.py`; ontology policy test |
| G9 | Context, expansion, and raw export implement dispute, time, confidence, status, node, relationship, pagination, prioritization, coverage, detail, hint, and partition semantics. | retrieval API; filter/expansion/export tests |
| G10 | Article identity fingerprints publisher, canonical URL, and published time, while changed and duplicate content retain explicit lineage. | article model/migration and lineage test |
| G11 | Evidence-free claims and relationships are accepted with warnings, capped below high-confidence promotion, and surfaced in reports. | validation/canonicalization services; warning test |
| G12 | Automatic lifecycle transitions link directly to the ingestion that caused them; manual transitions remain distinguishable. | lifecycle migration/service and topic tests |
| G13 | Append-only mapping revisions and superseding decisions reverse a mapping without rewriting history; current and historical entity projections are tested. | `reconciliation.py`; mapping-revision test |
| G14 | The dashboard replays committed real-topic fixtures, renders connected graph edges with distinct possible-match styling, and shows complete decision details. | frontend components and acceptance tests |
| G15 | Backend/frontend tests, lint, type checks, migration drift, production build, dependency audits, and CI are configured and passing. | test suites, project configs, and `.github/workflows/ci.yml` |
