# Product Requirements Document
## Current Affairs Knowledge Graph — Layer 2

**Status:** Hackathon MVP
**Owner:** Layer 2 Team
**Source document:** `Current Affairs Knowledge Graph Layer PRD.pdf`
**Scope of this document:** An implementation-oriented restatement of the Layer 2 product requirements and architecture decisions agreed for the MVP.

## 1. Product definition

Layer 2 is a provenance-aware semantic memory system for a bounded, evolving current-affairs situation. It receives independent research deltas from Layer 1, stores them unchanged, reconciles their candidates into a canonical graph, preserves uncertainty and disagreement, and returns structured context to Layer 3.

Layer 2 transforms:

> Here is newly ingested research about this topic.

into:

> Here is the current, connected, traceable, uncertainty-aware representation of what Layer 1 has provided about this topic.

Layer 2 is not a research engine, fact-checker, web crawler, or story generator. It accepts Layer 1 material as trusted input for ingestion and provenance purposes. It must still distinguish reported, attributed, inferred, disputed, corrected, retracted, and superseded information so it never flattens competing perspectives into an unqualified fact.

## 2. System context and responsibilities

```text
Layer 1: research and ingestion
  - gathers raw source material
  - extracts structured candidates and evidence
  - sends self-contained deltas for a registered topic
            |
            v
Layer 2: knowledge graph
  - preserves raw packages
  - validates, normalizes, reconciles, versions, and retrieves graph knowledge
            |
            v
Layer 3: storytelling and inference
  - receives Layer 2 context
  - asks Layer 2 follow-up questions
  - creates stories, podcasts, and other narrative outputs
```

### 2.1 Layer 1 responsibilities

Layer 1:

- Collects research and source material.
- Extracts articles, entities, event candidates, claims, evidence, relationship candidates, and source assessments.
- Validates that extracted claims are grounded in its cited material.
- Sends independent, self-contained delta packages.
- Includes a registered `topic_key` but does not need any Layer 2 canonical IDs or earlier local IDs.
- May repeat entities, sources, articles, and claims in later packages when they are relevant to new material.

Layer 1 does **not** own canonical graph identity, graph status, duplicate classification, contradiction classification, or merge decisions.

### 2.2 Layer 2 responsibilities

Layer 2:

- Owns canonical topic, entity, event, claim, evidence, relationship, and source IDs.
- Stores every received Layer 1 package exactly as received.
- Validates package structure and internal references.
- Normalizes and resolves incoming candidates against existing graph knowledge.
- Classifies incoming material as new, duplicate, confirmation, clarification, correction, contradiction, retraction, or progression.
- Maintains source-to-claim-to-graph provenance internally.
- Makes conservative, reversible entity and event resolution decisions.
- Provides a topic-local graph API and a story-ready context API for Layer 3.
- Provides a local operator/demo dashboard for observing ingestion, graph evolution, and query results.

### 2.3 Layer 3 responsibilities

Layer 3:

- Uses Layer 2 as its sole knowledge boundary.
- Receives a self-contained, story-ready topic context and may make bounded follow-up graph queries.
- Owns narrative generation, creative inference, and the ultimate use of returned information.
- May request original story-relevant wording retained by Layer 2 when it needs texture or nuance.

Layer 3 must not receive Layer 1 transport identifiers, source URLs, publisher identifiers, or other Layer 1 ingestion metadata. Layer 2 returns canonical graph IDs and Layer 2-generated support summaries instead.

## 3. Goals

The MVP must:

1. Ingest Layer 1 research deltas for a registered topic.
2. Store every package immutably and make it replayable.
3. Create canonical graph objects from Layer 1 candidates.
4. Reconcile later independent deltas with existing graph knowledge.
5. Detect basic duplicates and possible matches conservatively.
6. Preserve conflicting, corrected, retracted, and superseded claims.
7. Preserve internal provenance for every material graph object.
8. Return a topic-level graph, ordered timeline, and story-ready context.
9. Let Layer 3 retrieve all story-relevant raw wording for a topic without revealing Layer 1 source/transport metadata.
10. Visualize graph updates and retrieval results locally.

## 4. Non-goals

The MVP will not:

- Search the web or collect primary source material.
- Independently fact-check or research publishers, articles, or claims.
- Declare one disputed claim to be universally true.
- Generate stories, dialogue, scripts, podcasts, translations, or audio.
- Provide manual graph editing or a human-review workflow.
- Provide production authentication, role-based access control, queues, streaming ingestion, or deployment infrastructure.
- Implement cross-lingual entity resolution, global graph traversal, automated causal reasoning, or sophisticated misinformation classification.
- Expose Layer 1 URLs, publisher identifiers, local IDs, or ingestion details to Layer 3.

## 5. Core design principles

### 5.1 Immutable input, derived graph

The exact Layer 1 payload is immutable. It is retained for audit, debugging, replay, and reconstruction.

Canonical graph objects are derived Layer 2 data. They may be created, updated, linked, superseded, marked disputed, or deactivated. A change to graph interpretation must never rewrite the stored Layer 1 package.

### 5.2 Layer 2 owns canonical identity

Layer 1 IDs are local to a package. They are never promoted directly to canonical graph IDs.

Layer 2 generates opaque UUIDs for canonical topics, entities, events, claims, sources, evidence records, relationships, and resolution decisions. It stores mappings from:

```text
(package_id, local_object_type, local_object_id) -> canonical_id
```

with the resolution outcome and decision metadata.

### 5.3 Preserve alternatives

Different reports, perspectives, values, corrections, and retractions remain present in the graph. Layer 2 may produce a current view, but it must retain the alternatives and their statuses.

