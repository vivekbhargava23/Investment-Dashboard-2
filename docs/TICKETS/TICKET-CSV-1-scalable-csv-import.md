# TICKET-CSV-1 — Scalable Capital CSV import (trades only)

**Status:** IN_PROGRESS
**Priority:** HIGH
**Estimated session length:** 2 hr
**Drafted by:** Vivek + Claude (chat session 2026-05-15)
**Implemented by:** TBD
**Milestone:** Foundation

## Problem

Today portfolio bootstrap goes through `app/scripts/seed_portfolio.py` reading a hand-curated `docs/reference/seed_portfolio.csv`. This is artificial. Vivek's real portfolio lives at Scalable Capital and he can export the full transaction history as a CSV (semicolon-separated, EUR-native, sample: `2026-05-14_20-00-30_ScalableCapital-Broker-Transactions.csv`). The seed approach is now obsolete.

We need a CSV import pipeline that:

1. Reads the Scalable export directly into `data/portfolio.json` (the existing repository format — no domain model changes).
2. Maps Scalable's ISIN-only identifiers to Yahoo-style tickers (NVDA, MU, etc.) via an editable mapping file.
3. Survives missing mappings gracefully — the app keeps working with whatever's mapped, unmapped ISINs are quarantined for the user to resolve later.
4. Is idempotent: re-running on a newer CSV export adds new rows but does not duplicate existing ones.
5. Handles only true trade events in v1 (Buy, Sell, Savings plan, Security transfer). Non-trade events (Distribution, Interest, Taxes/Vorabpauschale, Corporate action with shares) are skipped with a counted summary and deferred to TICKET-CSV-3.

## CSV format reference (from real export, 2026-05-14)

Semicolon-separated, European number format (`,` decimal, `.` thousands), UTF-8, 14 columns:

```
date;time;status;reference;description;assetType;type;isin;shares;price;amount;fee;tax;currency
```

Sample rows (each row shown once per type we care about):

```
2026-05-13;08:57:51;Executed;"SCALWs6zGYc5iX3";"ServiceNow";Security;Buy;US81762P1021;4;76,51;-306,04;0,99;0,00;EUR
2026-04-24;08:30:09;Executed;"SCALnAqHCXVxXKk";"Vanguard S&P 500 (Acc)";Security;Sell;IE00BFMXXD54;15;117,355;1.760,325;0,99;40,45;EUR
2026-01-16;11:46:29;Executed;"SCALZHDgcCy8jrP";"Marvell Technology";Security;Savings plan;US5738741041;7,054176;70,88;-499,99999488;0,00;0,00;EUR
2025-12-06;01:00:00;Executed;"SWITCH-101-…-FR0004038263-WDP";"Parrot";Security;Security transfer;FR0004038263;50;8,68;434,00;;;EUR
```

Skipped rows: rows where `status` is not `Executed` (Cancelled / Expired / Rejected — all have `shares=0` and zero amounts in the real export). Also skipped in v1: any `type` not in {Buy, Sell, Savings plan, Security transfer}, and `Corporate action` rows even when `assetType=Security` (these include negative-share writeoffs that need design work — defer to TICKET-CSV-3).

Cardinality from the reference export (302 data rows): 73 Buy, 55 Sell, 52 Savings plan, 26 Security transfer = **206 in-scope rows**. 53 Deposit, 21 Distribution, 11 Taxes, 5 Interest, 3 Withdrawal, 2 Corporate action = **95 out-of-scope rows**. 14 Cancelled + 2 Expired + 2 Rejected = **18 status-filtered rows**.

All rows in the reference export have `currency=EUR`. The import script must reject (with a clear error) any row whose currency column is not `EUR` — Scalable shows EUR-equivalent for US/UK instruments natively, so a non-EUR row would indicate a format change worth flagging rather than silently handling.

## Architecture overview

### New files

