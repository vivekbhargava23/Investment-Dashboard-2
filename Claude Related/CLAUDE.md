# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Personal investment tracking and analysis tool for a retail investor in Germany (Scalable Capital). Tracks a concentrated equity portfolio across AI infrastructure, semiconductors, defence, and power infrastructure. Enforces German tax law (FIFO, Abgeltungsteuer, Sparerpauschbetrag) and supports the Investment Panel session framework.

## Environment

- **Python:** 3.11.13 via Conda — activate first: `conda activate investment-dashboard`
- **First-time setup:** `pip install -e .` — installs the `app` package in editable mode so `from app.xxx import yyy` resolves correctly
- **Run app:** `streamlit run app/main.py`
- **Run tests:** `pytest tests/ -v`
- **Run single test:** `pytest tests/test_fifo.py -v`
- **Lint:** `ruff check app/`
- **Type check:** `mypy app/`
- **Verify settings load:** `python -c "from app.config.settings import get_settings; s = get_settings(); print(s.app_title)"`

## Architecture — Four Layers (strict, never skip)

```
UI (app/ui/) → Core (app/core/) → Services (app/services/) → External APIs
```

- **`app/ui/`** — Renders only. No calculations. Passes data from core to Streamlit widgets.
- **`app/core/`** — All domain logic: Lot, Position, Portfolio, Tax models and FIFO engine.
- **`app/services/`** — External API clients only: Finnhub (US tickers) and yfinance (Frankfurt tickers).
- **`app/data/`** — Data access through `repository.py` only. Storage is `data/portfolio.json` (gitignored, local only).
- **`app/utils/formatting.py`** — All display formatting. Never format numbers inline in UI components.
- **`app/utils/logger.py`** — `get_logger(__name__)` everywhere. `configure_logging()` called once at startup in `main.py` only.
- **`app/config/settings.py`** — `get_settings()` is the single source of truth for all config. Cached with `@lru_cache`.

## Key Technical Decisions

- **Pydantic v2** for all models — typed validation at startup, fail fast on misconfiguration.
- **yfinance** for Frankfurt-listed tickers (HY9H.F, RHM.DE, MTE.DE etc).
- **Finnhub** for US-listed tickers (NVDA, MRVL, MU etc) — 60 req/min free tier, cache aggressively.
- **JSON flat file** (`data/portfolio.json`) — gitignored, local only. Repository pattern means storage backend can be swapped by touching one file.
- **Streamlit** — runs from terminal, not IDE run buttons. Use `st.session_state` carefully to minimise full-page re-renders.

## German Tax Rules (hardcoded constraints)

- **FIFO lot accounting** — mandatory under German law. Never use average cost.
- **Abgeltungsteuer:** 26.375% (25% + 5.5% solidarity surcharge).
- **Sparerpauschbetrag:** €1,000 annual tax-free allowance.
- **Loss pots:** carry forward indefinitely, absorb gains before tax applies.

## Configuration

All config lives in `.env` (gitignored). Required variable: `FINNHUB_API_KEY`. Settings are loaded and validated at startup by `app/config/settings.py` — a missing required variable crashes immediately with a clear error.

## Development Rules

- **One file at a time** — write, verify it runs, commit, then next file.
- **Commit convention:** Conventional Commits — `feat:` / `chore:` / `fix:` / `test:` / `docs:`.
- **Never commit** `.env` or `data/portfolio.json`.
- **Never add packages** without also updating `requirements.txt`.

## Build Status

| Phase | Status |
|---|---|
| Phase 1 — Foundation (settings, logging, formatting) | ✅ Complete |
| Phase 2 — Domain Models (Lot, Position, Portfolio, Tax + FIFO engine) | 🔲 Next |
| Phase 3 — Price Engine (Finnhub + yfinance clients) | 🔲 Pending |
| Phase 4 — UI: Live Position Overview | 🔲 Pending |
| Phase 5 — UI: FIFO Lot Ledger + disposal simulator | 🔲 Pending |
| Phase 6 — UI: Tax Dashboard | 🔲 Pending |
| Phase 7 — UI: Risk Flags, Decision Gates, Pre-Trade Checklist | 🔲 Pending |
| Phase 8 — UI: Behavioural Ledger + Session Log | 🔲 Pending |

Phase 2 build order: `app/core/lot.py` → `app/core/position.py` → `app/core/portfolio.py` → `app/core/tax.py` → `app/data/seeds/portfolio.json` → `tests/test_fifo.py` → `tests/test_tax.py`.

## Documentation

All internal docs are `.md` files in `/docs`. Each build phase gets its own doc (e.g. `phase1_foundation.md`, `phase2_domain_models.md`). Never create `.docx` for internal project docs.
