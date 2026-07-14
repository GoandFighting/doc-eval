"""Registry for managing multiple evaluation datasets."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from eval.core.config import EvalConfig
from eval.core.runner import AsyncEvalRunner

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-zA-Z0-9_\u4e00-\u9fff\-]+$")


@dataclass
class DatasetEntry:
    """A registered dataset with its own runner.

    :param id: Unique dataset identifier (sanitised name).
    :param name: Human-readable name.
    :param path: Filesystem path to the dataset directory.
    :param is_builtin: Whether this is a built-in dataset.
    :param runner: AsyncEvalRunner bound to this dataset.
    """

    id: str
    name: str
    path: Path
    is_builtin: bool
    runner: AsyncEvalRunner

    @property
    def available_pdfs(self) -> list[str]:
        """Return PDF file names that are both testable and downloadable.

        For built-in datasets, only PDFs in ``selected_text/`` and
        ``selected_table/`` are considered (layout-only PDFs are
        excluded because they can't be downloaded or evaluated from
        Markdown alone).

        For user datasets, all ``*.pdf`` files in the dataset directory
        are included.
        """
        testable = set(self.runner.available_pdfs)
        if self.is_builtin:
            downloadable: set[str] = set()
            for subdir in ("selected_text", "selected_table"):
                d = self.path / subdir
                if d.exists():
                    downloadable.update(p.name for p in d.glob("*.pdf"))
        else:
            downloadable = {p.name for p in self.path.rglob("*.pdf")}
        return sorted(testable & downloadable)

    def to_dict(self) -> dict:
        """Serialise to dict for API responses.

        ``pdf_count`` reflects the number of PDFs with test cases in
        the JSONL files (used in the dataset dropdown).
        """
        return {
            "id": self.id,
            "name": self.name,
            "is_builtin": self.is_builtin,
            "pdf_count": len(self.runner.available_pdfs),
        }


class DatasetRegistry:
    """Manages multiple datasets, each with its own AsyncEvalRunner.

    On startup, registers the built-in dataset and scans the user
    directory for previously uploaded datasets.

    :param builtin_dir: Path to the built-in dataset (e.g. newbench/).
    :param user_dir: Directory where user-uploaded datasets are stored.
    """

    def __init__(self, builtin_dir: Path, user_dir: Path) -> None:
        self._builtin_dir = builtin_dir
        self._user_dir = user_dir
        self._entries: dict[str, DatasetEntry] = {}
        self._user_dir.mkdir(parents=True, exist_ok=True)
        self._load_all()

    def _load_all(self) -> None:
        """Load built-in and user datasets on startup."""
        if self._builtin_dir.exists():
            try:
                entry = self._create_entry(
                    name="newbench",
                    path=self._builtin_dir,
                    is_builtin=True,
                )
                self._entries[entry.id] = entry
                logger.info("Loaded built-in dataset: %s", entry.name)
            except Exception:
                logger.exception("Failed to load built-in dataset: %s", self._builtin_dir)

        if self._user_dir.exists():
            for child in sorted(self._user_dir.iterdir()):
                if not child.is_dir():
                    continue
                try:
                    entry = self._create_entry(
                        name=child.name,
                        path=child,
                        is_builtin=False,
                    )
                    self._entries[entry.id] = entry
                    logger.info("Loaded user dataset: %s", entry.name)
                except Exception:
                    logger.exception("Failed to load user dataset: %s", child)

    def _create_entry(self, name: str, path: Path, is_builtin: bool) -> DatasetEntry:
        """Create a DatasetEntry with a fresh AsyncEvalRunner."""
        config = EvalConfig(dataset_dir=path)
        runner = AsyncEvalRunner(config)
        return DatasetEntry(
            id=self._name_to_id(name),
            name=name,
            path=path,
            is_builtin=is_builtin,
            runner=runner,
        )

    @staticmethod
    def _name_to_id(name: str) -> str:
        """Convert a dataset name to a safe identifier."""
        safe = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff\-]", "_", name)
        return safe or "dataset"

    def register(self, name: str, path: Path) -> DatasetEntry:
        """Register a new dataset.

        :param name: Human-readable dataset name.
        :param path: Path to the dataset directory (containing .jsonl files).
        :return: The created DatasetEntry.
        :raises ValueError: If name is invalid or already exists.
        """
        if not name or not _NAME_RE.match(name):
            raise ValueError(
                "Dataset name must contain only letters, digits, "
                "underscores, hyphens, or Chinese characters"
            )

        dataset_id = self._name_to_id(name)
        if dataset_id in self._entries:
            raise ValueError(f"Dataset '{name}' already exists")

        entry = self._create_entry(name=name, path=path, is_builtin=False)
        self._entries[dataset_id] = entry
        logger.info("Registered new dataset: %s (%s)", name, dataset_id)
        return entry

    def get(self, dataset_id: str) -> DatasetEntry | None:
        """Get a dataset entry by ID.

        :param dataset_id: Dataset identifier.
        :return: DatasetEntry or None if not found.
        """
        return self._entries.get(dataset_id)

    def list_all(self) -> list[DatasetEntry]:
        """Return all registered datasets."""
        return sorted(
            self._entries.values(),
            key=lambda e: (not e.is_builtin, e.name),
        )

    @property
    def user_dir(self) -> Path:
        """Return the user dataset directory."""
        return self._user_dir

    def refresh(self) -> dict[str, list[str]]:
        """Re-scan user directory for added or removed datasets.

        Does NOT touch the built-in dataset.

        :return: Dict with ``added`` and ``removed`` lists of dataset IDs.
        """
        added: list[str] = []
        removed: list[str] = []

        for entry_id, entry in list(self._entries.items()):
            if entry.is_builtin:
                continue
            if not entry.path.exists():
                del self._entries[entry_id]
                removed.append(entry_id)
                logger.info("Removed stale dataset: %s", entry_id)

        if self._user_dir.exists():
            for child in sorted(self._user_dir.iterdir()):
                if not child.is_dir():
                    continue
                child_id = self._name_to_id(child.name)
                if child_id in self._entries:
                    continue
                try:
                    entry = self._create_entry(
                        name=child.name,
                        path=child,
                        is_builtin=False,
                    )
                    self._entries[child_id] = entry
                    added.append(child_id)
                    logger.info("Loaded user dataset on refresh: %s", entry.name)
                except Exception:
                    logger.exception("Failed to load user dataset: %s", child)

        return {"added": added, "removed": removed}
