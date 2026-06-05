# TICKET-CSV-19 — Auto-suggest "ignore" for junk instruments

**Priority:** MEDIUM
**Estimated session length:** 2 hr
**Recommended model:** Sonnet — a heuristic + UI pre-selection; bounded, well-tested.
**Drafted by:** Vivek + Claude Code (session 2026-06-05)
**Implemented by:** TBD
**Milestone:** Investment Panel

---

## Problem

When the auto-resolver can't confidently map an ISIN, it lands in manual review. Many of
those are securities the user will never track — crypto ETPs, knockout/turbo certificates,
leveraged short products. The user wants the workbench to *suggest* which ones to ignore
("ignore these 4"), while still letting them keep and map any of them ("I'll keep this 1").
Right now every unresolved ISIN is presented identically with no steer.

## Solution

Add a pure heuristic that flags likely-junk instruments from the CSV description (and any
resolver metadata available), and in the workbench manual-review panel **pre-select an
"Ignore" suggestion** for flagged rows. The user confirms (one click) or overrides (map it
instead). Nothing is ignored automatically without a confirm.

### Decisions already made — do not re-litigate

- The classifier is a **pure domain/service function** — `suggest_ignore(description: str,
  *, isin: str) -> tuple[bool, str]` returning `(is_junk, reason)`. No I/O. Unit-tested with a
  table of real examples from the user's CSV.
- Heuristic signals (description-based, case-insensitive): contains `ETP`, `Staking`,
  `Turbo`, `Knock`, `Open End`, `Faktor`, `Short`/`Long` + leverage markers, issuer tokens
  like `21shares`, `CoinShares`, `HSBC ... Turbo`. Keep the list small and documented; this is
  a *suggestion*, not a verdict.
- It only ever **suggests**. The user's click is required. A wrong suggestion costs one click
  to override.
- Suggestion shows a short reason ("looks like a crypto ETP") so the user understands why.

### Execution

1. **Domain/service:** `app/services/instrument_triage.py` (or domain if pure) with
   `suggest_ignore(...)`. Unit tests covering the user's five (3× 21shares ETP, CoinShares
   Algorand, HSBC Apple Turbo) → junk; and a control set of real holdings (Vanguard S&P 500,
   Dell, iShares sector ETFs) → not junk.
2. **Workbench UI:** in the manual-review panel, call `suggest_ignore` per row; when junk,
   render the row with the Ignore action visually pre-highlighted and the reason as a caption.
   (Pairs with TICKET-CSV-18's inline Ignore button.)
3. Gate.

## Acceptance criteria

- [ ] `suggest_ignore` is pure, unit-tested, and correctly flags the five known junk ISINs
      while not flagging the user's real holdings.
- [ ] Flagged rows in the workbench show a pre-selected/highlighted Ignore with a reason.
- [ ] No ISIN is ignored without an explicit user click.
- [ ] `pytest`, `ruff check .`, `mypy app/`, `lint-imports` clean.

## Files likely touched

- `app/services/instrument_triage.py` (new) or `app/domain/...`
- `app/ui/pages/import_workbench.py`
- `tests/unit/test_instrument_triage.py` (new)

## Out of scope

- Auto-ignoring without confirmation. Always a suggestion.
- ML / network lookups for classification. Description-based heuristic only.
- Acting on already-imported positions (TICKET-CSV-16).

## Notes / assumptions

- Depends on TICKET-CSV-18 (inline Ignore in the workbench) for the action surface.
- The heuristic token list is a starting set; expect to tune it as the user sees real CSVs.
  Keep it in one documented constant so tuning is a one-line change.
