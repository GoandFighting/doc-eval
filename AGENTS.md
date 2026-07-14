# Repository Guidelines

## Project Structure & Module Organization

The Python package lives in `eval/`. Core request models, configuration, dataset registration, and orchestration are under `eval/core/`; ParseBench integration is in `eval/adapters/`; optional scoring layers are in `eval/layers/`; shared score helpers are in `eval/metrics/`. `server/` contains the FastAPI application and routes, with the single-page UI in `server/static/`. Tests mirror behavior in `tests/test_*.py`. `newbench/` holds the bundled JSONL rules and reference PDFs; treat `datasets/` as ignored runtime/user-uploaded data. `example_eval.py` is the command-line example. Do not modify the ignored `ParseBench-main/` checkout as application source.

## Build, Test, and Development Commands

- `python -m pip install -e ".[server,dev]"` installs the package, web dependencies, pytest, and Ruff in editable mode.
- `python -m uvicorn server.app:app --reload --port 8000` starts the local web UI at `http://localhost:8000`.
- `python example_eval.py output.md source.pdf` evaluates one converted Markdown file; running it without arguments launches the demo.
- `python -m pytest` runs the configured test suite with verbose output and short tracebacks.
- `python -m ruff check .` checks imports, correctness, modernization, and style rules. Use `python -m ruff check . --fix` only after reviewing the proposed scope.

## Coding Style & Naming Conventions

Target Python 3.12 and keep lines within Ruff's 120-character limit. Use four-space indentation, type annotations for public interfaces, and concise docstrings for modules, classes, and non-obvious methods. Follow `snake_case` for functions, variables, and modules; `PascalCase` for classes; and `UPPER_SNAKE_CASE` for constants. Keep imports sorted and avoid eager imports of optional, heavyweight dependencies (follow the lazy-loading pattern in `eval/core/runner.py`).

## Testing Guidelines

Pytest discovers `test_*.py`, `Test*` classes, and `test_*` functions under `tests/`. Add focused unit tests beside the closest existing test module and use fixtures for reusable setup. Cover success, empty/error input, and serialization or API boundaries when changing evaluation behavior. Run `python -m pytest tests/test_runner.py` for a focused check, then the full suite before submitting.

## Commit & Pull Request Guidelines

History uses short, focused subjects in English or Chinese without a required prefix. Prefer an imperative summary such as `Add dataset validation` and keep unrelated changes separate. Pull requests should explain the problem and solution, list verification commands, link relevant issues, and call out dataset or dependency changes. Include screenshots for updates to `server/static/index.html` and note any optional extras needed to reproduce results.
