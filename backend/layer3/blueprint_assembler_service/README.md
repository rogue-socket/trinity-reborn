# blueprint_assembler_service

Deterministic, LLM-free assembly of Layer 2 context + world bible into a story blueprint.

## Run

Requires Layer 2 and a completed world bible for the topic. From the repo root:

```sh
uv run uvicorn backend.layer3.blueprint_assembler_service.main:app --port 8002
```

```sh
curl -sX POST http://127.0.0.1:8002/build-blueprint \
  -H 'content-type: application/json' \
  -d '{"topic_id":"<topic-uuid>"}'
```

Artefacts default to `<repo>/world_bible` and `<repo>/blueprints` (override via `.env`).
