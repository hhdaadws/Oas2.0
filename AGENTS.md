# Repository Guidelines

## Project Structure & Module Organization
- Backend (FastAPI): `src/app/`
  - Core config/logging: `src/app/core/`
  - Database: `src/app/db/`
  - Domain modules: `src/app/modules/` (e.g., `executor`, `tasks`, `web` with `routers/`)
  - Entrypoint: `src/app/main.py`
- Frontend (Vite + Vue 3): `frontend/` (`src/`, `vite.config.js`)
- Configuration: `.env.example` → copy to `.env` (see `src/app/core/config.py`)
- Tooling & script tests: `.claude/scripts/`

## Build, Test, and Development Commands
- Backend setup: `pip install -r requirements.txt`
- Run API (dev): `uvicorn app.main:app --reload --app-dir src --host 0.0.0.0 --port 9001`
- Frontend dev: `cd frontend && npm install && npm run dev`
- Frontend build: `cd frontend && npm run build`
- Lint/format (backend): `flake8 src` and `black src`
- Tests (backend): `pytest -q` or with coverage `pytest --cov=src/app -q`

## Coding Style & Naming Conventions
- Python: 4-space indent, type hints where practical, prefer pure functions.
- Formatting: Black; keep imports sorted and unused code removed; fix lint with Flake8 before PR.
- Naming: packages/modules `snake_case` (e.g., `tasks/simple_scheduler.py`), classes `PascalCase`, functions/vars `snake_case`, constants `UPPER_CASE`.
- Paths: new modules under `src/app/modules/<feature>/` with `__init__.py`.

## Testing Guidelines
- Frameworks: `pytest`, `pytest-asyncio`, `pytest-cov`.
- Layout: place tests in `tests/` mirroring package paths (e.g., `tests/modules/tasks/test_scheduler.py`).
- Naming: files `test_*.py`; async tests use `pytest.mark.asyncio`.
- Coverage: target ≥ 80% for changed lines; include edge cases and error paths.

## Commit & Pull Request Guidelines
- Commits: use Conventional Commits (e.g., `feat(executor): add task queue`, `fix(web): null check router`).
- Scope small and focused; run lint/tests before committing.
- PRs: include description, rationale, screenshots for UI, and linked issues; list breaking changes and migration steps.

## Security & Configuration Tips
- Copy `.env.example` to `.env`; never commit secrets.
- Key settings: `API_HOST`/`API_PORT`, `DATABASE_URL`, emulator/ADB paths; prefer defaults for local dev.
- Do not hardcode credentials; read via `Settings` in `app/core/config.py`.
