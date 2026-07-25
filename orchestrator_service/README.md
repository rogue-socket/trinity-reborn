# orchestrator_service

Coordinates the Layer 3 chain over HTTP. Does not call an LLM itself.

## Ports

| Service | Port |
|---------|-----:|
| Layer 2 API | 8000 |
| world_builder | 8001 |
| blueprint_assembler | 8002 |
| story_generator | 8003 |
| translator | 8004 |
| audio_generator | 8005 |
| orchestrator | 8006 |

## Run

```sh
uv run uvicorn orchestrator_service.main:app --port 8006
```

```sh
# Text-only
curl -sX POST http://localhost:8006/run-topic \
  -H 'content-type: application/json' \
  -d '{"topic_id":"<topic-uuid>","narrate":false}'

# With DEMO_MODE=true in .env, omitting narrate turns narration on
curl -sX POST http://localhost:8006/run-topic \
  -H 'content-type: application/json' \
  -d '{"topic_id":"<topic-uuid>"}'
```

Reports are saved under `<repo>/runs/<topic_id>/`. `DOWNSTREAM_TIMEOUT_SECONDS` defaults to 180.
