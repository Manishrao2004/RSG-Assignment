# RSG backend

This directory is the Python project root. Run `uv sync --locked` here; uv creates `.venv/` here. Copy `.env.example` to `.env`, add `GROQ_API_KEY`, and run:

```powershell
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Run checks with `uv run pytest -q` and `uv run ruff check .`. The CSV at `data/sales.csv` is imported automatically. The LangGraph main agent runs the Groq/SQL tool loop and stores conversation checkpoints in a separate SQLite file. Generated databases, environments, caches, and `.env` are ignored by this directory's `.gitignore`. Groq is required; no rule-based fallback is used.

The backend API runs independently of the frontend. See the [workspace README](../README.md) for architecture, data policy, API details, and the frontend setup.
