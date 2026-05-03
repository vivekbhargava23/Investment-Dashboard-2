# TICKET-000 — Repo scaffolding + CI setup

**Status:** IN_REVIEW
**Priority:** P0
**Estimated session length:** 30–45 min
**Drafted by:** Vivek + Claude (chat 2026-05-03)
**Implemented by:** Claude Code (session 2026-05-03)

## Problem

The empty repo has `docs/`, `CLAUDE.md`, and the PR template already committed by Vivek. We now need:
- Python package structure under `app/`
- `pyproject.toml` with all dependencies
- Test scaffold under `tests/`
- GitHub Actions CI running pytest + ruff + mypy + lint-imports on every push
- Conda environment file for reproducibility
- A working `streamlit run app/ui/main.py` showing a placeholder page
- Architecture rule enforcement via `import-linter`
- **Secrets management infrastructure** (`.env` + `.env.example` + `pydantic-settings`-based config)

This ticket creates the skeleton. **No domain logic yet. No adapter implementations yet.**

This ticket also exercises the full Claude Code workflow end-to-end for the first time:
session-start ritual → implementation → session-end ritual → PR opened.

## Acceptance criteria

### Package structure
- [ ] `app/` package with `__init__.py` files in `app/`, `app/domain/`, `app/services/`, `app/ports/`, `app/adapters/`, `app/ui/`
- [ ] `tests/__init__.py` and `tests/unit/__init__.py`

### Configuration files
- [ ] `pyproject.toml` with:
  - Runtime deps: `streamlit`, `pydantic>=2`, `pydantic-settings`, `yfinance`, `requests`, `plotly`, `pandas`, `python-dotenv`
  - Dev deps: `pytest`, `pytest-cov`, `hypothesis`, `ruff`, `mypy`, `import-linter`
  - `[tool.ruff]` with line-length 100, target-version py311
  - `[tool.mypy]` with `strict = true` for `app/domain/*` (others can be lenient initially)
  - `[tool.pytest.ini_options]` with `testpaths = ["tests"]`
- [ ] `environment.yml` for conda — env name `investment-dashboard`, Python 3.11
- [ ] `.gitignore` — Python standard + `.env` + `data/portfolio.json` + `.streamlit/secrets.toml` + `__pycache__` + `.pytest_cache` + `.mypy_cache` + `.ruff_cache`
- [ ] `.importlinter` config enforcing the dependency rule:
  - `app.domain` cannot import from `app.services`, `app.adapters`, `app.ui`, `app.ports`
  - `app.services` cannot import from `app.adapters`, `app.ui`
  - `app.ui` cannot import from `app.adapters` or `app.domain` directly (only via services)

### Secrets management
- [ ] `.env.example` committed to repo with these placeholder lines (no real values):
  ```
  # Price feeds
  FINNHUB_API_KEY=your_finnhub_key_here
  ALPHA_VANTAGE_API_KEY=your_alpha_vantage_key_here_optional

  # FX feeds (ECB is free, no key needed)

  # App config
  APP_ENV=local
  PORTFOLIO_JSON_PATH=data/portfolio.json
  ```
- [ ] `.env` is in `.gitignore` (verified by attempting `git check-ignore .env`)
- [ ] `app/config.py` defines a `Settings` class using `pydantic-settings`:
  ```python
  from pydantic_settings import BaseSettings, SettingsConfigDict

  class Settings(BaseSettings):
      model_config = SettingsConfigDict(env_file=".env", extra="ignore")

      finnhub_api_key: str | None = None
      alpha_vantage_api_key: str | None = None
      app_env: str = "local"
      portfolio_json_path: str = "data/portfolio.json"

  def get_settings() -> Settings:
      return Settings()
  ```
- [ ] `tests/unit/test_config.py` confirms `Settings` loads with default values when no `.env` file exists
- [ ] **Do NOT create the actual `.env` file in the repo.** Vivek will create it locally after the ticket merges by copying `.env.example` and filling in real values.
- [ ] `README.md` includes a "Setup secrets" section explaining `cp .env.example .env` and editing it.

