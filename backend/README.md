# AI Research Engine Backend

This repository section contains the Step 1 backend scaffold. Business logic and
pipeline processing are intentionally not implemented.

## Setup

From this directory:

```powershell
uv sync
uv run uvicorn app.main:app --reload
```

## Endpoint

- `GET /health` returns the service health status.

## Quality checks

```powershell
uv run ruff check .
uv run pytest
```
