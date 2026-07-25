# story_generator_service

Generates one short English episode from one character perspective in a completed Story Blueprint. It implements no translation, audio, or provider integrations other than OpenAI.

## Run

Ensure `BLUEPRINT_DIR/<topic_id>/blueprint.json` has been built, then run from the repository root:

```powershell
pip install -r story_generator_service/requirements.txt
uvicorn story_generator_service.main:app --port 8003
```

`OPENAI_API_KEY`, `BLUEPRINT_DIR`, and `EPISODE_DIR` are loaded from `.env`; directory defaults are `./blueprints` and `./episodes`.

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8003/episodes `
  -ContentType "application/json" `
  -Body '{"topic_id":"3f7a1b2c-0001-4a10-9c11-000000000001","character_id":"<character-uuid>","force":false}'
```

The OpenAI call uses a Structured Outputs response with `title` and `story_text`; this is the documented title-extraction approach. Successful episodes are cached at `EPISODE_DIR/<topic_id>/<character_id>.json`. Requests without `force` return a cached `story_generated` episode without calling OpenAI.
