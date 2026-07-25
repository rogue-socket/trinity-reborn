# world_builder_service

Echoes' small FastAPI service that converts a Layer 2 topic context into a persisted fictional world bible. It implements only `POST /build-world` and `GET /health`.

## Run

From the repository root, first start and seed Layer 2:

```powershell
docker compose -f layer2_mock/docker-compose.yml up -d
python -m layer2_mock.seed prds/fixture-topic-context.json
uvicorn layer2_mock.main:app --port 8000
```

In a second terminal, configure the world builder and start it:

```powershell
$env:OPENAI_API_KEY = "your-key"
# Optional; these are the defaults:
# $env:LAYER2_BASE_URL = "http://localhost:8000"
# $env:WORLD_BIBLE_DIR = "./world_bible"
uv sync
uv run uvicorn world_builder_service.main:app --port 8001
```

Call it with:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8001/build-world `
  -ContentType "application/json" `
  -Body '{"topic_id":"3f7a1b2c-0001-4a10-9c11-000000000001"}'
```

The service makes one Structured Outputs OpenAI call for a generation batch, validates the final `world.json` and `characters.json` schemas, and writes them under `WORLD_BIBLE_DIR/<topic_id>/`. On later calls it preserves the existing world and only asks the model for unmapped entities and missing characters.

If Layer 2 returns 404, the service returns a clear 404. A malformed Layer 2 context results in 502. Missing `OPENAI_API_KEY` returns a clear 503 without writing files.
