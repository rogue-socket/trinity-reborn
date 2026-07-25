# Trinity Reborn

Backend scaffold for Step 1 of the AI Research Engine pipeline.

## Requirements

- Python 3.12
- [uv](https://docs.astral.sh/uv/)

## Run locally

```powershell
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

The health check is available at `GET /health`.
