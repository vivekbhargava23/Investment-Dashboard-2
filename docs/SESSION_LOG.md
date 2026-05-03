# SESSION_LOG.md

Append-only log of every Claude Code session and significant Claude Chat session.
Newest entries at the bottom.

When this file exceeds ~500 lines, archive everything older than 30 days into `docs/SESSION_LOG_ARCHIVE_<year>_Q<N>.md` and keep this file lean.

---

## 2026-05-03 — Foundation setup (Claude Chat)

**Surface:** Claude Chat (claude.ai)
**Participants:** Vivek + Claude
**Duration:** ~1.5 hours

### What got done
- Decided on greenfield rebuild (old repo archived as reference only)
- Confirmed stack: Streamlit + Pydantic v2 + JSON storage
- Designed the state-handoff system (PROJECT_STATE.md + SESSION_LOG.md + ADRs + TICKETS)
- Defined the Vivek/Claude Chat/Claude Code division of labor
- Drafted root `CLAUDE.md`, `PROJECT_STATE.md`, `METHODOLOGY.md`, `ARCHITECTURE.md`
- Drafted `BACKLOG.md` and `TICKET-000` in detail
- Drafted `ADR-001` (Streamlit over FastAPI)
- Set up `.github/PULL_REQUEST_TEMPLATE.md` for standardized PRs

### Decisions made
- ADR-001: Streamlit over FastAPI+React
- ADR-002: JSON over SQLite (with port for swap) — ADR file pending
- ADR-003: FIFO replay-on-edit (not immutable lots) — ADR file pending
- ADR-004: Cost basis frozen at transaction-date ECB FX — ADR file pending
- Workflow: Claude Code does all commits and opens PRs; Vivek reviews and merges; `main` is branch-protected

### Follow-ups
- Vivek to create empty repo, drop in scaffold files, push initial commit
- Vivek to authenticate `gh` CLI: `gh auth login`
- Vivek to set up branch protection on `main` after TICKET-000 lands (CI must exist first as a status check)
- First Claude Code session: TICKET-000 (scaffolding + CI)

### Files produced
All files under `docs/`, `.github/PULL_REQUEST_TEMPLATE.md`, root `CLAUDE.md`. See repo for current state.

---

## 2026-05-03 — TICKET-000

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~25 min
**Branch:** ticket-000-scaffolding
**PR:** https://github.com/vivekbhargava23/Investement-Dashboard-Claude/pull/1
**Status at session end:** IN_REVIEW

### What got done
- Created `pyproject.toml` with runtime + dev deps, ruff/mypy/pytest config
- Created full `app/` package structure: domain, services, ports, adapters, ui sub-packages
- Created `app/config.py` — pydantic-settings `Settings` class (single secret-loading boundary)
- Created `app/ui/app.py` — Streamlit placeholder page
- Created `tests/unit/` — smoke, import, and config tests (5 passing)
- Created `.github/workflows/ci.yml` — pytest + ruff + mypy + lint-imports on every push/PR
- Created `.importlinter` — 3 contracts enforcing clean-architecture layer boundaries
- Created `.env.example`, `environment.yml`, `README.md`

### Files touched
- `pyproject.toml` — new
- `environment.yml` — new
- `.gitignore` — added project-specific entries to existing file
- `.importlinter` — new
- `.env.example` — new
- `README.md` — replaced placeholder with full setup/run/test instructions
- `app/__init__.py` + all sub-package `__init__.py` — new
- `app/config.py` — new
- `app/domain/CLAUDE.md` — new
- `app/ui/app.py` — new
- `tests/unit/test_smoke.py`, `test_imports.py`, `test_config.py` — new
- `.github/workflows/ci.yml` — new

### Tests
0 passing → 5 passing (3 new test files)

### Decisions made during the session
- Used `setuptools.build_meta` backend (not `setuptools.backends.legacy` — not available in the installed setuptools version)
- No architectural decisions made

### Out-of-scope items noticed
- (none)

---

## 2026-05-03 — TICKET-001

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~45 min
**Branch:** ticket-001-domain-models
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Implemented `Money` value object with normalized Decimal precision and arithmetic/comparison operators.
- Implemented `Transaction` model with validation for EUR FX rates, ticker case, and share quantities.
- Implemented `OpenLot` and `Position` models with consistency checks between positions and underlying lots.
- Created exhaustive unit tests for all domain models, including property-based tests for `Money`.
- Restored `.importlinter` configuration to enforce clean architecture layers.
- Exported all models via `app.domain.__init__.py`.
- All tests and lints (ruff, mypy strict, import-linter) pass.

### Files touched
- `app/domain/money.py` — new
- `app/domain/models.py` — new
- `app/domain/positions.py` — new
- `app/domain/__init__.py` — updated
- `tests/unit/domain/test_money.py` — new
- `tests/unit/domain/test_transaction.py` — new
- `tests/unit/domain/test_positions.py` — new
- `.importlinter` — new (restored)
- `app/domain/CLAUDE.md` — updated
- `docs/PROJECT_STATE.md` — updated
- `docs/SESSION_LOG.md` — updated

