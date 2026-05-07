# TICKET-023 — Price sanity check for EUR-denominated and unsupported-suffix tickers

**Status:** MERGED
**Priority:** P0
**Estimated session length:** 1 – 1.5 hr
**Drafted by:** Claude Code (bug investigation 2026-05-07)
**Implemented by:** _pending_
**Found by:** Vivek — entering €10 or €1000 for SK Hynix in Manage Portfolio accepted without any deviation warning, while the same for APD correctly flags the issue.

---

## Problem

`_render_recording_preview` in `app/ui/pages/manage.py` (lines 132–146) has two gaps in its price sanity check:

### Gap 1 — EUR path skips the check entirely

```python
if currency == Currency.EUR:
    # just shows implied price — no historical cross-check
    return True, None
```

For any EUR-denominated ticker (`.F`, `.DE`, `.AS`, `.MI`, `.PA`), the function displays the implied price-per-share but **never fetches the yfinance historical close to verify it is reasonable**. A user entering €10 for a stock trading at €25 sees no warning. APD (USD) gets a deviation check; RHM.DE (EUR) does not.

### Gap 2 — `.KS` (and other unrecognised exchange suffixes) silently default to USD

`infer_currency_from_ticker("000660.KS")` returns `Currency.USD` because `.KS` is not in `_SUFFIX_TO_CURRENCY` and not in `_UNSUPPORTED_SUFFIXES`. yfinance actually returns KRW prices (~1,654,000) for `000660.KS`, not USD. The deviation check runs but the comparison is nonsensical (EUR vs. KRW-labeled-as-USD). Worse: if the historical fetch for `000660.KS` fails (Korean public holiday, yfinance gap, any non-`PriceUnavailableError` exception), the broad `except Exception: return True, None` at line 201–202 silently swallows the error and the form shows no warning at all.

### Root cause of the silent swallow

```python
except PriceUnavailableError:
    st.warning("⚠ Couldn't fetch the historical price…")
    return False, None
except Exception:
    return True, None  # ← BUG: any other exception pretends check passed
```

The `except Exception: return True, None` catches real errors (AttributeError from yfinance, ValueError from Decimal conversion, etc.) and tells the caller "price is available, no deviation" — which is the opposite of what we want on an error.

---

## Acceptance criteria

### Fix 1 — Add historical price check for EUR-denominated tickers

In `_render_recording_preview`, when `currency == Currency.EUR`:
- Attempt `get_historical_close(ticker, trade_date)` — this returns a EUR-denominated `Money` for European exchange tickers.
- If successful: compute `implied_per_share = (eur_total - fees_eur) / shares`. Compute `deviation_pct = abs(implied_per_share - hist.amount) / hist.amount × 100`. If `deviation_pct > 2`: show the same `⚠` warning shown for foreign-currency tickers (and set `deviation_pct` in the return value so the button label changes to "Record anyway" for >= 10%). If within 2%: show `✓ within X% of market close`.
- If `PriceUnavailableError`: show "Couldn't fetch historical price for {ticker}" (same as foreign-currency path). No deviation note, form still usable.
- The simple EUR breakdown (implied price-per-share, EUR total) is still shown above the deviation check.
- **No FX conversion needed** — both the user's total and the historical close are in EUR.

### Fix 2 — Make the broad `except Exception` surface the error rather than hide it

Replace:
```python
except Exception:
    return True, None
```
With:
```python
except Exception:
    logging.warning("_render_recording_preview unexpected error for %s", ticker, exc_info=True)
    return True, None
```
The `return True, None` can stay (it's the safest fallback for the UI — the user can still submit) but the error must be logged at WARNING so we can diagnose future failures.

### Fix 3 — Add `.KS` (and at minimum `.TW`, `.BK`) to `_UNSUPPORTED_SUFFIXES` in `tickers.py`

Korean (KRW), Taiwanese (TWD), and Thai (THB) stocks have suffixes that are currently unrecognised and default silently to USD. The correct behaviour for an unrecognised-but-known-foreign suffix is to raise `UnsupportedTickerError`, not default to USD.

Add to `_UNSUPPORTED_SUFFIXES`:
```python
_UNSUPPORTED_SUFFIXES: tuple[str, ...] = (".HK", ".KS", ".KQ", ".TW", ".TWO", ".BK")
```

This means the resolver will return `None` for these tickers in `_build_match` (they are filtered silently, per the protocol contract). The user then uses "use as-typed" but knows the ticker is not fully supported. A future ticket can add proper KRW/TWD/THB support.

**Note:** `.KS` suffix for Korean stocks (KRW) currently wrongly returns `Currency.USD`. Fixing it to raise `UnsupportedTickerError` makes the currency logic correct and consistent.

### Tests

- `tests/unit/domain/test_tickers.py` — add test cases that `infer_currency_from_ticker("000660.KS")`, `infer_currency_from_ticker("005930.KS")`, `infer_currency_from_ticker("2330.TW")` all raise `UnsupportedTickerError`.
- `tests/unit/ui/test_manage_form_pipeline.py` (or new file) — unit test `_render_recording_preview` with EUR currency and a fake price provider that returns a EUR close. Assert: deviation warning is generated when implied price is > 2% off.
- `tests/unit/ui/test_manage_form_pipeline.py` — test that when the price provider raises a generic `Exception` (not `PriceUnavailableError`), `_render_recording_preview` returns `(True, None)` and does NOT raise.

### Lints / quality

- `pytest && ruff check . && mypy app/ && lint-imports` — all green.

---

## Files likely touched

```
app/domain/tickers.py                   ← add .KS, .KQ, .TW, .TWO, .BK to _UNSUPPORTED_SUFFIXES
app/ui/pages/manage.py                  ← fix EUR path in _render_recording_preview; fix broad except
tests/unit/domain/test_tickers.py       ← new cases for .KS etc.
tests/unit/ui/test_manage_form_pipeline.py  ← EUR price check tests
```

## Out of scope

- Adding KRW, TWD, THB to the Currency enum (separate ADR + ticket).
- Adding EUR price-check to the Edit form's inline preview (same function, same fix, but verify it's called correctly).
- Any changes to the sell simulator.
