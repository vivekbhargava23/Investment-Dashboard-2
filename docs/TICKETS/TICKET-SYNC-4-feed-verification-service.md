# TICKET-SYNC-4 — Feed verification: does the mapped ticker price what Scalable charged?

**Priority:** HIGH
**Status:** IN_PROGRESS
**Milestone:** Investment Panel
**Recommended model:** Sonnet — pure domain function + one service over existing ports, fully specified.
**Estimated session length:** 1.5 hr
**Drafted by:** Vivek + Claude (Cowork session 2026-09-03)
**Depends on:** TICKET-SYNC-1.
**Can run independently of:** TICKET-SYNC-2 and TICKET-SYNC-3.

> **After this ticket merges:** for every ISIN with a mapped ticker the app can say `ok`, `suspicious`, `no_feed` or `unchecked`, with the numbers behind it, by comparing the EUR trade prices in the CSV rows with the feed's historical close. This is what tells the user *when and where* a ticker is wrong.

## Rules (fixed, from docs/DESIGN/SYNC-TAB.md)
- Use the last 3 transactions (by `trade_date`, then `id`) per ISIN with `source == "scalable_csv"`.
- For each: `close = price_provider.get_historical_close(ticker, trade_date)` (Money, native
  currency). If `close.currency != EUR`: `rate = fx_provider.get_historical_rate(close.currency, Currency.EUR, trade_date)`;
  `close_eur = close.amount * rate`. Deviation % = `abs(tx.price_native.amount − close_eur) / close_eur × 100`.
- `PriceUnavailableError` or `FxRateUnavailableError` on a trade → that trade is skipped.
- Central value: median for 3 comparable trades, arithmetic mean for 2, the value itself for 1.
- Status: no mapped ticker → `unchecked`; zero comparable trades → `no_feed`; central value
  ≤ 15 → `ok`; > 15 → `suspicious`.
- This is a **warning, not proof of identity**. `detail` always carries both averages so the
  user can judge; a split may trigger a false warning and that is accepted.

## Execution — one commit per step

### Step 1 — domain model + pure evaluation
New file `app/domain/feed_check.py` (no I/O, no datetime.now):
```python
class FeedCheck(BaseModel):
    model_config = ConfigDict(frozen=True)
    isin: str
    ticker: str | None
    status: Literal["ok", "suspicious", "no_feed", "unchecked"]
    compared: int
    median_deviation_pct: Decimal | None
    avg_trade_price_eur: Decimal | None
    avg_close_eur: Decimal | None
    detail: str

SUSPICIOUS_THRESHOLD_PCT = Decimal("15")

def evaluate_deviations(isin, ticker, pairs: list[tuple[Decimal, Decimal]]) -> FeedCheck:
    """pairs = (trade_price_eur, close_eur). Applies the status rules above; detail is a
    one-sentence human string, e.g. 'your trades averaged €20.44, AY7.F closed at €0.20 (median 9900% off)'."""
```
Tests `tests/unit/domain/test_feed_check.py`: ok (3 pairs within 2 %), suspicious (10×),
no_feed (empty pairs, ticker set), unchecked (ticker None), two pairs use the mean (0 % and
40 % → 20 % → suspicious), one pair uses itself.

### Step 2 — service
New file `app/services/feed_check.py`:
```python
def check_feeds(transactions, isin_doc, price_provider, fx_provider, *, max_trades: int = 3) -> dict[str, FeedCheck]
```
Groups scalable transactions by `isin`, resolves ticker from `isin_doc.entries[isin]`
(status `mapped` only), fetches closes as per the rules, calls `evaluate_deviations`.
Returns one entry per ISIN present in `transactions` (including `unchecked`).

Tests `tests/unit/services/test_feed_check.py` with `tests/fakes/price_feed.py` and
`tests/fakes/fx_feed.py`: EUR ok case; USD case with conversion; one of three trades raising
`PriceUnavailableError` → compared == 2; all raising → `no_feed`; unmapped ISIN → `unchecked`.

### Step 3 — gate, commit, session log, PR. No UI in this ticket.

## Acceptance criteria
- [ ] Domain function has no imports outside stdlib/pydantic/app.domain.
- [ ] Service takes ports as parameters (no wiring imports).
- [ ] Tests listed above pass; gate clean.

## Out of scope
Rendering; caching (SYNC-6B wraps the call in `st.cache_data`).
