# audio_generator_service

ElevenLabs narration for existing episode text, with a persistent OpenAI-inferred voice profile per character.

## Run

```sh
uv run uvicorn audio_generator_service.main:app --port 8005
```

```sh
curl -sX POST http://127.0.0.1:8005/narrate \
  -H 'content-type: application/json' \
  -d '{"topic_id":"<topic-uuid>","character_id":"<character-uuid>","languages":["en"]}'
```

Requires `ELEVENLABS_API_KEY` and `OPENAI_API_KEY`. Optional `ELEVENLABS_FALLBACK_VOICE_ID`. Audio lands under `<repo>/audio` by default.