### 5.4 Conservative and reversible resolution

An incorrect merge harms graph quality more than retaining two possible objects. Layer 2 should:

- auto-resolve only high-confidence matches;
- retain lower-confidence candidates as distinct canonical objects;
- link them through `POSSIBLY_SAME_AS` or `possible_contradiction`;
- retain all source-derived mentions and resolution decisions;
- reverse a merge by changing mappings and versioning decisions, not by deleting input.

### 5.5 No causality from sequence

Temporal order is not causal proof. Layer 2 may derive `BEFORE`, `AFTER`, or `FOLLOWS` when supported, but may not create a causal relationship merely because one event happened before another.

## 6. Topic lifecycle

Layer 2 owns the canonical topic registry.

Before ingestion, a topic is created through a Layer 2 topic-registration flow. Layer 2 returns:

- canonical `topic_id`;
- registered `topic_key`;
- display name;
- bounded scope;
- lifecycle status.

Layer 1 includes the registered `topic_key` in every package. Unknown topic keys are rejected during ingestion.

Topic statuses are:

- `active`
- `monitoring`
- `closed`
- `archived`

Layer 1 may provide a lifecycle recommendation, but Layer 2 records the canonical transition. Closing a topic does not remove graph data or prevent retrieval. A later package may reopen the topic through an auditable transition.

## 7. Layer 1 package contract

### 7.1 Delta model

Layer 1 sends independent deltas, not complete snapshots. For example:

```text
Package 1: a, b, c
Package 2: d, e, f
```

Package 2 may contain new information, corroboration, or material that changes Layer 2's interpretation of Package 1. Layer 1 does not need to know canonical IDs or previously submitted local IDs.

Omission from a later package means nothing. It is never a retraction, deletion, or correction by itself.

### 7.2 Self-contained packages

Every package is self-contained. Any local ID referenced by an event, claim, relationship, or evidence record must be defined in the same package.

If a new event refers to an entity previously sent in another package, Layer 1 includes that entity again as a fresh local entity candidate. Layer 2 resolves it to an existing canonical entity or creates a new one.

### 7.3 Required envelope

```json
{
  "schema_version": "1.0",
  "package_id": "delivery-uuid",
  "topic_key": "registered-topic-key",
  "metadata": {
    "title": "Human-readable topic title",
    "generated_at": "2026-07-25T10:30:00Z"
  },
  "sources": [],
  "articles": [],
  "evidence": [],
  "entities": [],
  "events": [],
  "claims": []
}
```

Recommended optional fields:

```json
{
  "relationships": [],
  "timeline": [],
  "uncertainties": [],
  "themes": [],
  "sentiment": []
}
```

`package_id` is a unique delivery/audit identifier. It is not a topic, event, or semantic content ID.

### 7.4 Sources and articles

Layer 1 may supply source and article metadata needed for internal Layer 2 provenance. A canonicalized article fingerprint should use:

- canonicalized URL;
- publisher;
- published timestamp, where available;
- hash of the received article text.

The same URL with changed article text is a new article version linked to the earlier article version, never an overwrite.

### 7.5 Evidence

Claims and events must be grounded in evidence records where possible:

```json
{
  "evidence_id": "ev_001",
  "article_id": "art_001",
  "excerpt": "Original supporting text.",
  "start_offset": 120,
  "end_offset": 220,
  "language": "en"
}
```

Evidence offsets refer to the immutable `articles[].content` supplied in the same package.

### 7.6 Entities

Each entity candidate has a package-local ID, original label, controlled type, aliases where known, and provenance references.

The MVP entity taxonomy is:

- Actors: `person`, `organization`, `government_body`, `government_agency`, `military_unit`, `armed_group`, `political_party`, `community_group`, `media_outlet`, `international_organization`
- Places: `country`, `administrative_region`, `city_or_locality`, `neighborhood`, `geographic_feature`, `facility_or_site`, `border_or_route`
- Things and concepts: `document`, `law_or_policy`, `court_case`, `agreement`, `infrastructure`, `vehicle_or_equipment`, `weapon_system`, `digital_account_or_channel`
- Fallback: `unknown`

Unrecognized Layer 1 types become `unknown` while preserving the original type label.

### 7.7 Events

An event represents one bounded happening or state change, not an entire conflict, campaign, protest movement, or war. Large situations are topics or event clusters containing smaller events.

Events should include:

```json
{
  "event_id": "evt_001",
  "type": "public_demonstration",
  "title": "Students assembled for protest",
  "description": "Original Layer 1 description",
  "temporal": {
    "start": "2026-07-20T10:00:00Z",
    "precision": "exact",
    "basis": "reported"
  },
  "participant_entity_ids": ["ent_001"],
  "location_entity_ids": ["ent_003"],
  "evidence_ids": ["ev_001"],
  "related_claim_ids": ["clm_001"]
}
```

### 7.8 Claims

Layer 1 retains the original claim text. It may also send extraction hints, which Layer 2 validates and normalizes:

```json
{
  "claim_id": "clm_001",
  "text": "Thousands of students protested in Delhi.",
  "evidence_ids": ["ev_001"],
  "event_id": "evt_001",
  "subject_ref": "ent_001",
  "predicate_candidate": "PARTICIPATED_IN",
  "object_ref_or_value": "evt_001",
  "temporal_scope": {
    "start": "2026-07-20",
    "precision": "day",
    "basis": "reported"
  },
  "asserted_by_entity_id": null,
  "epistemic_status": "reported"
}
```

Valid epistemic statuses include:

