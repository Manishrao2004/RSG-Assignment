import logging
import time
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from starlette.concurrency import run_in_threadpool

from app.config import ROOT, Settings
from app.database import initialize, quality
from app.main_agent.graph import AgentError, MainAgent
from app.main_agent.schemas import ChatRequest

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, model=None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application):
        await run_in_threadpool(initialize, settings.db_path, settings.csv_path)
        checkpoint_path = settings.db_path.with_name("conversations.sqlite3")
        async with AsyncSqliteSaver.from_conn_string(str(checkpoint_path)) as saver:
            application.state.agent = MainAgent(settings, saver, model=model)
            try:
                yield
            finally:
                await run_in_threadpool(application.state.agent.tracing.close)

    api = FastAPI(title="Sales BI Assistant", version="0.1.0", lifespan=lifespan)

    @api.exception_handler(AgentError)
    async def interpretation_error(request: Request, exc: AgentError):
        return JSONResponse(status_code=exc.status, content={"detail": str(exc)})

    @api.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.exception("Unexpected API error")
        return JSONResponse(
            status_code=500,
            content={
                "detail": "An unexpected server error occurred. Please try again or check the server logs."
            },
        )

    @api.get("/api/health")
    def health():
        return {
            "status": "ok",
            "mode": "groq" if settings.groq_api_key else "unconfigured",
            "model": settings.groq_model,
            "tracing_enabled": bool(settings.langsmith_tracing and settings.langsmith_api_key),
            "tracing_project": settings.langsmith_project,
        }

    @api.get("/api/dataset")
    def dataset():
        return quality(settings.db_path)

    @api.post("/api/chat")
    @api.post("/api/ask")
    async def ask(body: ChatRequest):
        started = time.perf_counter()
        result = await api.state.agent.run_turn(
            body.question, str(body.thread_id) if body.thread_id else None
        )
        return {
            **result,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }

    @api.get("/api/conversations/{thread_id}")
    async def history(thread_id: UUID):
        return {"thread_id": str(thread_id), "messages": await api.state.agent.history(str(thread_id))}

    dist = ROOT.parent / "rsg-frontend" / "dist"
    if (dist / "assets").exists():
        api.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @api.get("/", include_in_schema=False)
    def index():
        if (dist / "index.html").exists():
            return FileResponse(dist / "index.html")
        return JSONResponse(
            {
                "message": "Build the frontend with npm run build in rsg-frontend/, or use Vite at http://localhost:5173.",
                "api_docs": "/docs",
            }
        )

    return api


app = create_app()
