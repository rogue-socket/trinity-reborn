# audio_generator_service

Generates ElevenLabs narration for existing episode text. It uses a persistent, OpenAI-inferred voice profile per character and no Gemini calls.

## Run

`ELEVENLABS_API_KEY`, `OPENAI_API_KEY`, `BLUEPRINT_DIR`, `EPISODE_DIR`, `AUDIO_DIR`, and `ELEVENLABS_FALLBACK_VOICE_ID` are loaded from `.env`.

```powershell
pip install -r audio_generator_service/requirements.txt
uvicorn audio_generator_service.main:app --port 8005
```

The process validates the ElevenLabs key before it becomes ready. The health endpoint performs the same live validation and returns current character usage:

```powershell
Invoke-RestMethod http://127.0.0.1:8005/health
```

Start with one language:

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8005/narrate `
  -ContentType "application/json" `
  -Body '{"topic_id":"3f7a1b2c-0001-4a10-9c11-000000000001","character_id":"<character-uuid>","languages":["en"]}'
```

The service caches the profile at `AUDIO_DIR/<topic_id>/<character_id>/voice_profile.json`; it uses that same selected voice for every language and episode for the character. Per-language audio is written immediately, while per-language failures are recorded in `audio_errors` without stopping the remainder.
