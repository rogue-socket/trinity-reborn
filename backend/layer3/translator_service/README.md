# translator_service

Gemini-powered per-language translation of completed English episodes.

## Run

```sh
uv run uvicorn backend.layer3.translator_service.main:app --port 8004
```

```sh
curl -sX POST http://127.0.0.1:8004/translate \
  -H 'content-type: application/json' \
  -d '{"topic_id":"<topic-uuid>","character_id":"<character-uuid>","target_languages":["hi","ta"],"force":false}'
```

Requires `GEMINI_API_KEY`. Reads blueprints/episodes from the repo-rooted artefact dirs.
