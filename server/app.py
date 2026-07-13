"""FastAPI application for document conversion evaluation."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from server.registry_holder import init_registry
from server.routes_dataset import router as dataset_router
from server.routes_eval import router as eval_router

app = FastAPI(
    title="Document Conversion Evaluation",
    description="Evaluate document-to-Markdown conversion quality",
    version="0.2.0",
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
init_registry(builtin_dir=_builtin_dir, user_dir=_user_dir)

app.include_router(dataset_router, prefix="/api/evaluation/datasets", tags=["dataset"])
app.include_router(eval_router, prefix="/api/evaluation/eval", tags=["eval"])

static_dir = Path(__file__).parent / "static"
app.mount("/evaluation", StaticFiles(directory=str(static_dir), html=True), name="static")
