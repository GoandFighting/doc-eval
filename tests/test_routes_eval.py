"""Tests for evaluation route submission classification."""

from server.routes_eval import _is_full_newbench_submission


def _pdf_names(count: int = 175) -> set[str]:
    return {f"document_{index:03d}.pdf" for index in range(count)}


def test_full_newbench_submission_is_enabled_for_report_leaderboard():
    available = _pdf_names()

    assert _is_full_newbench_submission(
        dataset_id="newbench",
        submitted_total=175,
        submitted_names=[name.replace(".pdf", ".md") for name in sorted(available)],
        available_pdfs=available,
        matched_pdfs=sorted(available),
    )


def test_report_leaderboard_rejects_partial_or_custom_dataset_submission():
    available = _pdf_names()

    markdown_names = [name.replace(".pdf", ".md") for name in sorted(available)]
    assert not _is_full_newbench_submission("newbench", 174, markdown_names[:-1], available, sorted(available)[:-1])
    assert not _is_full_newbench_submission("custom", 175, markdown_names, available, sorted(available))


def test_report_leaderboard_rejects_duplicate_in_place_of_missing_file():
    available = _pdf_names()
    matched = sorted(available)
    matched[-1] = matched[0]

    submitted_names = [name.replace(".pdf", ".md") for name in sorted(available)]
    assert not _is_full_newbench_submission("newbench", 175, submitted_names, available, matched)


def test_report_leaderboard_requires_markdown_files():
    available = _pdf_names()
    submitted_names = [name.replace(".pdf", ".md") for name in sorted(available)]
    submitted_names[-1] = submitted_names[-1].replace(".md", ".txt")

    assert not _is_full_newbench_submission("newbench", 175, submitted_names, available, sorted(available))
