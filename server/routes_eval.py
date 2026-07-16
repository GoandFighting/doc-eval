"""Evaluation API routes: batch evaluation from uploaded Markdown files."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, UploadFile
from fastapi.responses import JSONResponse

from eval.core.models import BatchEvalRequest, EvalRequest
from eval.report import batch_to_dict
from server.registry_holder import get_registry

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/batch")
async def eval_batch(
    files: list[UploadFile] | None = None,
    dataset_id: str = "newbench",
) -> dict[str, Any]:
    """Evaluate multiple uploaded Markdown files against a specific dataset.

    Each uploaded .md file is matched to a PDF by stripping the .md
    extension and appending .pdf.  Files that don't match any known
    PDF are returned in the errors list.

    :param files: List of uploaded Markdown files.
    :param dataset_id: Dataset identifier to use for evaluation.
    :return: Batch evaluation result as dict.
    """
    if files is None:
        files = []

    registry = get_registry()
    entry = registry.get(dataset_id)
    if entry is None:
        return JSONResponse(
            status_code=404,
            content={"error": f"Dataset '{dataset_id}' not found"},
        )

    runner = entry.runner
    available_pdfs = set(entry.available_pdfs)
    pdf_lookup: dict[str, str] = {}
    for pdf_name in available_pdfs:
        stem = Path(pdf_name).stem
        pdf_lookup[stem] = pdf_name

    items: list[EvalRequest] = []
    skipped: list[dict[str, str]] = []

    for f in files:
        md_name = f.filename or ""
        stem = Path(md_name).stem
        pdf_name = pdf_lookup.get(stem)
        if pdf_name is None:
            skipped.append({
                "pdf_name": md_name,
                "error": f"No matching PDF found for '{md_name}'",
            })
            continue

        content = f.file.read().decode("utf-8")
        content = content.replace("\r\n", "\n").replace("\r", "\n")
        items.append(EvalRequest(converted_md=content, pdf_name=pdf_name))

    if not items:
        return {
            "total": len(files),
            "evaluated": 0,
            "failed": len(skipped),
            "results": [],
            "errors": skipped,
            "warnings": [],
            "summary": {},
        }

    response = await runner.evaluate_batch(BatchEvalRequest(items=items))
    result = batch_to_dict(response)
    for s in skipped:
        result["errors"].append(s)
    result["failed"] = response.failed + len(skipped)
    return result
