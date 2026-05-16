# TICKET-CSV-10 — Live Overview: real names, drop CCY column, honest price hover

**Status:** QUEUED
**Priority:** MEDIUM
**Estimated session length:** 1 hr
**Drafted by:** Vivek + Claude Chat (2026-05-16)
**Implemented by:** TBD
**Milestone:** Investment Panel

---

## Problem

Three cosmetic-but-misleading issues on the Live Overview positions table (`app/ui/pages/overview.py`):

### 1. Wrong company names

The Name column reads from a hardcoded dict `_PLACEHOLDER_NAME` near the top of `overview.py` that covers ~12 tickers. Any ticker not in the dict shows the ticker as its own name. Visible on the current Overview: `QDVE` shows "QDVE", `ANAU` shows "ANAU", `5631.T` shows "Japan Steel Works" only because it happens to be in the dict, while ETN's `_PLACEHOLDER_NAME["ETN"]` is "Eaton" but for the wrong reason — the dict happens to be right by accident.

`isin_map.json` already contains the correct human-readable name for every ISIN (e.g. `"name": "iShares S&P 500 Information Technology Sector (Acc)"` for QDVE). After CSV-8 ships, `Transaction.isin` will be populated for every Scalable-CSV-sourced position, making name lookup trivial: `isin_map.entries[tx.isin].name`.

### 2. Misleading CCY column

The CCY column reads `p.position.open_lots[0].cost_per_share_native.currency.value`. Since CSV-7, every CSV-imported lot has `cost_per_share_native.currency == EUR` (face-value EUR storage). So every row shows "EUR" regardless of where the security actually trades. That's not informative — it's the same value for every row.

### 3. Price column is unitless and lying by omission

The Price column shows `f"{float(p.live_price_native.amount):.2f}"` with no currency label. For NVDA, yfinance returns ~225 USD; the cell shows "225.32" under a header that says "Price" in a row labelled "EUR". The number is the USD price; the row says EUR. This is the source of "the prices look like USD" Vivek noticed.

The downstream Value (€) and Gain (€) columns are correctly EUR-converted via `valuation.py` — that path is fine and is not touched by this ticket.

## Solution

1. **Name column**: resolve name via `Transaction.isin → isin_map.json`. Fall back to ticker for manual transactions where `isin is None`.
2. **CCY column**: remove it entirely.
3. **Price column**: keep the displayed number as native (`live_price_native.amount`), but add a tooltip on hover showing native currency and the EUR-converted per-share price. Example tooltip text: `"USD 225.32 · €198.45 per share"`. EUR-native rows just show `"EUR 1120.00"`.

### Decisions already made

- Names come from `isin_map.json`, not from the CSV's Description column or any field on Transaction. Reason: name is metadata that may want to be edited by the user later (e.g. shortening "iShares S&P 500 Information Technology Sector (Acc)" to "iShares S&P 500 IT"); centralising it in `isin_map.json` keeps it editable.
- Adding a name field to `Transaction` is **not** the right move. Names belong with ISINs, not lots.
- Manual transactions without ISIN show the ticker as the name. Acceptable for now.
- The CCY column goes away. No replacement column. The CCY information moves into the Price hover tooltip.
- The Price column continues to show **native** price (not EUR-converted). Reason: switching to EUR-per-share would lose information without gaining anything — Value (€) and Gain (€) are already EUR. The hover gives the EUR equivalent for spot-checks.
- Hover implementation: use the HTML `title` attribute on the Price `<td>`. Simple, works everywhere, no JS needed. Match the existing pattern from the long-name hover in `_build_positions_table_html` (`<span title="{name}">…</span>`).

---

## Execution

### Step 1: Name resolution helper

**File:** `app/ui/pages/overview.py`

Delete `_PLACEHOLDER_NAME` at top of file.

Add a small helper near `_build_positions_table_html`:

```python
from app.ui.wiring import get_isin_map_repo  # add to imports

def _resolve_name_for_position(p: LivePosition, isin_map_entries: dict[str, IsinMapping]) -> str:
    """Return the display name for a position. Looks up via ISIN on the first open lot's
    originating transaction. Falls back to ticker if ISIN missing or not in map."""
    # Get an ISIN from any transaction backing this position. All lots for one ticker
    # should share the same ISIN after CSV-8; pick the first.
    ticker = p.position.ticker
    isin: str | None = None
    for lot in p.position.open_lots:
        # OpenLot does not currently carry ISIN — it carries the originating Transaction's
        # ticker. We need access to the source transactions. See "Notes / assumptions" for
        # the correct lookup path; agent should verify the cleanest way to plumb ISIN from
        # transaction → position → lot.
        if hasattr(lot, "isin") and lot.isin:
            isin = lot.isin
            break
    if isin and isin in isin_map_entries:
        return isin_map_entries[isin].name or ticker
    return ticker
```

**Important caveat:** I have not verified that `OpenLot` carries ISIN. It may not. The agent's first task on this ticket is to **read `app/domain/positions.py` and `app/domain/fifo.py`** to determine the correct path from a `LivePosition` back to its source ISIN. Three plausible paths:
1. `OpenLot` already has a reference to its source Transaction → use `lot.source_tx.isin`.
2. `OpenLot` has a `ticker` only → look up ISIN via the **inverse** isin_map (build `{ticker: isin}` from mapped entries, same as the CSV-8 migration does). Limitation: this fails for unmapped or stale tickers, falling back to ticker.
3. Add `isin` to `OpenLot` in this ticket (small refactor, propagates from Transaction).

**Pick (2) unless (1) turns out to already exist.** (2) is zero-risk and uses the same backward-lookup pattern as the CSV-8 migration. (3) is a refactor and should be a separate ticket if needed.

