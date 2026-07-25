# Orchestrator Service

This FastAPI service only coordinates the Echoes services over HTTP. It does not call an LLM or generate, translate, or synthesize content itself.

## Local ports

| Service | Port |
| --- | ---: |
| `layer2_mock` | 8000 |
| `world_builder_service` | 8001 |
| `blueprint_assembler_service` | 8002 |
| `story_generator_service` | 8003 |
| `translator_service` | 8004 |
| `audio_generator_service` | 8005 |
| `orchestrator_service` | 8006 |

The downstream URLs default to these localhost ports. Set `LAYER2_BASE_URL`, `WORLD_BUILDER_URL`, `BLUEPRINT_URL`, `STORY_GEN_URL`, `TRANSLATOR_URL`, or `AUDIO_URL` to override them. `RUN_HISTORY_DIR` defaults to `./runs`; `DOWNSTREAM_TIMEOUT_SECONDS` defaults to 180 seconds.

## Run

```powershell
pip install -r orchestrator_service/requirements.txt
uvicorn orchestrator_service.main:app --port 8006
```

`GET /health` probes every dependent service live. Run the text-only pipeline without spending ElevenLabs quota:

```powershell
Invoke-RestMethod -Method Post http://localhost:8006/run-topic `
  -ContentType 'application/json' `
  -Body '{"topic_id":"3f7a1b2c-0001-4a10-9c11-000000000001","narrate":false}'
```

The completed report is returned and also saved in `runs/<topic_id>/<run_id>.json`.
