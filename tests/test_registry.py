"""Tests for DatasetRegistry."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from eval.core.registry import DatasetRegistry


def _make_test_case(pdf_name: str = "test_doc.pdf") -> dict:
    """Create a minimal valid ParseBench test case."""
    return {
        "pdf": f"docs/text/{pdf_name}",
        "category": "text_content",
        "id": f"{Path(pdf_name).stem}_is_header_1",
        "type": "is_header",
        "rule": json.dumps({"text": "Test Header"}),
        "page": None,
        "expected_markdown": None,
        "tags": ["simple", "easy"],
    }


def _write_jsonl(path: Path, cases: list[dict]) -> None:
    """Write test cases to a JSONL file."""
    with open(path, "w", encoding="utf-8") as f:
        for tc in cases:
            f.write(json.dumps(tc, ensure_ascii=False) + "\n")


@pytest.fixture
def temp_dirs():
    """Create temp builtin and user dirs with a minimal dataset."""
    tmp = Path(tempfile.mkdtemp(prefix="registry_test_"))
    builtin_dir = tmp / "newbench"
    user_dir = tmp / "datasets"
    builtin_dir.mkdir()

    _write_jsonl(builtin_dir / "text_content.jsonl", [_make_test_case()])

    yield builtin_dir, user_dir

    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def registry(temp_dirs):
    builtin_dir, user_dir = temp_dirs
    return DatasetRegistry(builtin_dir=builtin_dir, user_dir=user_dir)


def _make_dataset_dir(base: Path, name: str, pdf_name: str = "custom.pdf") -> Path:
    """Create a dataset directory with a valid JSONL file."""
    ds_path = base / name
    ds_path.mkdir(parents=True)
    _write_jsonl(ds_path / "text_content.jsonl", [_make_test_case(pdf_name)])
    return ds_path


class TestDatasetRegistry:
    def test_builtin_loaded_on_init(self, registry):
        """Built-in dataset should be loaded automatically."""
        entry = registry.get("newbench")
        assert entry is not None
        assert entry.is_builtin is True
        assert entry.name == "newbench"

    def test_process_pool_is_enabled_only_for_builtin_dataset(self, temp_dirs):
        """Custom datasets retain the existing serial compatibility path."""
        builtin_dir, user_dir = temp_dirs
        registry = DatasetRegistry(
            builtin_dir=builtin_dir,
            user_dir=user_dir,
            builtin_process_workers=2,
        )
        custom_path = _make_dataset_dir(user_dir, "custom", "custom.pdf")
        custom = registry.register(name="custom", path=custom_path)

        assert registry.get("newbench").runner._config.process_workers == 2
        assert custom.runner._config.process_workers == 0

    def test_list_all_returns_builtin_first(self, registry):
        """list_all should return built-in datasets first."""
        all_ds = registry.list_all()
        assert len(all_ds) >= 1
        assert all_ds[0].is_builtin is True

    def test_register_new_dataset(self, registry, temp_dirs):
        """Register a new user dataset."""
        _, user_dir = temp_dirs
        ds_path = _make_dataset_dir(user_dir, "my_set", "custom.pdf")

        entry = registry.register(name="my_set", path=ds_path)
        assert entry.id == "my_set"
        assert entry.is_builtin is False
        assert "custom.pdf" in entry.runner.available_pdfs

    def test_manifest_jsonl_is_not_loaded_as_evaluation_data(self, registry, temp_dirs):
        """Dataset package metadata must not create an evaluation PDF entry."""
        _, user_dir = temp_dirs
        ds_path = _make_dataset_dir(user_dir, "with_manifest", "custom.pdf")
        _write_jsonl(
            ds_path / "manifest.jsonl",
            [
                {
                    "document_id": "metadata_only",
                    "department": "qa",
                    "pdf": "metadata_only.pdf",
                    "rules": 1,
                    "tables": 0,
                }
            ],
        )

        entry = registry.register(name="with_manifest", path=ds_path)

        assert "custom.pdf" in entry.runner.available_pdfs
        assert "metadata_only.pdf" not in entry.runner.available_pdfs

    def test_register_duplicate_name_raises(self, registry):
        """Registering a duplicate name should raise ValueError."""
        with pytest.raises(ValueError, match="already exists"):
            registry.register(name="newbench", path=Path("."))

    def test_register_invalid_name_raises(self, registry, temp_dirs):
        """Invalid dataset names should be rejected."""
        _, user_dir = temp_dirs
        ds_path = _make_dataset_dir(user_dir, "test_invalid", "x.pdf")

        with pytest.raises(ValueError, match="must contain only"):
            registry.register(name="bad/name!", path=ds_path)

    def test_register_dataset_without_usable_cases_raises(self, registry, temp_dirs):
        """Directories without usable evaluation cases must not be registered."""
        _, user_dir = temp_dirs
        empty_dataset = user_dir / "empty_dataset"
        empty_dataset.mkdir()

        with pytest.raises(ValueError, match="contains no usable evaluation cases"):
            registry.register(name="empty_dataset", path=empty_dataset)

    def test_get_nonexistent_returns_none(self, registry):
        """Getting an unknown ID should return None."""
        assert registry.get("nonexistent") is None

    def test_to_dict(self, registry):
        """to_dict should include id, name, is_builtin, pdf_count."""
        entry = registry.get("newbench")
        d = entry.to_dict()
        assert d["id"] == "newbench"
        assert d["name"] == "newbench"
        assert d["is_builtin"] is True
        assert isinstance(d["pdf_count"], int)

    def test_user_dir_property(self, registry, temp_dirs):
        """user_dir property should return the user directory path."""
        _, user_dir = temp_dirs
        assert registry.user_dir == user_dir

    def test_user_dataset_persisted_on_reload(self, temp_dirs):
        """User datasets should be reloaded when registry is recreated."""
        builtin_dir, user_dir = temp_dirs

        # First instance: register a user dataset
        r1 = DatasetRegistry(builtin_dir=builtin_dir, user_dir=user_dir)
        ds_path = _make_dataset_dir(user_dir, "persist_test", "persist.pdf")
        r1.register(name="persist_test", path=ds_path)

        # Second instance: should auto-load the user dataset
        r2 = DatasetRegistry(builtin_dir=builtin_dir, user_dir=user_dir)
        entry = r2.get("persist_test")
        assert entry is not None
        assert entry.is_builtin is False
        assert "persist.pdf" in entry.runner.available_pdfs

    def test_startup_ignores_hidden_staging_directory(self, temp_dirs):
        """A hidden staging directory must never become a dataset."""
        builtin_dir, user_dir = temp_dirs
        _make_dataset_dir(user_dir, ".staging", "staged.pdf")

        loaded = DatasetRegistry(builtin_dir=builtin_dir, user_dir=user_dir)

        assert all(entry.name != ".staging" for entry in loaded.list_all())

    def test_startup_ignores_empty_and_manifest_only_directories(self, temp_dirs):
        """Metadata and empty directories are not valid datasets."""
        builtin_dir, user_dir = temp_dirs
        (user_dir / "empty").mkdir(parents=True)
        manifest_only = user_dir / "manifest_only"
        manifest_only.mkdir()
        _write_jsonl(manifest_only / "manifest.jsonl", [{"pdf": "metadata.pdf"}])

        loaded = DatasetRegistry(builtin_dir=builtin_dir, user_dir=user_dir)

        names = {entry.name for entry in loaded.list_all()}
        assert "empty" not in names
        assert "manifest_only" not in names

    def test_refresh_ignores_staging_and_loads_published_dataset(self, registry, temp_dirs):
        """Refresh should expose only the completed published dataset."""
        _, user_dir = temp_dirs
        _make_dataset_dir(user_dir, ".staging", "staged.pdf")
        _make_dataset_dir(user_dir, "published", "published.pdf")

        changes = registry.refresh()

        assert changes["added"] == ["published"]
        assert registry.get("published") is not None
        assert all(entry.name != ".staging" for entry in registry.list_all())

    def test_refresh_removes_dataset_that_becomes_invalid(self, registry, temp_dirs):
        """Refresh should unregister a dataset whose rule files disappear."""
        _, user_dir = temp_dirs
        dataset_path = _make_dataset_dir(user_dir, "transient", "transient.pdf")
        registry.refresh()
        (dataset_path / "text_content.jsonl").unlink()

        changes = registry.refresh()

        assert changes["removed"] == ["transient"]
        assert registry.get("transient") is None

    def test_delete_user_dataset_removes_registry_entry_and_directory(self, registry, temp_dirs):
        """Deleting a user dataset should remove both state and files."""
        _, user_dir = temp_dirs
        ds_path = _make_dataset_dir(user_dir, "delete_me", "delete.pdf")
        registry.register(name="delete_me", path=ds_path)

        removed = registry.delete_user_dataset("delete_me")

        assert removed.name == "delete_me"
        assert registry.get("delete_me") is None
        assert not ds_path.exists()

    def test_delete_builtin_dataset_is_rejected(self, registry, temp_dirs):
        """The built-in benchmark must remain immutable."""
        builtin_dir, _ = temp_dirs

        with pytest.raises(ValueError, match="Built-in datasets cannot be deleted"):
            registry.delete_user_dataset("newbench")

        assert registry.get("newbench") is not None
        assert builtin_dir.exists()

    def test_delete_unknown_dataset_raises_key_error(self, registry):
        """Deleting an unknown dataset should report a missing identifier."""
        with pytest.raises(KeyError):
            registry.delete_user_dataset("missing")