In `_build_positions_table_html`, replace:
```python
name = _PLACEHOLDER_NAME.get(ticker, ticker)
```
with:
```python
name = name_lookup.get(ticker, ticker)
```
where `name_lookup` is a pre-built `{ticker: name}` dict passed in as an argument, built once in `render()` from `get_isin_map_repo().load()` (build ticker→name via `{m.ticker: m.name for m in doc.entries.values() if m.status == "mapped" and m.ticker}`).

### Step 2: Drop CCY column

In `_build_positions_table_html`:
- Remove the `<th>` for `CCY` in the header.
- Remove the `<td>` for `ccy` in each row's tbody construction.
- Remove the local `ccy = "EUR"` lines and the `if len(p.position.open_lots) > 0:` block that derives it.

### Step 3: Price hover tooltip

In `_build_positions_table_html`, in the row construction:

Current:
```python
price = "—" if is_stale or p.live_price_native is None else f"{float(p.live_price_native.amount):.2f}"
...
f'<td class="font-mono text-right">{price}</td>'
```

Change to:
```python
if is_stale or p.live_price_native is None:
    price_cell = '<td class="font-mono text-right">—</td>'
else:
    native_ccy = p.live_price_native.currency.value
    native_amt = float(p.live_price_native.amount)
    native_str = f"{native_ccy} {native_amt:.2f}"
    # EUR-equivalent per share (Value / shares), if available
    if p.live_value_eur is not None and p.position.open_shares > 0:
        eur_per_share = float(p.live_value_eur.amount) / float(p.position.open_shares)
        tooltip = f"{native_str} · €{eur_per_share:.2f} per share"
    else:
        tooltip = native_str
    price_cell = (
        f'<td class="font-mono text-right" title="{tooltip}">'
        f'{native_amt:.2f}'
        f'</td>'
    )
```

For EUR-native rows the tooltip just reads `"EUR 1120.00"` which is correct (the per-share EUR is the same as the displayed number).

### Step 4: Tests

Extend `tests/unit/ui/test_overview.py` (or wherever overview's tests live — check):
- `_build_positions_table_html` no longer emits a `CCY` `<th>` or per-row CCY cell.
- Name resolution: build a `LivePosition` whose underlying transaction has `isin=US67066G1040`. Pass a `name_lookup` with `NVDA: "NVIDIA Corp"`. Assert the rendered HTML contains `"NVIDIA Corp"`.
- Name fallback: position with no ISIN-path resolution → renders ticker as name.
- Price tooltip: USD-priced position → asserted `title="USD 225.32 · €..."` substring present. EUR-priced position → `title="EUR ..."`. Stale position → no `title` attribute (or empty), and cell renders `—`.

### Step 5: Clean up dead placeholders

`_PLACEHOLDER_THESIS_STATUS`, `_PLACEHOLDER_HORIZON`, `_PLACEHOLDER_NAME` are all hardcoded dicts at the top of `overview.py`. This ticket removes `_PLACEHOLDER_NAME`. **Leave the other two alone** — they drive UI columns that are out of scope here (Thesis, Horizon). File a separate ticket if you want those cleaned up too.

---

## Acceptance criteria

- [ ] `_PLACEHOLDER_NAME` is removed from `overview.py`.
- [ ] Name column on Live Overview resolves via ISIN → `isin_map.json` for CSV-sourced positions.
- [ ] Manual transactions or unresolvable ISINs fall back to ticker for name; no row shows an empty Name cell.
- [ ] CCY column is removed (header and all body cells).
- [ ] Price cell has a `title=` tooltip on hover showing `"<NATIVE_CCY> <native_price>"`; if EUR-equivalent is computable, also `"· €<eur_per_share> per share"`.
- [ ] Stale rows still render `—` and no tooltip.
- [ ] All existing overview tests still pass after column removal (likely needs test updates for column count assertions).
- [ ] ruff / mypy / lint-imports clean.

### Manual smoke

- Open Live Overview after merge.
- Verify: QDVE row shows "iShares S&P 500 Information Technology Sector (Acc)" (or the name as stored in `isin_map.json`).
- Verify: NVDA row's Price cell shows the native (USD) number; hovering shows `"USD 225.32 · €202.18 per share"` or similar.
- Verify: RHM.DE row's Price cell hovers shows `"EUR 1120.00"`.
- Verify: CCY column is gone.

---

## Out of scope

- Removing `_PLACEHOLDER_THESIS_STATUS` and `_PLACEHOLDER_HORIZON` — separate concerns (these drive features not yet wired to real data).
- Editing names from the UI (`isin_map.json` name field is editable only by hand-editing the file or via the Mappings page if such functionality is later added).
- Currency conversion of historical lots — already correct, not touched here.

---

## Notes / assumptions

- Depends on CSV-8 being merged. Without `Transaction.isin`, the name lookup path doesn't work — the agent would need to fall back to a ticker→name map built from `isin_map.json`'s mapped entries, which has the same effective behaviour but reverses the lookup direction. Either way works. Pick the direction that fits the actual code shape.
- Assumes `OpenLot` does not currently carry ISIN. If it does, use it directly. The agent should read `app/domain/positions.py` and `app/domain/fifo.py` first to confirm. **Adding ISIN to OpenLot is out of scope for this ticket** — file a follow-up if it becomes necessary.
- The `title=` HTML attribute is the simplest cross-browser tooltip. If a richer Streamlit-native tooltip is preferred (e.g. via a custom component), file separately. Don't gold-plate this ticket.
- The hardcoded placeholders for Thesis and Horizon are noted but left alone. Vivek explicitly scoped this ticket to names + CCY + Price; the agent should resist the urge to "while I'm here" the other placeholders.
