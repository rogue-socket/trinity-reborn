# translator_service

Gemini-powered, per-language translation of completed English episodes. It does not generate audio or call OpenAI or ElevenLabs.

## Run

The service loads `GEMINI_API_KEY`, optional `GEMINI_MODEL`, `BLUEPRINT_DIR`, and `EPISODE_DIR` from `.env`. The configured model is checked against the API's visible models and must be Flash-tier, never Pro.

```powershell
pip install -r translator_service/requirements.txt
uvicorn translator_service.main:app --port 8004
```

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8004/translate `
  -ContentType "application/json" `
  -Body '{"topic_id":"3f7a1b2c-0001-4a10-9c11-000000000001","character_id":"<character-uuid>","target_languages":["hi","ta","bn","pa","gu"],"force":false}'
```

If `target_languages` is omitted, the service uses the episode's target languages except English. Existing per-language translations are returned from cache unless `force` is true. Every language result is written to disk immediately; failures are recorded in `translation_errors` and do not stop the other languages.
