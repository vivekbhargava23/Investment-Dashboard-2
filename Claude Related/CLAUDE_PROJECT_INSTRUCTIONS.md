# Investment Panel Dashboard — Claude Project Instructions

to start claude
cd ~/Desktop/Apps/investment-panel-dashboard-2026
conda activate investment-dashboard
claude


control + c to exit calude code

## What This Project Is
A professional investment tracking dashboard built in Python + Streamlit for a retail investor in Germany. Tracks a concentrated equity portfolio across AI infrastructure, semiconductors, defence, and power infrastructure. Supports the Investment Panel session framework.

## How to Work With Me on This Project

### At the start of every session, tell me:
1. Which phase we are working on
2. Upload the relevant phase `.md` doc from the `/docs` folder in the repo
3. Any terminal output or errors from where we left off

### Documentation standard
- All docs are `.md` files stored in `/docs` in the repo
- Never generate `.docx` for internal project docs
- Each phase has its own doc: `phase1_foundation.md`, `phase2_domain_models.md` etc
- Docs are committed to git so they version with the code

### Development rules
- One file at a time — write it, verify it works, commit it, then move to next
- Every file gets a verification command before committing
- Commit message convention: `feat:` for new code, `chore:` for setup, `fix:` for bugs, `test:` for tests, `docs:` for documentation
- Always activate conda environment first: `conda activate investment-dashboard`
- Never hardcode API keys, tax rates, or config values — everything goes in `.env`

### Architecture rules (never break these)
- UI components only render — they never calculate
- All domain logic lives in `app/core/`
- All external API calls go through `app/services/`
- All data access goes through `app/data/repository.py`
- All formatting goes through `app/utils/formatting.py`
- All logging uses `get_logger(__name__)` from `app/utils/logger.py`
- Settings are always accessed via `get_settings()` from `app/config/settings.py`

### Key technical facts
- Python 3.11.13, Conda env named `investment-dashboard`
- Streamlit runs from terminal only — not from Spyder's run button
- Frankfurt tickers use yfinance (HY9H.F, RHM.DE, MTE.DE)
- US tickers use Finnhub free tier (60 req/min)
- German tax: FIFO lot accounting, 26.375% Abgeltungsteuer, €1,000 Sparerpauschbetrag
- Data persisted in `data/portfolio.json` — gitignored, local only

### Current build status
| Phase | Status | Doc |
|---|---|---|
| Phase 1 — Foundation | ✅ Complete | `docs/phase1_foundation.md` |
| Phase 2 — Domain Models + FIFO Engine | 🔲 Next | `docs/phase2_domain_models.md` |
| Phase 3 — Price Engine | 🔲 Pending | — |
| Phase 4 — UI Overview Page | 🔲 Pending | — |
| Phase 5 — FIFO Lot Ledger UI | 🔲 Pending | — |
| Phase 6 — Tax Dashboard UI | 🔲 Pending | — |
| Phase 7 — Risk & Milestones UI | 🔲 Pending | — |
| Phase 8 — Session & Behavioural Log UI | 🔲 Pending | — |

### Repo
`https://github.com/vivekbhargava23/investment-panel-dashboard-2026` (private)