- `observed`
- `reported`
- `attributed`
- `corroborated`
- `disputed`
- `inferred`
- `interpretive`
- `unknown`
- `retracted`
- `superseded`

### 7.9 Relationship candidates

Layer 1 may provide extracted relationship candidates. Layer 2 owns normalization and canonical acceptance.

```json
{
  "relationship_id": "rel_001",
  "subject_ref": "ent_001",
  "object_ref": "evt_001",
  "source_relation_label": "joined",
  "evidence_ids": ["ev_001"],
  "extraction_confidence": 0.91
}
```

## 8. Validation

### 8.1 Whole-package rejection

Reject the package when its envelope is invalid:

- invalid JSON;
- unsupported or missing `schema_version`;
- missing `package_id`;
- missing or unknown `topic_key`;
- missing required top-level collections;
- structurally invalid payload.

The exact raw package and the rejection report are retained.

### 8.2 Object-level rejection

For a valid package envelope, accept valid objects and reject invalid objects individually. Object-level failures include:

- missing required fields;
- duplicate local IDs within the package;
- references to nonexistent local IDs;
- invalid timestamps;
- malformed evidence offsets;
- invalid confidence shape or value;
- relationship endpoints that violate the controlled ontology.

### 8.3 Ingestion outcome

Every ingestion returns one of:

- `accepted`
- `accepted_with_warnings`
- `partially_accepted`
- `rejected`

The report includes accepted and rejected local IDs, errors, warnings, classification results, canonical mappings, processing duration, and processing version.

## 9. Idempotency and package revisions

Layer 2 calculates a checksum from the exact received payload.

| Situation | Required behavior |
| --- | --- |
| Same `package_id`, schema version, and checksum | Treat as retry; return the existing ingestion result. |
| Same `package_id`, different checksum | Store a new immutable package revision and process it. |
| Different `package_id`, same checksum | Record duplicate delivery/audit information; do not duplicate canonical graph objects. |
| Different payloads describing the same real-world object | Reconcile through normal entity, event, claim, and relationship resolution. |

Idempotency prevents repeated processing of the same payload. It does not replace semantic duplicate detection.

## 10. Canonical graph model

### 10.1 First-class graph objects

The graph stores first-class, versioned records for:

- topics;
- entities;
- entity mentions;
- events;
- event mentions;
- claims;
- evidence;
- sources and article versions;
- relationships;
- relationship assertions;
- provenance mappings;
- confidence assessments;
- resolution decisions;
- ingestion runs;
- topic lifecycle transitions.

Relationships are first-class objects, not anonymous edges. They have a canonical ID, endpoints, type, status, temporal scope, evidence, confidence assessments, and derivation metadata.

### 10.2 Source-derived mentions and canonical clusters

Incoming Layer 1 entities and events are retained as source-derived mentions. A resolution mapping associates a mention with a canonical entity or event.

This allows Layer 2 to:

- merge high-confidence matches;
- keep possible matches separate;
- reverse a merge later;
- explain why a mapping was made;
- retain every original label and evidence link.

### 10.3 Claims and assertions

Claims preserve their original text and may additionally contain a Layer 2-derived structured form:

- subject;
- controlled predicate;
- object or typed value;
- event/topic scope;
- temporal scope;
- epistemic status;
- provenance;
- support and confidence assessments.

Derived claim fields are not source replacements. Each derived field records its method, inputs, confidence, and processing version.

### 10.4 Mutable facts are time-bounded assertions

Roles, control of territory, organizational status, and similar changing facts are represented as time-bounded, provenance-backed claims or relationships. They are not stored as permanent entity properties.

## 11. Reconciliation and update classification

For each accepted object, Layer 2:

1. Normalizes labels, temporal expressions, entity types, relationship labels, and values.
2. Retrieves likely candidates from the same topic and, for eligible high-confidence identities, the global entity graph.
3. Applies deterministic matching signals first.
4. Optionally uses an LLM only for bounded, structured match scoring or normalization.
5. Applies graph policy to classify and create a canonical object, mapping, or candidate relationship.
6. Records decision inputs, outcome, rationale, scores, and pipeline version.

### 11.1 Matching policy

Candidate retrieval may use:

- `topic_key`;
- normalized names and aliases;
- time and temporal overlap;
- place;
- participants;
- source/article fingerprints;
- evidence overlap;
- structured subject-predicate-object form;
- embedding similarity or constrained LLM scoring.

Auto-merge requires a deliberately high threshold. Lower-confidence cases remain separate and are linked as possible matches.

### 11.2 Classifications

- **New:** no existing canonical object represents the incoming material.
- **Duplicate:** substantially the same underlying object is already present.
- **Confirmation:** independent evidence supports an existing claim or event.
- **Clarification:** compatible precision is added without invalidating earlier information.
- **Correction:** new material explicitly or strongly indicates a prior report is incorrect.
- **Contradiction:** two claims cannot both hold for the same subject, predicate, scope, and timeframe.
- **Retraction:** a prior claim is withdrawn by its source or claimant.
- **Progression:** the situation changed over time; the claims describe different states rather than incompatible ones.

Layer 1 does not need to label these classes. Layer 2 decides them from graph context and incoming material.

### 11.3 Contradictions

Layer 2 initially creates `possible_contradiction`. It promotes the relationship to `confirmed_contradiction` only when claims have compatible scope and mutually incompatible values.

Quantities are never compared as bare numbers. A normalized value includes:

- original wording;
- value;
- unit/currency;
- range or bounds;
- approximation status;
- population or measurement scope;
- temporal scope.

For example, “500 displaced by Friday” and “1,000 displaced since the conflict began” are not automatically contradictory.

