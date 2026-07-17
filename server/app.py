"""FastAPI application for document conversion evaluation."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from eval.core.config import server_process_workers
from server.registry_holder import get_registry, init_registry
from server.routes_dataset import router as dataset_router
from server.routes_eval import router as eval_router
from server.routes_leaderboard import router as leaderboard_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Warm persistent evaluation workers and close them on shutdown."""
    registry = get_registry()
    builtin = registry.get("newbench")
    if builtin is not None:
        await builtin.runner.start()
    try:
        yield
    finally:
        for entry in registry.list_all():
            await entry.runner.close()


app = FastAPI(
    title="Document Conversion Evaluation",
    description="Evaluate document-to-Markdown conversion quality",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialise dataset registry at startup
_builtin_dir = Path("newbench")
_user_dir = Path("datasets")
init_registry(
    builtin_dir=_builtin_dir,
    user_dir=_user_dir,
    builtin_process_workers=server_process_workers(),
)

app.include_router(dataset_router, prefix="/api/evaluation/datasets", tags=["dataset"])
app.include_router(eval_router, prefix="/api/evaluation/eval", tags=["eval"])
app.include_router(leaderboard_router, prefix="/api/evaluation/leaderboard", tags=["leaderboard"])

static_dir = Path(__file__).parent / "static"
app.mount("/evaluation", StaticFiles(directory=str(static_dir), html=True), name="static")
