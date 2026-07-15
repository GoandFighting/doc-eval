"""Dataset-related API routes: list, upload, info, download."""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter
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


@router.post("/refresh")
async def refresh_datasets() -> dict[str, Any]:
    """Re-scan user dataset directory for added or removed datasets.

    :return: Updated dataset list plus added/removed IDs.
    """
    registry = get_registry()
    changes = registry.refresh()
    datasets = [e.to_dict() for e in registry.list_all()]
    return {
        "added": changes["added"],
        "removed": changes["removed"],
        "datasets": datasets,
    }


@router.delete("/{dataset_id}")
async def delete_dataset(dataset_id: str) -> dict[str, Any]:
    """Delete a user-created dataset.

    Built-in datasets are immutable and cannot be removed through the API.
    """
    registry = get_registry()
    try:
        entry = registry.delete_user_dataset(dataset_id)
    except KeyError:
        return JSONResponse(status_code=404, content={"error": "Dataset not found"})
    except ValueError as exc:
        return JSONResponse(status_code=403, content={"error": str(exc)})

    return {
        "deleted": True,
        "id": entry.id,
        "name": entry.name,
    }


@router.get("/{dataset_id}/info")
async def dataset_info(dataset_id: str) -> dict[str, Any]:
    """Return available PDF list for a specific dataset."""
    registry = get_registry()
    entry = registry.get(dataset_id)
    if entry is None:
        return JSONResponse(status_code=404, content={"error": "Dataset not found"})

    pdfs = entry.available_pdfs
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
