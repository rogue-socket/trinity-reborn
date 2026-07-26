# Trinity Reborn

Trinity Reborn turns a current-affairs research package into a fictional story
world, character-led English episodes, and translations. Layers 1 and 2 retain
evidence, provenance, and disagreements. Layer 3 uses that topic context to
create fictional output.

The standard local setup is a single Docker Compose command. It starts the
database, applies migrations, brings up the API and text-generation services,
and serves the dashboard. Audio is optional and disabled by default to avoid
ElevenLabs quota use.

## Services

| Component | Purpose | Local address |
|---|---|---:|
| Layer 1 | Discover, extract, deduplicate, and build research packages | hosted by Layer 2 on 8000 |
| Layer 2 API | Register topics, ingest packages, reconcile data, return topic context | http://localhost:8000 |
| World builder | Build world.json and characters.json | http://localhost:8001 |
| Blueprint assembler | Assemble the deterministic story blueprint | http://localhost:8002 |
| Story generator | Generate one English episode per character | http://localhost:8003 |
| Translator | Translate episodes with Gemini | http://localhost:8004 |
| Audio generator | Narrate episodes with ElevenLabs; optional profile | http://localhost:8005 |
| Orchestrator | Call Layer 3 services in order and save a run report | http://localhost:8006 |
| Dashboard | Browser UI | http://localhost:5173 |

## Prerequisites

- Docker Desktop, running
- An OpenAI API key for world and story generation
- A Gemini API key for translations

Python, uv, Node.js, and npm are only required for development commands and
local test runs; Docker Compose provides the normal demo runtime.

## Configure credentials

The repository's root .env is ignored by Git. If it does not exist yet, create
it from the example:

~~~powershell
Copy-Item .env.example .env
~~~

Set these values in .env:

~~~dotenv
OPENAI_API_KEY=...
GEMINI_API_KEY=...
~~~

These local defaults already match the Compose stack:

~~~dotenv
LAYER2_BASE_URL=http://localhost:8000
WORLD_BUILDER_URL=http://localhost:8001
BLUEPRINT_URL=http://localhost:8002
STORY_GEN_URL=http://localhost:8003
TRANSLATOR_URL=http://localhost:8004
AUDIO_URL=http://localhost:8005
DOWNSTREAM_TIMEOUT_SECONDS=180
~~~

| Optional variable | Default | Used by |
|---|---|---|
| OPENAI_BASE_URL | OpenAI default | World builder and story generator |
| GEMINI_MODEL | gemini-3.5-flash-lite | Translator |
| ELEVENLABS_API_KEY | none | Audio generator |
| ELEVENLABS_FALLBACK_VOICE_ID | none | Audio generator fallback voice |
| WORLD_BIBLE_DIR | ./world_bible | World builder and blueprint assembler |
| BLUEPRINT_DIR | ./blueprints | Blueprint assembler and later services |
| EPISODE_DIR | ./episodes | Story generator and later services |
| AUDIO_DIR | ./audio | Audio generator |
| RUN_HISTORY_DIR | ./runs | Orchestrator |

Artifact directories are mounted to the repository root, so outputs remain on
your machine even if the containers are recreated.

## Run the complete text demo

From the repository root:

~~~powershell
docker compose up --build
~~~

That one command:

1. starts PostgreSQL on port 5432;
2. runs Alembic migrations;
3. starts Layer 2 and all text-pipeline services;
4. starts the orchestrator; and
5. starts the dashboard on port 5173.

Open http://localhost:5173. Choose an available demo workflow in the dashboard
and click **Launch**. The dashboard creates a compact research package, ingests
it, and sends it through the World Bible, blueprint, story, and translation
stages. It keeps narration disabled.

The first run can take several minutes because OpenAI and Gemini are called for
eligible characters and target languages. Watch all container logs in the same
terminal. In another terminal, inspect only one service if needed:

~~~powershell
docker compose logs -f orchestrator
docker compose logs -f story_generator
~~~

Stop the stack with:

~~~powershell
docker compose down
~~~

The database data persists. Use the following only when you intentionally want
to remove the local database volume too:

~~~powershell
docker compose down -v
~~~

## Confirm service health

Once Compose reports the services running:

