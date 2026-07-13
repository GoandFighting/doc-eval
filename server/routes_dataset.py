"""Dataset-related API routes: list, upload, info, download."""

from __future__ import annotations

import io
import json
import logging
import shutil
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Form, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from server.registry_holder import get_registry

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def list_datasets() -> dict[str, Any]:
    """List all available datasets."""
    registry = get_registry()
    datasets = [e.to_dict() for e in registry.list_all()]
    return {"datasets": datasets}


@router.post("/upload")
async def upload_dataset(
    name: str = Form(...),
    file: UploadFile = Form(...),  # noqa: B008
) -> dict[str, Any]:
    """Upload a custom dataset as a zip file.

    Supports two ParseBench formats:
    1. JSONL: zip contains .jsonl files
    2. Sidecar: zip contains .test.json files alongside PDFs

    PDF files are optional (needed for download but not for evaluation).

    :param name: Dataset name (letters, digits, underscores, hyphens, Chinese).
    :param file: Zip file containing JSONL or sidecar test files.
    :return: Dataset info on success, error on failure.
    """
    registry = get_registry()

    # Read and validate zip
    content = await file.read()
    try:
        buf = io.BytesIO(content)
        with zipfile.ZipFile(buf, "r") as zf:
            names = zf.namelist()
            has_jsonl = any(n.endswith(".jsonl") for n in names)
            has_test_json = any(n.endswith(".test.json") for n in names)
            if not has_jsonl and not has_test_json:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Zip must contain at least one .jsonl or .test.json file"},
                )
    except zipfile.BadZipFile:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid zip file"},
        )

    # Create dataset directory
    dataset_id = registry._name_to_id(name)
    dataset_dir = registry.user_dir / dataset_id
    if dataset_dir.exists():
        return JSONResponse(
            status_code=400,
            content={"error": f"Dataset '{name}' already exists"},
        )

    dataset_dir.mkdir(parents=True)

    # Extract zip
    buf.seek(0)
    with zipfile.ZipFile(buf, "r") as zf:
        zf.extractall(str(dataset_dir))

    # Find the actual root containing test files (.jsonl or .test.json)
    ds_root = dataset_dir
    root_has_jsonl = list(dataset_dir.glob("*.jsonl"))
    root_has_test_json = list(dataset_dir.rglob("*.test.json"))
    if not root_has_jsonl and not root_has_test_json:
        for child in dataset_dir.iterdir():
            if child.is_dir() and (
                list(child.glob("*.jsonl")) or list(child.rglob("*.test.json"))
            ):
                ds_root = child
                break

    if not list(ds_root.glob("*.jsonl")) and not list(ds_root.rglob("*.test.json")):
        shutil.rmtree(dataset_dir, ignore_errors=True)
        return JSONResponse(
            status_code=400,
            content={"error": "No .jsonl or .test.json files found in zip"},
        )

    # Validate JSONL files are parseable
    for jf in ds_root.glob("*.jsonl"):
        try:
            with open(jf, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            shutil.rmtree(dataset_dir, ignore_errors=True)
            return JSONResponse(
                status_code=400,
                content={"error": f"Invalid JSON in {jf.name}: {e}"},
            )

    # Validate .test.json files are parseable
    for tj in ds_root.rglob("*.test.json"):
        try:
            with open(tj, encoding="utf-8") as f:
                json.load(f)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            shutil.rmtree(dataset_dir, ignore_errors=True)
            return JSONResponse(
                status_code=400,
                content={"error": f"Invalid JSON in {tj.name}: {e}"},
            )

    # Register dataset
    try:
        entry = registry.register(name=name, path=ds_root)
    except ValueError as e:
        shutil.rmtree(dataset_dir, ignore_errors=True)
        return JSONResponse(status_code=400, content={"error": str(e)})

    return entry.to_dict()


@router.get("/{dataset_id}/info")
async def dataset_info(dataset_id: str) -> dict[str, Any]:
    """Return available PDF list for a specific dataset."""
    registry = get_registry()
    entry = registry.get(dataset_id)
    if entry is None:
        return JSONResponse(status_code=404, content={"error": "Dataset not found"})

    pdfs = sorted(entry.runner.available_pdfs)
    return {
        "id": entry.id,
        "name": entry.name,
        "is_builtin": entry.is_builtin,
        "total": len(pdfs),
        "pdfs": pdfs,
    }


@router.get("/{dataset_id}/download")
async def dataset_download(dataset_id: str) -> Any:
    """Download all PDFs from a dataset as a zip file.

    For built-in datasets, zips the selected_text/ and selected_table/ dirs.
    For user datasets, zips any .pdf files found in the dataset directory.
    """
    registry = get_registry()
    entry = registry.get(dataset_id)
    if entry is None:
        return JSONResponse(status_code=404, content={"error": "Dataset not found"})

    # Collect PDF files
    pdf_files: list[Path] = []
    if entry.is_builtin:
        for subdir in ["selected_text", "selected_table"]:
            d = entry.path / subdir
            if d.exists():
                pdf_files.extend(sorted(d.glob("*.pdf")))
    else:
        for p in entry.path.rglob("*.pdf"):
            pdf_files.append(p)

    if not pdf_files:
        return JSONResponse(
            status_code=404,
            content={"error": "No PDF files available in this dataset"},
        )

    # Stream zip
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for pdf in pdf_files:
            arcname = pdf.name
            zf.write(str(pdf), arcname)

    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={dataset_id}.zip"},
    )
