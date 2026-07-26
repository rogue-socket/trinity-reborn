# story_generator_service

Generates one short English episode from one character perspective in a completed blueprint.

## Run

```sh
uv run uvicorn backend.layer3.story_generator_service.main:app --port 8003
```

```sh
curl -sX POST http://127.0.0.1:8003/episodes \
  -H 'content-type: application/json' \
  -d '{"topic_id":"<topic-uuid>","character_id":"<character-uuid>","force":false}'
```

Requires `OPENAI_API_KEY`. Caches under `<repo>/episodes` by default.