### 11.4 Event resolution

Event resolution is stricter than entity resolution. Time, location, participants, action, and topic should align before Layer 2 maps two event mentions to one canonical event.

Potential phases remain separate events connected by relationships such as `PART_OF`, `FOLLOWS`, or `ESCALATES`.

### 11.5 Current representation and history

Layer 2 never destructively overwrites a prior graph interpretation. It versions derived assertions and resolution decisions, marks previous representations as superseded or reversed, and selects current active representations for normal retrieval.

An `as_of` processing timestamp allows retrieval of the graph as it was known at an earlier time.

## 12. Controlled relationship ontology

The MVP uses a versioned controlled ontology. The exact catalogue may grow, but every relation must define:

- valid subject and object types;
- inverse relation, when applicable;
- symmetry/transitivity behavior;
- whether it may be inferred;
- evidence requirements;
- temporal behavior.

Initial groups include:

### 12.1 Participation and institutional relations

- `PARTICIPATED_IN`
- `ORGANIZED`
- `ANNOUNCED`
- `RESPONDED_TO`
- `AFFECTED_BY`
- `LOCATED_AT`
- `TARGETED`
- `REPRESENTED_BY`

### 12.2 Event relations

- `BEFORE`
- `AFTER`
- `DURING`
- `PART_OF`
- `FOLLOWS`
- `RESPONDS_TO`
- `ESCALATES`
- `DEESCALATES`
- `CONTRIBUTES_TO`

### 12.3 Claim and evidence relations

- `SUPPORTS`
- `CONTRADICTS`
- `CLARIFIES`
- `CORRECTS`
- `RETRACTS`
- `SUPERSEDES`
- `DUPLICATES`

### 12.4 Identity relations

- `SAME_AS`
- `POSSIBLY_SAME_AS`
- `ALIAS_OF`
- `SUBSET_OF`
- `RELATED_TO`

Layer 2 may infer safe structural relations such as supported temporal order and possible identity. Substantive or causal relations, including `CAUSED`, `RESPONSIBLE_FOR`, and `SUPPORTED_BY`, require explicit source-backed assertions and must remain attributed rather than Layer 2-established facts.

Unrecognized relationship labels are retained as candidates with their original wording. They are not written directly into the canonical ontology.

## 13. Time model

Every temporal value supports:

- `start`;
- optional `end`;
- `precision`: `exact`, `approximate`, `day`, `month`, `range`, or `unknown`;
- `basis`: `reported` or `inferred`.

Layer 2 distinguishes:

- when an event occurred;
- when a claim applies;
- when a source was published;
- when Layer 1 retrieved or generated the item, when supplied;
- when Layer 2 received and processed the package;
- when the graph object and interpretation were created or superseded.

Late-arriving material is inserted according to event time in timelines while retaining its later receipt/processing time in audit history.

## 14. Confidence model

Confidence is a typed assessment, not a universal truth score.

Each assessment includes:

```json
{
  "dimension": "entity_resolution",
  "value": 0.93,
  "assessed_by": "layer_2_rule",
  "method": "name-time-location-match",
  "model_or_rule_version": "kg-pipeline-0.1",
  "rationale": "Normalized name and location match; overlapping event time.",
  "supporting_ids": ["..."],
  "assessed_at": "2026-07-25T10:30:00Z"
}
```

Supported dimensions:

- `extraction`
- `source_reliability`
- `claim_support`
- `entity_resolution`
- `event_resolution`
- `relationship_resolution`
- `interpretation`

Layer 1 may provide extraction and source assessments. Layer 2 records them as Layer 1-provided information and may use them for prioritization or retrieval filtering. Layer 2 does not independently research sources for the MVP.

Low confidence is a retrieval preference, not an ingestion gate. Structurally valid, provenance-backed low-confidence information is stored with warnings rather than silently discarded.

## 15. Internal provenance

Layer 2 internally maintains the provenance chain:

```text
canonical graph object
  -> Layer 1 object/claim
  -> evidence excerpt
  -> article/source
  -> immutable package
```

Derived graph objects also record:

- derivation method;
- inputs;
- confidence;
- processing/pipeline version;
- creation timestamp;
- resolution decision ID, where relevant.

This internal provenance is necessary for audit, replay, debugging, and correction. It is not automatically exposed to Layer 3.

## 16. Retrieval for Layer 3

### 16.1 Retrieval principles

Layer 3 talks only to Layer 2 APIs. All retrieval is topic-local by default and bounded by node, relationship, time, and response-size limits.

The initial context must be:

1. self-sufficient enough for Layer 3 to understand the known situation; and
2. navigable enough for Layer 3 to ask more informed follow-up questions.

### 16.2 Story-ready topic context

The default topic context returns:

- topic summary and lifecycle;
- ordered event sequence;
- main actors and roles;
- active canonical claims;
- relationship summaries;
- disputes, corrections, retractions, and uncertainty;
- themes and sentiment labelled as interpretive;
- support summaries;
- canonical IDs, coverage information, truncation information, and query hints.

Every material returned object includes:

- canonical Layer 2 ID;
- status;
- temporal scope;
- confidence dimensions;
- relevant graph relationships;
- a Layer 2-generated support summary.

A support summary may include counts and assessments such as:

```json
{
  "source_count": 3,
  "independent_source_count": 2,
  "assessment": "corroborated"
}
```

It does not expose Layer 1 source URLs, publishers, local IDs, or transport metadata.

### 16.3 Raw story material

Layer 3 may request raw story-relevant material retained by Layer 2. This returns original claim and evidence wording, organized by canonical Layer 2 graph IDs and statuses.