```
data/scalable_raw.csv               # gitignored — user drops the export here
data/isin_map.json                  # source of truth for ISIN → ticker mapping
tools/import_scalable_csv.py        # the import command (replaces app/scripts/seed_portfolio.py)
app/adapters/scalable_csv/__init__.py
app/adapters/scalable_csv/parser.py  # pure CSV → typed rows (domain-adjacent, no I/O beyond reading)
app/adapters/scalable_csv/importer.py  # orchestrates parser + isin_map + repo
app/adapters/isin_map/__init__.py
app/adapters/isin_map/repo.py        # JSON load/save for isin_map.json
app/domain/isin_map.py               # IsinMapping, IsinMapDocument Pydantic models
app/ports/isin_map.py                # IsinMapRepository Protocol
```

### Deleted files

```
app/scripts/seed_portfolio.py        # replaced by tools/import_scalable_csv.py
docs/reference/seed_portfolio.csv    # obsolete (keep in git history; delete from main)
tests/unit/test_seed_portfolio.py    # if present, replace with test_import_scalable_csv.py
```

The `app/scripts/migrate_currency.py` script stays — it's a separate concern.

### `isin_map.json` schema

```json
{
  "version": 1,
  "entries": {
    "US67066G1040": {
      "ticker": "NVDA",
      "name": "NVIDIA",
      "status": "mapped",
      "last_seen_in_csv": "2026-05-14"
    },
    "JP3721400004": {
      "ticker": null,
      "name": "Japan Steel Works",
      "status": "unmapped",
      "last_seen_in_csv": "2026-05-14"
    }
  }
}
```

Rules:
- Keys are ISINs (uppercase, 12 chars).
- `ticker` is the Yahoo symbol (e.g. `NVDA`, `5631.T`, `IE00BFMXXD54.L`) — same shape as `Transaction.ticker` today. `null` when status is `unmapped`.
- `name` is the human-readable name from CSV's `description` column on the most recent import. Used by the Mappings UI in CSV-2.
- `status` is `mapped` or `unmapped`. Only `mapped` entries flow into portfolio.json.
- `last_seen_in_csv` is the date column of the most recent CSV row referencing this ISIN. Helps Vivek see which mappings are stale.

### Transaction.id strategy

Use the CSV's `reference` column verbatim as `Transaction.id`. This is stable across re-exports (Scalable doesn't re-issue them) and gives us natural deduplication: if a reference is already in `portfolio.json`, skip it on re-import. No UUIDs.

The `reference` column is quoted in the CSV but the quotes are CSV-level escaping, not part of the value. After parsing it's a plain string like `SCALWs6zGYc5iX3` or `SWITCH-101-6bGhp5rRF7hYfm8fAueTLK-FR0004038263-WDP`. Both fit Transaction.id's `str` type without modification.

### Row → Transaction mapping

| CSV `type` | `TransactionType` | Notes |
|---|---|---|
| Buy | BUY | straightforward |
| Savings plan | BUY | autobuy is identical to a Buy from FIFO's perspective; only differs in ticket source (the savings plan engine vs manual order) |
| Sell | SELL | straightforward |
| Security transfer | BUY | the Dec-2025 migration into Scalable — preserves real cost basis |