### CI workflow
- [ ] `.github/workflows/ci.yml` runs on push and pull_request:
  - Sets up Python 3.11
  - Installs dev dependencies via `pip install -e ".[dev]"`
  - Runs `pytest -q --cov=app`
  - Runs `ruff check .`
  - Runs `mypy app/`
  - Runs `lint-imports`
  - Fails the workflow if any step fails
  - Does NOT need API keys at this stage — no adapter tests run yet

### Smoke tests
- [ ] `tests/unit/test_smoke.py` with one passing assertion (e.g., `assert 1 + 1 == 2`) — confirms test infra works
- [ ] `tests/unit/test_imports.py` confirming all `app.*` packages can be imported without error
- [ ] `tests/unit/test_config.py` confirming Settings loads cleanly with no `.env` present (uses defaults)

### Streamlit placeholder
- [ ] `app/ui/main.py` runs with `streamlit run app/ui/main.py` and shows:
  ```python
  import streamlit as st
  st.set_page_config(page_title="Investment Dashboard", layout="wide")
  st.title("Investment Dashboard")
  st.caption("Placeholder — TICKET-007 will replace this with the real UI.")
  ```

### README
- [ ] `README.md` with:
  - Project name + 1-line description
  - Setup instructions:
    1. `conda env create -f environment.yml`
    2. `conda activate investment-dashboard`
    3. `pip install -e ".[dev]"`
    4. `cp .env.example .env` and edit `.env` with your API keys
  - Run instructions: `streamlit run app/ui/main.py`
  - Test instructions: `pytest`
  - Link to `docs/PROJECT_STATE.md` and `docs/ARCHITECTURE.md`

### Workflow checks
- [ ] All commands pass locally: `pytest && ruff check . && mypy app/ && lint-imports`
- [ ] Branch `ticket-000-scaffolding` pushed to origin
- [ ] PR opened via `gh pr create --fill --base main`
- [ ] PR URL printed in the session summary
- [ ] CI runs on the PR and passes

### State updates
- [ ] `docs/SESSION_LOG.md` has a new entry for this session
- [ ] `docs/PROJECT_STATE.md` shows TICKET-000 in "In review" (not "In progress")
- [ ] `docs/TICKETS/TICKET-000-scaffolding.md` Status field updated to `IN_REVIEW`

## Files created

```
.github/workflows/ci.yml
.gitignore
.importlinter
.env.example                    ← placeholder env vars, committed
README.md
environment.yml
pyproject.toml
app/__init__.py
app/config.py                   ← pydantic-settings Settings class
app/domain/__init__.py
app/services/__init__.py
app/ports/__init__.py
app/adapters/__init__.py
app/ui/__init__.py
app/ui/main.py
tests/__init__.py
tests/unit/__init__.py
tests/unit/test_smoke.py
tests/unit/test_imports.py
tests/unit/test_config.py
```

## Files NOT created (Vivek does these locally after merge)

```
.env                            ← Vivek copies from .env.example and fills in real keys
data/portfolio.json             ← Created by future ticket or manually
```

## Out of scope

- Any domain models — that is TICKET-001
- Any actual UI styling, dark CSS — that is TICKET-007
- Any adapters — those are TICKET-003 onward
- Any FIFO logic — that is TICKET-002
- Wiring `Settings` into actual adapter calls — happens in TICKET-005 (price adapters)

## Notes

- Use Python 3.11.
- Conda env name: `investment-dashboard`.
- The placeholder Streamlit page must be the simplest possible — no styling, no logic.
- **Secrets pattern**: every adapter that needs a key receives it via the `Settings` object as a constructor parameter. NO adapter ever calls `os.getenv` directly. This keeps the secret-loading boundary at exactly one file (`app/config.py`).
- Vivek will set up branch protection on `main` AFTER this ticket merges, since branch protection requires the CI workflow to exist as a status check first. Mention this in the PR description.
- If `gh` is not authenticated, stop and tell Vivek to run `gh auth login`.