Raw responses remove:

- Layer 1 source URLs;
- publisher identifiers;
- Layer 1 local IDs;
- package/delivery identifiers;
- other Layer 1 transport metadata.

Layer 3 may retrieve:

- raw material for a selected graph object; or
- a complete, paginated raw topic export.

Full-topic raw exports are partitioned into:

- `active`;
- `disputed`;
- `superseded`;
- `retracted`.

This makes historical texture available for storytelling without presenting stale material as current knowledge.

### 16.4 Context boundaries and pagination

The default context response uses a generous budget, initially targeting approximately:

- 200 graph nodes;
- 500 relationships.

Prioritization is deterministic:

1. topic-defining and recent events;
2. high-connectivity actors;
3. active disputes;
4. safety/status summaries;
5. supporting graph context.

Responses include:

- `truncated`;
- `next_cursor`;
- coverage summary;
- omitted-object counts;
- suggested follow-up graph expansions.

## 17. API surface

The MVP exposes a small local REST API:

| Endpoint | Purpose |
| --- | --- |
| `POST /topics` | Register a Layer 2-owned topic and return its `topic_key`. |
| `POST /ingestions` | Validate, store, reconcile, and report on a Layer 1 package. |
| `GET /topics/{topic_id}/context` | Return self-contained story-ready topic context. |
| `GET /topics/{topic_id}/timeline` | Return ordered canonical events and relevant statuses. |
| `GET /entities/{entity_id}/context` | Return topic-scoped information about an entity. |
| `GET /claims/{claim_id}/evidence` | Return canonical claim context and permitted raw wording. |
| `POST /graph/expand` | Return bounded graph expansion from supplied canonical IDs. |
| `GET /topics/{topic_id}/raw-export` | Return complete paginated, story-relevant raw material. |
| `GET /ingestions/{ingestion_id}` | Return ingestion and resolution report for operator use. |

All graph-expansion endpoints enforce topic boundaries and accept limits for depth, node count, relationship types, time range, confidence, and status inclusion.

## 18. Local operator dashboard

The MVP includes a local read-only operator/demo dashboard. It is not a graph editing interface.

The dashboard supports:

- choosing a topic;
- viewing the canonical graph;
- viewing the ordered event timeline;
- coloring nodes and edges by status, including `active`, `disputed`, `superseded`, and `possible match`;
- inspecting a received delta;
- inspecting the ingestion report and resolution decisions;
- replaying seeded ingestions to show graph evolution;
- running a Layer 3-style query and displaying the returned context and graph coverage.

Manual graph edits are out of scope because they require a separate authoring, provenance, and authorization model.

## 19. Local implementation shape

The hackathon implementation runs locally:

- **API and reconciliation pipeline:** Python with FastAPI.
- **Database:** locally available PostgreSQL.
- **Dashboard:** small React application.
- **Documentation:** OpenAPI plus a seeded demo scenario and local startup instructions.

No Docker, deployment platform, queue, production observability stack, user accounts, or role-based access control is required for the MVP.

Canonical graph updates for the same topic are serialized through a database transaction or lock. Raw packages may be stored immediately, but reconciliation must see a stable topic graph to avoid concurrent duplicate creation.

## 20. Observability and explainability

Every ingestion run records:

- package received;
- validation outcome;
- raw-storage result;
- created and matched entities;
- created and matched events;
- claims and relationships added;
- possible matches;
- contradictions and update classifications;
- warnings and failures;
- processing duration;
- schema, graph-model, and pipeline versions.

Every automated resolution decision stores:

- incoming object;
- candidate canonical IDs;
- result;
- matching signals;
- confidence;
- rationale;
- model/rule and prompt/template version, if applicable;
- inputs and timestamp.

LLMs may be used for constrained normalization or match scoring only after deterministic candidate retrieval. Their structured outputs must pass schema and ontology validation before policy decides whether the result becomes canonical, possible, or rejected.

## 21. Evaluation

Maintain a small versioned golden corpus of Layer 1 delta packages and expected outcomes:

- canonical entities and events;
- duplicate links;
- possible matches;
- clarification/correction/retraction outcomes;
- possible and confirmed contradictions;
- timeline order;
- story-ready retrieval output.

The automated tests run the pipeline against this corpus and assert graph shape, statuses, provenance mappings, and retrieval responses. This provides a controlled way to tune thresholds, rules, prompts, and ontology versions.

## 22. Demo scenario and acceptance criteria

The demo uses one bounded, real current-affairs topic and three self-contained Layer 1 delta packages:

1. **Initial population:** initial articles, entities, events, claims, evidence, and relationships.
2. **New information:** additional events and corroboration that resolve against existing canonical objects.
3. **Change or conflict:** a correction, competing claim, or retraction that Layer 2 preserves and displays.

The MVP is accepted when:

- a registered topic receives each package without Layer 1 needing previous canonical context;
- all packages remain immutable and retrievable internally;
- Layer 2 creates its own canonical IDs;
- repeated delivery of the same payload produces no duplicate graph objects;
- later packages reconcile with prior graph objects where confidence is high;
- ambiguous matches remain separate and visibly linked as possible matches;
- conflicting and corrected claims remain available with explicit status;
- the timeline orders events by event time, not package arrival time;
- Layer 3 receives a self-contained topic context and can make bounded follow-up queries;
- Layer 3 can request a complete raw topic export without receiving Layer 1 URLs, publishers, local IDs, or delivery metadata;
- the dashboard visibly shows graph evolution, decisions, and query responses.

## 23. Deferred work

The following are intentionally deferred:

- production deployment and scaling;
- queue-based or streaming ingestion;
- user authentication and fine-grained access control;
- human review and manual graph editing;
- multilingual translation and cross-lingual identity resolution;
- global graph traversal;
- advanced ontology governance;
- automated causal reasoning;
- automated misinformation classification;
- strict deterministic replay of LLM outputs;
- safety-flag policy enforcement beyond preserving room in the model for future flags.

## 24. Development blueprint

This section is normative for the MVP implementation. Names may vary in code, but equivalent behavior and constraints are required.

### 24.1 Service boundaries

The local system consists of three processes:

1. **Layer 2 API:** FastAPI application that owns validation, storage, reconciliation, and retrieval.
2. **PostgreSQL:** authoritative store for immutable packages and derived graph state.
3. **Operator dashboard:** React application that calls only Layer 2 APIs.

There is no direct Layer 1-to-database or Layer 3-to-database access.

### 24.2 Recommended backend modules

```text
backend/
  app/
    api/
      topics.py
      ingestions.py
      retrieval.py
      graph.py
      operator.py
    contracts/
      layer1_models.py
      api_models.py
      enums.py
    services/
      validation.py
      ingestion.py
      normalization.py
      candidate_retrieval.py
      entity_resolution.py
      event_resolution.py
      claim_resolution.py
      relationship_resolution.py
      contradiction_detection.py
      retrieval.py
      raw_export.py
    repositories/
      topics.py
      packages.py
      graph.py
      decisions.py
    db/
      models.py
      migrations/
    tests/
      unit/
      integration/
      golden/
```

The API layer must not contain reconciliation rules. The service layer owns the rules; repositories own database access; contracts own request and response validation.

### 24.3 Processing versions

Define the following configuration values before implementing ingestion:

```text
input_schema_version = "1.0"
graph_model_version = "0.1"
pipeline_version = "kg-pipeline-0.1"
ontology_version = "0.1"
```

Persist all four on every ingestion run and every derived decision. A later change to matching or normalization must increment `pipeline_version` rather than silently revising the meaning of old decisions.

## 25. PostgreSQL data model

### 25.1 Storage conventions

- Canonical IDs are UUIDs generated by Layer 2.
- Timestamps use `timestamptz`.
- Immutable raw package payloads use `jsonb`.
- Graph status and type columns use PostgreSQL enums or checked text values.
- Do not use database-level cascading deletes for provenance-bearing records.
- Use `created_at`, `updated_at`, and where relevant `superseded_at` / `superseded_by_id`.
- Every record derived from a package must retain `ingestion_id` or an indirect provenance link to it.

### 25.2 Core tables

| Table | Purpose | Key fields |
| --- | --- | --- |
| `topics` | Canonical Layer 2 topic registry | `id`, `topic_key`, `display_name`, `scope_json`, `status` |
| `topic_lifecycle_transitions` | Auditable topic status changes | `id`, `topic_id`, `from_status`, `to_status`, `reason`, `ingestion_id` |
| `raw_packages` | Immutable exact Layer 1 payload | `id`, `package_id`, `schema_version`, `topic_id`, `payload`, `payload_checksum`, `revision` |
| `ingestion_runs` | Processing result for one received package/revision | `id`, `raw_package_id`, `status`, `pipeline_version`, `report_json`, `started_at`, `completed_at` |
| `source_mentions` | Layer 1 source objects, internal only | `id`, `raw_package_id`, `local_id`, `publisher`, `url`, `published_at` |
| `article_versions` | Received article text and its version fingerprint | `id`, `source_mention_id`, `canonical_url`, `content_hash`, `content`, `language` |
| `evidence_mentions` | Exact source-derived excerpts | `id`, `raw_package_id`, `local_id`, `article_version_id`, `excerpt`, `start_offset`, `end_offset` |
| `canonical_entities` | Canonical entity clusters | `id`, `canonical_label`, `entity_type`, `status`, `global_eligible` |
| `entity_mentions` | Layer 1 entity candidates | `id`, `raw_package_id`, `local_id`, `label`, `source_type`, `canonical_entity_id` |
| `canonical_events` | Canonical bounded happenings | `id`, `topic_id`, `display_title`, `event_type`, `status` |
| `event_mentions` | Layer 1 event candidates | `id`, `raw_package_id`, `local_id`, `canonical_event_id`, `original_title`, `original_description` |
| `claims` | Source-derived claims with original wording | `id`, `topic_id`, `original_text`, `epistemic_status`, `status`, `canonical_event_id` |
| `claim_assertions` | Structured, versioned interpretation of a claim | `id`, `claim_id`, `subject_id`, `predicate`, `object_json`, `temporal_json`, `status` |
| `graph_relationships` | First-class canonical graph relation records | `id`, `topic_id`, `subject_id`, `object_id`, `relationship_type`, `status`, `temporal_json` |
| `relationship_assertions` | Evidence-backed assertion or derivation for a relation | `id`, `relationship_id`, `assertion_kind`, `status`, `rationale` |
| `provenance_links` | Generic graph-object to input/evidence mapping | `id`, `graph_object_type`, `graph_object_id`, `evidence_mention_id`, `claim_id`, `raw_package_id` |
| `confidence_assessments` | Typed confidence records | `id`, `subject_type`, `subject_id`, `dimension`, `value`, `assessed_by`, `method` |
| `resolution_decisions` | Explainable match/classification decisions | `id`, `ingestion_id`, `incoming_type`, `incoming_id`, `outcome`, `rationale`, `signals_json` |
| `local_id_mappings` | Immutable local-to-canonical mappings | `id`, `raw_package_id`, `local_type`, `local_id`, `canonical_type`, `canonical_id`, `decision_id` |