For all four:
- `id` ← CSV `reference`
- `ticker` ← `isin_map.entries[isin].ticker` (must be status=mapped, else skip row)
- `trade_date` ← CSV `date` (`YYYY-MM-DD`)
- `shares` ← CSV `shares` (parse European number; reject if blank — only non-trade rows have blank shares)
- `price_native` ← `Money(amount=CSV price, currency=EUR)` (parse European number)
- `fees_native` ← `Money(amount=CSV fee, currency=EUR)` if fee present and non-zero, else None. `Security transfer` rows have blank fee → None.
- `fx_rate_eur` ← `Decimal("1.0")` (the CSV is EUR-native per ADR-005, so the EUR-native form's invariant applies: native currency is EUR, FX rate is 1.0)
- `notes` ← CSV `description` (the human name; useful audit trail when ISIN→ticker mapping is wrong)

The `tax` column on Sell rows (e.g. 40,45 on the Vanguard sell) is the *Abgeltungsteuer withheld at source by Scalable* — informational only for v1. We compute our own tax in the tax engine. Captured into notes as `"tax_withheld_eur=40.45"` for traceability but not used in any calculation.

The `amount` column is `shares × price ± fee` and serves as a sanity check. The importer must verify `|computed - csv_amount| < 0.01 EUR` per row and reject with a clear error if not (defense against format change).

### Idempotent re-import

Algorithm:

1. Load current `data/portfolio.json` (may be empty / missing — that's fine, treat as `[]`).
2. Build a set of existing `Transaction.id` values.
3. Parse the CSV.
4. For each in-scope row:
   - If row's `reference` is already in the existing-id set → skip silently (counted as `existing`).
   - Else if its ISIN is `unmapped` in `isin_map.json` → quarantine (counted as `unmapped`).
   - Else → construct Transaction, append to additions list (counted as `new`).
5. For each in-scope row whose ISIN is not yet in `isin_map.json`: add a new `unmapped` entry with the name from CSV.
6. For each in-scope row whose ISIN *is* in `isin_map.json`: update `last_seen_in_csv` to the row's date if later than the current value.
7. Save `isin_map.json`.
8. Save `portfolio.json` with `existing_transactions + additions`.
9. Print summary.

### Summary output

```
Scalable CSV import — 2026-05-14_20-00-30_ScalableCapital-Broker-Transactions.csv
=============================================================================
Rows in CSV:         302
  Status-filtered:   18    (Cancelled: 14, Expired: 2, Rejected: 2)
  Out of scope:      95    (Deposit/Distribution/Interest/Taxes/Withdrawal/Corp-action — see TICKET-CSV-3)
  In scope:          189
    Already in portfolio:  155
    New transactions:      26    (added to data/portfolio.json)
    Unmapped ISINs:        8     (skipped; map them in isin_map.json and re-run)

ISIN mapping status (15 unique ISINs in scope):
  ✓ Mapped:    13
  ✗ Unmapped:  2
    JP3721400004  Japan Steel Works
    GB00BNRRF105  CoinShares Physical Staked Algorand

Portfolio now has 181 transactions across 12 unique tickers.
```

(Numbers are illustrative — actual counts depend on CSV state.)

## Acceptance criteria

- [ ] `tools/import_scalable_csv.py --input data/scalable_raw.csv` runs end-to-end against the real 2026-05-14 export and exits 0.
- [ ] After running on the real export, `data/portfolio.json` contains exactly the in-scope Executed Buy/Sell/Savings-plan/Security-transfer rows whose ISIN is mapped. No duplicates by `id`.
- [ ] Running the importer twice in a row on the same CSV produces zero new transactions on the second run (idempotent).
- [ ] `data/isin_map.json` is created on first run with one entry per unique in-scope ISIN, status=unmapped for all initially.
- [ ] When an ISIN is manually flipped to status=mapped with a ticker, the next import picks up its rows.
- [ ] Unmapped ISINs do NOT block import of mapped ones — partial imports succeed with a clear summary of what was skipped.
- [ ] Non-EUR currency on any row → import aborts with a clear error referencing the row number and ISIN. (No row in the real export hits this; it's a defense.)
- [ ] `app/scripts/seed_portfolio.py` is deleted. `docs/reference/seed_portfolio.csv` is deleted. Any test file referencing them is removed or rewritten against the new importer.
- [ ] `data/scalable_raw.csv` is added to `.gitignore`. `data/portfolio.json` was already gitignored — leave that as-is. `data/isin_map.json` is committed (it's reference data, not user-private — but contains no transaction details, only ISIN→ticker mapping).
- [ ] The amount sanity check (`|shares×price + fee_signed - csv_amount| < 0.01`) is enforced on every in-scope row.
- [ ] `Transaction.fx_rate_eur` is `Decimal("1.0")` for every imported transaction (per ADR-005).
- [ ] Tests pass: `pytest tests/unit/test_scalable_csv_*.py tests/unit/test_isin_map_*.py`
- [ ] Lints pass: `ruff check . && mypy app/ && lint-imports`

## Files likely touched

- `app/adapters/scalable_csv/__init__.py` (new)
- `app/adapters/scalable_csv/parser.py` (new) — pure functions: bytes/path → list[ParsedCsvRow]; ParsedCsvRow is a small Pydantic model representing one CSV row with typed fields (no mapping logic, no I/O beyond opening the file)
- `app/adapters/scalable_csv/importer.py` (new) — orchestrator: takes parser output + IsinMapRepository + TransactionRepository, returns ImportSummary
- `app/adapters/isin_map/__init__.py` (new)
- `app/adapters/isin_map/repo.py` (new) — JsonIsinMapRepository (load_all / save_all / mark_seen / add_unmapped)
- `app/domain/isin_map.py` (new) — IsinMapping (single entry), IsinMapDocument (the file's root)
- `app/ports/isin_map.py` (new) — IsinMapRepository Protocol
- `tools/import_scalable_csv.py` (new) — thin CLI: parse args, wire adapters, call importer, print summary
- `app/scripts/seed_portfolio.py` (delete)
- `docs/reference/seed_portfolio.csv` (delete)
- `.gitignore` (add `data/scalable_raw.csv`)
- `tests/unit/test_scalable_csv_parser.py` (new)
- `tests/unit/test_scalable_csv_importer.py` (new)
- `tests/unit/test_isin_map_repo.py` (new)
- `tests/fixtures/scalable_csv/` (new — small fixture CSVs covering each scenario)

## Out of scope

- **Streamlit UI for mapping.** That's TICKET-CSV-2. v1 is CLI-only; Vivek edits `isin_map.json` by hand for the first run (and CSV-2 will replace that workflow).
- **Distribution / Interest / Taxes / Vorabpauschale / Corporate action handling.** Counted in the summary, skipped from import. TICKET-CSV-3.
- **Auto-resolution via yfinance ISIN lookup.** Manual mapping only. We can add auto-resolve later if 30+ ISINs becomes painful.
- **Changes to `TransactionType`** — the existing BUY / SELL values cover everything in scope.
- **Changes to `Transaction.id` regeneration for the existing seed data.** Since the old seed flow is deleted entirely and v1 starts from the real CSV, there's no migration story — Vivek runs the new importer once and `portfolio.json` is rebuilt from Scalable's references. (The implementation agent should delete any existing `data/portfolio.json` before the first real import; the script should NOT auto-delete it — Vivek does this manually so accidental data loss is impossible.)
- **The Streamlit app reading `data/scalable_raw.csv` directly.** The app reads `data/portfolio.json` as today. The CSV is only ever read by the importer.

## Test cases

Use small fixture CSVs under `tests/fixtures/scalable_csv/` — one CSV per scenario, 3-10 rows each. Do not load the real 302-row export in unit tests (that's a manual integration check).

### Parser tests (`test_scalable_csv_parser.py`)

1. **Happy path**: 4-row CSV with one Buy, one Sell, one Savings plan, one Security transfer. Parser returns 4 typed rows with correctly parsed decimals (European format → Decimal, e.g. `"1.760,325"` → `Decimal("1760.325")`).
2. **European number edge cases**: `"0,00"`, `"-306,04"`, `"7,054176"` (6-decimal savings-plan shares), `"1.760,325"` (thousands separator + decimal).
3. **Quoted fields with embedded characters**: descriptions like `"Vanguard S&P 500 (Acc)"` and `"21shares Polygon ETP"` parse cleanly (the `&` and parens must survive).
4. **Blank fields**: Distribution rows have blank shares/price; parser produces a row with those fields as None rather than crashing.
5. **Status filter is NOT applied in parser** — parser returns all rows. Filtering is the importer's job (separation of concerns; future tooling may want all rows).
6. **Malformed row** (wrong column count, unparseable date): parser raises a precise error referencing the row number, does not silently skip.

### Importer tests (`test_scalable_csv_importer.py`)

1. **Empty portfolio.json + 4-row CSV (all mapped, all in scope)** → produces 4 Transaction objects with correct fields. `id == reference`, `fx_rate_eur == 1.0`, `price_native.currency == EUR`.
2. **Idempotent re-import**: running on the same CSV twice produces 4 transactions the first time, 0 new the second time. Summary correctly reports `existing: 4, new: 0`.
3. **Partial CSV update**: existing portfolio has 3 transactions (refs A, B, C). New CSV contains refs B, C, D, E. Result: D and E added, A preserved (it's in portfolio but not in CSV — must not be deleted), B and C unchanged.
4. **Unmapped ISIN**: 2-row CSV, one ISIN mapped, one unmapped. Result: 1 transaction added, 1 quarantined. Summary lists the unmapped ISIN with its name. `isin_map.json` gets the unmapped entry with `status=unmapped, ticker=null`.
5. **New ISIN seen for first time**: ISIN not in `isin_map.json` at all → added with `status=unmapped` and the row is treated as quarantined.
6. **Status filter**: 5-row CSV with one Cancelled, one Expired, one Rejected, one Executed-Buy, one Executed-Sell. Result: 2 transactions added, 3 filtered with the right counts in summary.
7. **Out-of-scope type filter**: CSV with Distribution, Interest, Taxes, Corporate-action rows → all skipped, all counted under "out of scope" in summary.
8. **Amount mismatch defense**: CSV row where `shares × price + fee ≠ amount` (force-edited fixture). Importer aborts with row-number error. (For Buy: amount is negative, so check is `|shares × price + fee - (-amount)| < 0.01`. The sign convention is documented in code.)
9. **Non-EUR currency defense**: CSV row with `currency=USD` → import aborts.
10. **`last_seen_in_csv` update**: existing isin_map entry for NVDA with `last_seen_in_csv=2025-12-01`; CSV has a 2026-04-24 NVDA row. After import, the entry's `last_seen_in_csv` is `2026-04-24`.
11. **Fees None on Security transfer**: a transfer row has blank fee; resulting Transaction has `fees_native=None`. Buy/Sell rows with `fee=0,00` produce `fees_native=Money(0, EUR)` (not None — zero is a valid fee).
12. **Savings plan fractional shares**: a row with `shares=7,054176` produces `Transaction.shares=Decimal("7.054176")`. (FIFO already handles fractional shares; this just confirms the parse path preserves precision.)

### IsinMap repo tests (`test_isin_map_repo.py`)

1. Load missing file → returns empty `IsinMapDocument`.
2. Save then load → round-trips cleanly (including `last_seen_in_csv: None` for entries that never had a date).
3. Two entries with the same ISIN cannot exist (it's a dict — schema enforces this).
4. Saving rewrites atomically (write-temp + rename) so a crashed save doesn't corrupt the file.

## Notes

### macOS BSD portability

The agent is on macOS with bash 3.2 + BSD userland (per AGENTS.md). The import script is pure Python, so userland portability is irrelevant for the script itself. Tests use only stdlib + project deps. No shell scripts needed for the importer; if any helper shells are written, follow `tools/README.md` portability rules.

### Bench-test (per methodology checklist item 1)

Walked the spec against the real CSV before drafting. Specific things verified by reading 302 rows:
- All rows are EUR (column 14). FX inference at import time would be dead code.
- The `reference` column is unique per Executed row, and Cancelled rows have their own distinct references (also unique). Safe to use as Transaction.id.
- `Security transfer` rows have blank `fee` (column 12). The fee column position is fixed regardless — parsing handles blank.
- `Savings plan` rows have non-integer shares (e.g. `7,054176`) — confirmed our existing `Transaction.shares: Decimal` handles arbitrary precision.
- `Corporate action` includes one row with `assetType=Security` and `shares=-26` (the Apple Short Turbo writeoff). v1 skips this — handling negative-share corp actions is design work for CSV-3.

### Anti-approximation (per methodology checklist item 2)

No placeholders in the spec. Every CSV column either has a defined mapping or is explicitly out of scope with a tracked ticket (CSV-3) to address it. No "use X as approximation" anywhere.

### Domain-layer purity

`app/domain/isin_map.py` is pure Pydantic models. The repo lives under `app/adapters/`. Importer logic lives under `app/adapters/scalable_csv/` because it's I/O-bound (reads CSV, writes JSON). The domain layer has zero new I/O imports — AGENTS.md rule #3 holds.

### Why `tools/import_scalable_csv.py` and not `app/scripts/`

The existing `app/scripts/seed_portfolio.py` is being deleted, and `tools/` is the established home for portable shell + Python utilities Vivek runs by hand (`tools/file.sh`, `tools/regen_context.py`). The importer is an operator tool, not an app entry point — `tools/` is the right home. If the agent reads `tools/README.md` and finds it documents the dir as bash-only, update that README in this PR.
