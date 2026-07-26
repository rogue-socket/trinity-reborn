# world_builder_service

Converts a Layer 2 topic context into a persisted fictional world bible (`POST /build-world`, `GET /health`).

## Run

Start Layer 2 first (see root [`README.md`](../../../README.md)), set `OPENAI_API_KEY` in `.env`, then from the repo root:

```sh
uv run uvicorn backend.layer3.world_builder_service.main:app --port 8001
```

```sh
curl -sX POST http://127.0.0.1:8001/build-world \
  -H 'content-type: application/json' \
  -d '{"topic_id":"<topic-uuid>"}'
```

Writes under `WORLD_BIBLE_DIR/<topic_id>/` (defaults to `<repo>/world_bible`). Later calls preserve the existing world and only generate missing entities/characters.
