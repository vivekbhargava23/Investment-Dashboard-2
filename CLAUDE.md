# CLAUDE.md — Master Project Instructions

## Project
Investment Panel Dashboard — personal portfolio analysis tool for a retail investor in Germany on Scalable Capital. 
*(Note: Behavioural tracking and Decision Gates have been intentionally pruned to focus on core stability).*

## Environment
- **Python:** 3.11.13 via Conda
- **Activate:** `conda activate investment-dashboard`
- **Run app:** `streamlit run app/main.py`
- **Run tests:** `pytest tests/ -v`

## Strict Development Rules (Autonomous Git)
- **Autonomous Git:** You are responsible for the entire Git flow. After writing code and ensuring `pytest tests/` passes, you must automatically `git add`, write a conventional commit (`feat:`, `fix:`, etc.), and `git push`. 
- **One file at a time:** write, verify it runs, commit, then next file.
- **Never hardcode** API keys or config — everything in `.env`, accessed via `app/config/settings.py`.

## Architecture — Four Layers
Data flows strictly: `UI (app/ui/) → Core (app/core/) → Services (app/services/) → External APIs`.
- **UI components only render** — never calculate.
- **Data Model:** The system uses an append-only `Transaction` log. Open lots and realised disposals are *derived* by replaying this log, never mutated destructively.

## German Tax Rules
- **FIFO lot accounting:** mandatory under German law, no average cost.
- **Abgeltungsteuer:** 26.375% (25% + 5.5% solidarity surcharge).
- **Sparerpauschbetrag:** €1,000 annual tax-free allowance.

## Remaining Refactor Roadmap
- **Phase 5:** Migrate `data/portfolio.json` from the old lot-list schema to the new transaction-log schema.
- **Phase 6:** Update `price_service` and `history_service` to consume the new `Transaction` shape; vectorise history math.
- **Phase 7:** Cut chart load time via batched downloads in `history_service`.
- **Phase 8:** Implement one coherent caching strategy via `app/utils/cache.py`.
- **Phase 9:** Create a single canonical transaction-entry component and remove UI duplication.
- **Phase 10:** Implement a local JSON catalogue for instant ticker autocomplete.