`graph_relationships.subject_id` and `object_id` may point to different graph object types. Implement this either with a `graph_objects` registry table or with explicit endpoint type columns:

```text
subject_type, subject_id, object_type, object_id
```

The second approach is simpler for the MVP and must be validated in application code.

### 25.3 Required indexes and uniqueness constraints

At minimum create:

```text
topics(topic_key) UNIQUE
raw_packages(package_id, schema_version, payload_checksum) UNIQUE
raw_packages(payload_checksum)
raw_packages(topic_id, received_at DESC)
ingestion_runs(raw_package_id)
entity_mentions(raw_package_id, local_id) UNIQUE
event_mentions(raw_package_id, local_id) UNIQUE
evidence_mentions(raw_package_id, local_id) UNIQUE
local_id_mappings(raw_package_id, local_type, local_id) UNIQUE
canonical_events(topic_id, status)
claims(topic_id, status)
graph_relationships(topic_id, relationship_type, status)
resolution_decisions(ingestion_id, incoming_type)
```

Add PostgreSQL full-text or trigram indexes for normalized entity labels and event titles if candidate retrieval needs them. Do not add vector storage until lexical and structured candidate retrieval is demonstrated to be inadequate.

### 25.4 Immutability rules

Application code must never issue `UPDATE` or `DELETE` against:

- `raw_packages.payload`;
- original article text;
- evidence excerpt text;
- local IDs;
- original Layer 1 claim text.

Corrections are represented through new rows, statuses, and relationships. Database permissions or triggers may enforce this later; application-level guarantees are sufficient for the hackathon if covered by tests.

## 26. Ingestion transaction specification

### 26.1 Processing sequence

`POST /ingestions` follows this sequence:

1. Parse the request body and calculate the exact payload checksum.
2. Validate the package envelope.
3. Resolve the registered `topic_key`; reject unknown topics.
4. Check idempotency by package ID, schema version, and checksum.
5. Store the exact payload in `raw_packages` and create `ingestion_runs`.
6. Acquire a transaction-scoped advisory lock for the canonical topic.
7. Run object-level validation and write validation results.
8. Persist accepted source/article/evidence/entity/event/claim/relationship mentions.
9. Normalize accepted candidates without changing their original fields.
10. Resolve entities, events, claims, and relationships in dependency order.
11. Classify updates; create provenance links, confidence assessments, mappings, and resolution decisions.
12. Build and persist the ingestion report.
13. Commit the transaction and return the report.

If the envelope is invalid, store the raw package and a rejected `ingestion_run` when the payload can be retained safely, then return a deterministic error response. No derived graph objects may be created.

### 26.2 Dependency order

Resolve in this order:

```text
source/article/evidence
  -> entity mentions
  -> event mentions
  -> claims and claim assertions
  -> relationship candidates
  -> contradiction and update classification
  -> retrieval projections/report
```

A failure for one object must not make valid, independent objects unavailable. Objects with broken local references are rejected and reported; valid objects are processed.

### 26.3 Transaction pseudocode

```python
def ingest(payload: dict) -> IngestionReport:
    checksum = sha256(canonical_request_bytes(payload))
    envelope = validate_envelope(payload)
    topic = topic_repository.get_by_key(envelope.topic_key)
    idempotent_result = package_repository.find_retry(
        envelope.package_id, envelope.schema_version, checksum
    )
    if idempotent_result:
        return idempotent_result.report

    raw_package, run = package_repository.store_immutable(payload, checksum, topic)

    with topic_repository.lock(topic.id), database.transaction():
        validated = validate_objects(payload)
        mentions = mention_repository.store(validated.accepted, raw_package.id)
        normalized = normalization_service.normalize(mentions)
        decisions = reconciliation_service.resolve(topic.id, normalized, run.id)
        report = report_service.build(run, validated, decisions)
        ingestion_repository.complete(run.id, report)

    return report
```

The actual implementation must ensure the raw package and final report survive together. The pseudocode illustrates responsibilities, not a required ORM or transaction library.

### 26.4 Ingestion response

Successful responses return HTTP `200` for an idempotent retry and HTTP `201` for a newly processed package.

```json
{
  "ingestion_id": "uuid",
  "package_id": "delivery-uuid",
  "topic_id": "uuid",
  "status": "partially_accepted",
  "pipeline_version": "kg-pipeline-0.1",
  "summary": {
    "accepted": 14,
    "rejected": 1,
    "created": 7,
    "matched": 4,
    "possible_matches": 2,
    "contradictions": 1
  },
  "object_results": [],
  "warnings": [],
  "errors": []
}
```

`object_results` contains the local ID, canonical ID where created or resolved, classification, status, and decision ID for each accepted or rejected object.

## 27. Reconciliation policy specification

### 27.1 Deterministic candidate retrieval

Candidate retrieval must constrain the comparison set before any model-based scoring:

| Incoming type | Minimum candidate filters |
| --- | --- |
| Entity | normalized label/alias, compatible entity type, topic scope or global eligibility |
| Event | topic, overlapping or nearby time, compatible event type, shared location/participants when available |
| Claim | topic, normalized subject/predicate, compatible temporal scope, linked event where available |
| Relationship | topic, endpoint identity/type, normalized relation type, overlapping time |

For the MVP, candidate retrieval should return a small bounded list, such as the top 10 candidates. If no candidate passes basic filters, create a new canonical object without invoking an LLM.

### 27.2 Decision outcomes

Every resolver returns exactly one outcome:

