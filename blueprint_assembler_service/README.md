# blueprint_assembler_service

Deterministic, LLM-free assembly of Layer 2 context and a completed World Bible into the Story Blueprint consumed by downstream generators.

## Run

Start and seed Layer 2, then ensure `WORLD_BIBLE_DIR/<topic_id>/world.json` and `characters.json` exist (run `world_builder_service` first). From the repository root:

```powershell
uv sync
uv run uvicorn blueprint_assembler_service.main:app --port 8002
```

`LAYER2_BASE_URL`, `WORLD_BIBLE_DIR`, and `BLUEPRINT_DIR` are loaded from `.env`, with defaults of `http://localhost:8000`, `./world_bible`, and `./blueprints`.

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8002/build-blueprint `
  -ContentType "application/json" `
  -Body '{"topic_id":"3f7a1b2c-0001-4a10-9c11-000000000001"}'
```

The service never calls an LLM. Its UUID and ISO timestamp are content-derived from the Layer 2 and World Bible inputs, so unchanged inputs produce identical blueprint JSON.
