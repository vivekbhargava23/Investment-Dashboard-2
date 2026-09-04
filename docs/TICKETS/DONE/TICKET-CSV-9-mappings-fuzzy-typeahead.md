# TICKET-CSV-9 — Fuzzy ticker typeahead in Mappings page

\*\*Status:\*\* IN_PROGRESS
**Priority:** MEDIUM
**Estimated session length:** 30 min
**Drafted by:** Vivek + Claude Chat (2026-05-16)
**Implemented by:** TBD
**Milestone:** Investment Panel

---

## Problem

The Mappings page (`app/ui/pages/mappings.py`) uses plain `st.text_input` for both the unmapped-row "assign ticker" field and the edit-row "new ticker" field. The user has to type the exact yfinance symbol from memory (`HY9H.F`, `IUES.DE`, `XNAS.DE`, `5631.T`, etc.). For uncommon listings — German GDRs, Tokyo-listed names, suffixed ETF wrappers — guessing the right suffix is painful.

The Manage Portfolio page already solves this with `render_ticker_searchbox` (`app/ui/components/ticker_searchbox.py`), which calls `resolver.resolve(query)` for fuzzy text search and displays candidates as `"SYMBOL — Company name (Exchange, Currency)"`. Typing `"sk hynix"` in Manage Portfolio surfaces all SK Hynix listings across Frankfurt, Düsseldorf, Hamburg, and Korea — verified working as of 2026-05-16.

## Solution

Replace the two text_input ticker fields in `mappings.py` with `render_ticker_searchbox`. The user gets a name-based typeahead just like Manage Portfolio. Behaviour after selection is unchanged from CSV-8: save the mapping, run `rewrite_ticker_for_isin`, show toast.

### Decisions already made

- Same searchbox component reused — no new component built.
- `TickerMatch` returned by searchbox provides `.symbol` (use as the new ticker), `.name`, `.exchange`, `.currency`. The "hint" branch in the existing save handler (which shows resolver-derived metadata in the toast) becomes redundant since the user has already seen the metadata in the picker, but **keep the hint logic** so behaviour stays consistent if the searchbox is bypassed by an Enter-key shortcut returning a raw string. Don't refactor the hint flow in this ticket.
- Currency check / yfinance reachability is **not** added here. The searchbox already filters to candidates the resolver knows about; that's good enough. Tightening to "ticker must return current price" is a separate concern.

---

## Execution

### Step 1: Swap the unmapped-section input

**File:** `app/ui/pages/mappings.py`, `_render_unmapped_section`.

Current:
```python
ticker_input = st.text_input(
    "Ticker",
    key=ticker_key,
    placeholder="e.g. NVDA, 5631.T",
    label_visibility="collapsed",
)
```

Replace with `render_ticker_searchbox`:
```python
from app.ui.components.ticker_searchbox import render_ticker_searchbox
from app.ui.wiring import get_ticker_resolver  # already imported

selected_match = render_ticker_searchbox(
    key=f"mappings_searchbox_unmapped_{isin}",
    resolver=get_ticker_resolver(),
    placeholder=f"Search for {mapping.name or 'this security'}…",
)
```

In the Save button handler, derive the ticker from `selected_match.symbol` instead of `ticker_input.strip().upper()`. If `selected_match is None`, show an error toast `"Pick a ticker from the search results before saving."` and rerun without saving.

When `selected_match` is present, the existing `_validate_ticker` + `_try_resolve` + `_save_mapping` flow runs as today. `_try_resolve` will succeed because the searchbox only returns symbols the resolver knows; the toast will follow the `hint` branch.

### Step 2: Swap the edit-row input

**File:** same, `_render_edit_row`.

Current:
```python
new_ticker = st.text_input(
    "New ticker",
    value=st.session_state.mappings_edit_ticker_value,
    key=f"mappings_edit_input_{isin}",
    label_visibility="collapsed",
)
```

Replace with `render_ticker_searchbox`. Pre-seed it with the current ticker by passing a `default_match`:

```python
# Build a default_match from the current mapping if possible
default_match: TickerMatch | None = None
if mapping.ticker:
    try:
        default_match = get_ticker_resolver().lookup(mapping.ticker)
    except Exception:
        default_match = None

selected_match = render_ticker_searchbox(
    key=f"mappings_edit_searchbox_{isin}",
    resolver=get_ticker_resolver(),
    placeholder="Search by ticker or name…",
    default_match=default_match,
)
```

Save handler: if `selected_match is None` (user cleared without choosing), show error and don't save. Otherwise use `selected_match.symbol` as the new ticker. `rewrite_ticker_for_isin` call (from CSV-8) stays unchanged.

The `mappings_edit_ticker_value` session state key can be removed (it was only used to seed the text_input). Remove its key from `_STATE_DEFAULTS` and any references.

### Step 3: Imports

Add to imports in `mappings.py`:
```python
from app.ports.ticker_resolver import TickerMatch
from app.ui.components.ticker_searchbox import render_ticker_searchbox
```

(`get_ticker_resolver` is already imported.)

### Step 4: Tests

Update `tests/unit/ui/test_mappings_page.py`:
- Existing text_input-based tests need to switch to mocking `render_ticker_searchbox` to return a `TickerMatch` (success path) or `None` (cleared-without-selection path).
- New test: edit-row pre-seeds the searchbox with a `default_match` built from the current mapping ticker. Mock `get_ticker_resolver().lookup` to verify it's called with the current ticker.
- New test: save with `selected_match=None` shows error toast, does not call `_save_mapping` or `rewrite_ticker_for_isin`.
- The `mappings_edit_ticker_value` session key removal: confirm no test relies on its default.

---

## Acceptance criteria

- [ ] Both ticker input fields in Mappings use `render_ticker_searchbox`.
- [ ] Unmapped section: typing the security name (e.g. "sk hynix") surfaces yfinance candidates; picking one + Save uses the picked symbol.
- [ ] Edit row: opens pre-seeded with the current ticker (if resolvable); changing selection + Save uses the new symbol; `rewrite_ticker_for_isin` runs as in CSV-8.
- [ ] `selected_match is None` blocks save with a clear error toast.
- [ ] `mappings_edit_ticker_value` session state key is removed.
- [ ] All tests pass; ruff / mypy / lint-imports clean.

### Manual smoke

- Mappings page → an unmapped ISIN (e.g. one of the crypto ETPs) → type "polygon" → pick the right symbol → Save. Mapping appears in the mapped section.
- Mappings page → edit a mapped ISIN → searchbox shows current symbol pre-filled → change selection → Save → success toast names the new symbol.

---

## Out of scope

- Tightening "ticker must return a current price" validation.
- Replacing the resolver entirely (current implementation is yfinance-backed; switching providers is a separate decision).

---

## Notes / assumptions

- Assumes CSV-8 has merged. CSV-9's edit-save handler relies on the `rewrite_ticker_for_isin` call introduced in CSV-8.
- Assumes `render_ticker_searchbox` works inside a `st.columns` cell. It does on the Manage page; the Mappings page also uses columns. If column width causes layout issues, widen the input column from `1.5` to `2.5` rather than refactoring the component.
- Assumes `streamlit_searchbox` widget keys are unique per page — the keying convention used here (`mappings_searchbox_unmapped_{isin}` and `mappings_edit_searchbox_{isin}`) follows that rule.