```text
CREATE_NEW
RESOLVE_TO_EXISTING
CREATE_POSSIBLE_MATCH
CREATE_DUPLICATE_LINK
CREATE_CLARIFICATION
CREATE_CORRECTION
CREATE_POSSIBLE_CONTRADICTION
CREATE_CONFIRMED_CONTRADICTION
CREATE_PROGRESSION
REJECT
```

The outcome must be persisted as a resolution decision and reflected in the ingestion report.

### 27.3 Thresholds

Keep thresholds in a versioned configuration file:

```text
entity_auto_resolve_threshold = 0.90
event_auto_resolve_threshold = 0.92
possible_match_threshold = 0.70
contradiction_confirmation_threshold = 0.90
```

These are initial defaults, not proof of factual truth. Tests against the golden corpus determine any adjustments. Threshold changes require a new pipeline version.

### 27.4 LLM guardrails

If an LLM is used, its input must contain only:

- the incoming normalized candidate;
- a bounded list of retrieved candidates;
- controlled ontology choices;
- required JSON output schema.

The LLM must not:

- search the web;
- invent new relation labels;
- create a canonical ID;
- decide a merge without policy validation;
- infer causality from order;
- overwrite original input.

Invalid structured output results in a warning and a conservative outcome (`CREATE_NEW` or `CREATE_POSSIBLE_MATCH`), never a guessed merge.

## 28. Detailed API contracts

### 28.1 Topic registration

`POST /topics`

```json
{
  "topic_key": "war-example-2026",
  "display_name": "Bounded current-affairs situation",
  "scope": {
    "description": "What the topic includes and excludes",
    "geography": ["..."],
    "start": "2026-07-01",
    "end": null
  }
}
```

Response:

```json
{
  "topic_id": "uuid",
  "topic_key": "war-example-2026",
  "status": "active",
  "created_at": "2026-07-25T10:30:00Z"
}
```

### 28.2 Topic context

`GET /topics/{topic_id}/context`

Supported query parameters:

```text
as_of=<processing timestamp, optional>
include_disputed=true|false
include_interpretations=true|false
minimum_confidence=<0..1, optional>
max_nodes=<1..200, default 200>
max_relationships=<1..500, default 500>
time_start=<ISO 8601, optional>
time_end=<ISO 8601, optional>
cursor=<opaque cursor, optional>
```

Response shape:

```json
{
  "topic": {},
  "summary": {
    "text": "Strictly graph-derived summary or structured summary fields.",
    "claim_ids": ["uuid"]
  },
  "timeline": [],
  "entities": [],
  "events": [],
  "claims": [],
  "relationships": [],
  "disputes": [],
  "interpretations": [],
  "coverage": {
    "returned_nodes": 0,
    "returned_relationships": 0,
    "omitted_nodes": 0,
    "truncated": false,
    "next_cursor": null
  },
  "query_hints": {
    "available_expansions": [],
    "raw_export_available": true
  }
}
```

The summary must identify source claim IDs for every substantive statement. For the MVP, a structured summary is preferred over unconstrained generated prose.

### 28.3 Graph expansion

`POST /graph/expand`

```json
{
  "topic_id": "uuid",
  "seed_ids": ["uuid"],
  "relationship_types": ["RESPONDED_TO", "CONTRADICTS"],
  "max_depth": 2,
  "max_nodes": 100,
  "include_disputed": true,
  "as_of": null
}
```

The service rejects seed IDs outside the supplied topic and rejects unbounded requests.

### 28.4 Raw export

`GET /topics/{topic_id}/raw-export`

Query parameters:

```text
status=active,disputed,superseded,retracted
event_id=<optional canonical event UUID>
claim_id=<optional canonical claim UUID>
cursor=<opaque cursor>
limit=<1..100>
```

Each item returns canonical IDs, status, time, raw story-relevant wording, and a Layer 2 support summary. It must not return Layer 1 URLs, publishers, local IDs, package IDs, raw source metadata, or database-internal fields.

## 29. Test plan

### 29.1 Unit tests

Unit test:

- Pydantic/schema validation and error messages;
- checksums and idempotency decisions;
- local reference validation;
- temporal precision parsing;
- quantity normalization;
- ontology endpoint validation;
- status transitions;
- candidate retrieval filters;
- threshold policy;
- raw-export redaction of Layer 1 metadata.

### 29.2 Integration tests

Run against a real local PostgreSQL database:

- topic registration and unknown-topic rejection;
- raw package immutability;
- partial acceptance;
- package retry and revised package handling;
- same-topic serialization;
- source/article versioning;
- entity and event mapping;
- correction, retraction, and contradiction persistence;
- `as_of` retrieval;
- response pagination and topic boundary enforcement.

### 29.3 Golden scenario

The seeded three-delta demo must have committed expected outputs:

```text
fixtures/
  topic.json
  delta-01-initial.json
  delta-02-update.json
  delta-03-conflict.json
  expected/
    final-context.json
    final-timeline.json
    final-raw-export.json
    ingestion-reports.json
```

The test asserts canonical IDs only when fixtures intentionally pin them; otherwise it asserts stable object counts, mappings, statuses, relations, and ordering.

### 29.4 Dashboard acceptance checks

Manual checks for the demo:

1. Reset the local database and register the demo topic.
2. Submit Delta 1 and verify initial graph/timeline creation.
3. Submit Delta 2 and verify new nodes plus resolved links to existing objects.
4. Submit Delta 3 and verify a visible correction or dispute without loss of prior material.
5. Run a story-context query and verify the returned coverage information.
6. Run a raw export and verify raw wording is present while URLs, publishers, local IDs, and delivery IDs are absent.