### Tests
5 passing → 32 passing (27 new tests)

### Decisions made during the session
- Used `StrEnum` (Python 3.11+) for `Currency` and `TransactionType` as suggested by `ruff`.
- Used `from __future__ import annotations` to support modern type hint syntax with forward references.
- Return types for `Money` arithmetic operators were adjusted to `Money` instead of `Self` to satisfy `mypy`'s strictness with Pydantic models.

### Out-of-scope items noticed
- `.importlinter` was missing from the repo despite being mentioned in TICKET-000 and ARCHITECTURE.md. Restored it.

---

## 2026-05-03 — TICKET-003

**Surface:** Gemini CLI
**Model:** Gemini 2.0 Pro
**Duration:** ~30 min
**Branch:** _pending_
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Implemented `TransactionRepository` port (Protocol) in `app/ports/repository.py` with CRUD and atomic save methods.
- Implemented `JsonTransactionRepository` adapter in `app/adapters/repo_json/json_repo.py` using Pydantic serialization.
- Implemented atomic writes using a temporary file, `fsync`, and `os.replace` to prevent data corruption.
- Added schema versioning (`version: 1`) to the JSON file format.
- Created 18 integration tests in `tests/integration/test_json_repo.py` covering CRUD, atomic writes, corruption handling, and Decimal precision.
- All tests (63 passing), lints (ruff), and type checks (mypy) pass.
- `import-linter` contracts verified.

### Files touched
- `app/ports/repository.py` — new
- `app/ports/__init__.py` — updated
- `app/adapters/repo_json/__init__.py` — new
- `app/adapters/repo_json/json_repo.py` — new
- `tests/integration/test_json_repo.py` — new
- `docs/TICKETS/TICKET-003-json-repository.md` — updated
- `docs/PROJECT_STATE.md` — updated
- `docs/TICKETS/BACKLOG.md` — updated
- `docs/SESSION_LOG.md` — updated

### Tests
45 passing → 63 passing (18 new)

### Decisions made during the session
- Used `collections.abc.Sequence` for type hints in the port and adapter.
- Implemented parent directory creation in `save_all`.
- Chained underlying exceptions in `RepositoryCorruptedError` for better debugging.

### Out-of-scope items noticed
- (none)

---

## 2026-05-03 — TICKET-004-005

**Surface:** Gemini CLI
**Model:** Gemini 2.0 Pro
**Duration:** ~45 min
**Branch:** ticket-004-005-yfinance-adapter
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Implemented `PriceProvider` and `FxProvider` ports (Protocols) with detailed error classes.
- Implemented `YfinanceAdapter` satisfying both ports with in-memory caching and 60s TTL.
- Added currency inference heuristic for European tickers (.DE, .F, etc.).
- Implemented EUR/USD FX rate handling with automatic inversion for USD/EUR lookups.
- Created `FakePriceProvider` and `FakeFxProvider` for unit testing downstream services.
- Added integration tests gated by `--run-integration` flag hitting real yfinance.
- Verified all unit and integration tests (94 passing), lints (ruff), type checks (mypy), and import contracts.

### Files touched
- `app/ports/price_feed.py` — new
- `app/ports/fx_feed.py` — new
- `app/ports/__init__.py` — updated
- `app/adapters/yfinance_feed/__init__.py` — new
- `app/adapters/yfinance_feed/yfinance_adapter.py` — new
- `tests/fakes/__init__.py` — new
- `tests/fakes/price_feed.py` — new
- `tests/fakes/fx_feed.py` — new
- `tests/unit/adapters/test_yfinance_adapter_caching.py` — new
- `tests/unit/adapters/test_yfinance_adapter_inference.py` — new
- `tests/unit/adapters/test_yfinance_adapter_errors.py` — new
- `tests/unit/fakes/test_fakes.py` — new
- `tests/integration/test_yfinance_real.py` — new
- `tests/conftest.py` — new
- `pyproject.toml` — updated
- `docs/TICKETS/TICKET-004-005-yfinance-adapter.md` — updated
- `docs/PROJECT_STATE.md` — updated
- `docs/TICKETS/BACKLOG.md` — updated
- `docs/SESSION_LOG.md` — updated

### Tests
63 passing → 94 passing (31 new: 27 unit, 4 integration)

### Decisions made during the session
- Used `time.monotonic()` for cache TTL to ensure immunity to system clock changes.
- Implemented 7-day look-back expansion for historical data to handle weekends/holidays.
- Used `Decimal(str(float))` conversion to avoid floating point precision issues.
- Integrated `integration` marker in `pyproject.toml` and custom `pytest` hook in `conftest.py`.

### Out-of-scope items noticed
- (none)