~~~powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8006/health
~~~

The orchestrator health response includes every downstream service. Audio will
report unreachable in the standard text-only stack; that is expected and does
not prevent a run.

## What the dashboard run does

1. The frontend registers a topic with POST /topics.
2. It submits a Layer 1-compatible package to POST /ingestions.
3. It calls POST /run-topic with narration disabled.
4. The orchestrator calls world builder, blueprint assembler, story generator,
   and translator. It continues with the next character if one fails.
5. It saves a run report and returns it to the dashboard.

The demonstration package is intentionally self-contained. For live research,
Layer 1 endpoints are available on port 8000: GET /discover, POST /extract,
POST /deduplicate, and POST /build-package.

## Output files

| Path | Contents |
|---|---|
| world_bible/<topic_id>/world.json | Fictional world name and source-entity map |
| world_bible/<topic_id>/characters.json | Generated character profiles |
| blueprints/<topic_id>/blueprint.json | Deterministic story blueprint |
| episodes/<topic_id>/<character_id>.json | English story and translations |
| runs/<topic_id>/<run_id>.json | Orchestrator run report |
| audio/<topic_id>/<character_id>/ | Voice profile and MP3s; narrated runs only |

## Optional narration

Add ELEVENLABS_API_KEY and OPENAI_API_KEY to .env, then include the audio
profile when starting Compose:

~~~powershell
docker compose --profile audio up --build
~~~

The audio generator validates the ElevenLabs key before it starts. Confirm it
before submitting a narrated run:

~~~powershell
Invoke-RestMethod http://localhost:8005/health
~~~

Run narration directly with a limited character and language set to conserve
quota:

~~~powershell
Invoke-RestMethod http://localhost:8006/run-topic -Method Post -ContentType 'application/json' -Body '{"topic_id":"<topic-uuid>","character_ids":["<character-uuid>"],"languages":["en","hi"],"narrate":true}'
~~~

## Architecture diagram and API docs

The dashboard's **Architecture** tab displays the flow and downloads the
[Excalidraw diagram](frontend/public/trinity-reborn-architecture.excalidraw).

- Layer 1 and Layer 2: http://localhost:8000/docs
- World builder: http://localhost:8001/docs
- Blueprint assembler: http://localhost:8002/docs
- Story generator: http://localhost:8003/docs
- Translator: http://localhost:8004/docs
- Audio generator: http://localhost:8005/docs
- Orchestrator: http://localhost:8006/docs

More implementation detail: [Layer 1 / Layer 2 integration](docs/layer1-layer2-integration.md),
[full architecture](docs/full-architecture.md), and [bug audit](docs/bug-audit.md).

## Development without Compose

For local source editing, use the existing commands:

~~~powershell
docker compose up -d db
uv sync --group dev
uv run alembic upgrade head
uv run uvicorn backend.main:app --reload --port 8000
npm run dev --prefix frontend
~~~

The complete service commands remain documented in each service directory under
backend/layer3/. In normal use, prefer the single Compose command above.

## Verify the repository

With PostgreSQL running and migrations applied:

~~~powershell
uv run alembic upgrade head
uv run alembic check
uv run ruff check backend
$env:PYTHONPATH = '.'; uv run mypy backend
$env:PYTHONPATH = '.'; uv run pytest backend -q
npm run lint --prefix frontend
npm run typecheck --prefix frontend
npm test --prefix frontend
npm run build --prefix frontend
~~~

The current suite contains 88 backend tests and 3 frontend tests.

## Troubleshooting

| Symptom | What to check |
|---|---|
| Dashboard is blank | Restart Compose, then hard-refresh the browser. |
| Dashboard reports Failed to fetch | Run docker compose ps and docker compose logs -f. Layer 2 and the orchestrator must be healthy. |
| Run board shows NEEDS ATTENTION | Read docker compose logs -f <service>. OpenAI and Gemini keys must be in .env before the stack starts. |
| Orchestrator reports audio unreachable | Expected unless you start with --profile audio. |
| Docker cannot bind port 5432 | Stop the unrelated process/container using port 5432, then start Compose again. |

Do not commit .env or generated data under world_bible/, blueprints/, episodes/,
audio/, or runs/.
