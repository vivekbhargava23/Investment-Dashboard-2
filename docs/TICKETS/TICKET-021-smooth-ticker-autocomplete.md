# TICKET-021 — Smooth ticker autocomplete on Manage Portfolio

**Status:** IN_REVIEW
**Priority:** P1
**Estimated session length:** 1.5 – 2 hr
**Drafted by:** Vivek + Claude (chat 2026-05-06)
**Implemented by:** _pending_
**Depends on:** TICKETs 008c (Currency enum + `infer_currency_from_ticker`), 009-revised (Manage Portfolio form — this ticket modifies its ticker field), **020 (TickerResolver port + yfinance adapter)**

> **After this ticket merges, typing a ticker into Manage Portfolio's Add Transaction form feels instantaneous.** The user types "AP" and a dropdown appears with `APD — Air Products and Chemicals (NYSE, USD)` in under 100ms for cached prefixes, under 800ms for first-time queries. Every successful resolve is persisted so the second time the user types the same prefix, the result is local.

---

## Problem

The current Manage Portfolio form (TICKET-009-revised) calls `TickerResolver.resolve(query)` on submit-blur. The resolver itself is fine — it caches in-memory with a 1 hour TTL — but two real-world UX problems remain:

1. **The first time a user types a ticker after starting Streamlit, every resolve is a network round-trip.** yfinance's search endpoint takes 400–900ms in normal conditions. The user types "APD", presses Enter, and waits. The wait is short enough to feel "slow but working," not short enough to feel responsive.

2. **The cache is in-memory only and dies with the process.** Restart Streamlit → cache gone → first-time-each-session penalty repeats. Vivek restarts the app frequently while iterating on the dashboard. Every restart costs ~1s per ticker re-typed.

3. **There is no incremental autocomplete.** The user types "AP" and nothing happens; they type "APD", press Enter, and *then* something happens. Modern brokers (Trading 212, Scalable's own search) drop suggestions as the user types the second character. The current form feels dated by comparison.

The fix is twofold: a **disk-backed cache** that survives restarts, and an **incremental dropdown** that surfaces suggestions as the user types.

---

## Architectural decisions implemented by this ticket

These were decided in the chat session 2026-05-06.

### 1. Disk cache lives at `data/ticker_cache.json` (gitignored), keyed by normalised query

The cache stores both `resolve(query)` results (multi-match) and `lookup(symbol)` results (single match). Schema: `{"resolve:apd": {"results": [...], "fetched_at": "2026-05-06T10:30:00Z"}, "lookup:NVDA": {"result": {...}, "fetched_at": "..."}}`. TTL is 30 days (these are stable mappings; ticker symbols don't change).

Why JSON, not SQLite: same architectural rationale as `portfolio.json` and `tax_profile.json` (ADR-002). The cache is small (under 1 MB even with thousands of entries), human-readable for debugging, atomically writable.

Why `data/` not `.cache/`: keeps all dashboard state in one directory. The user already knows `data/` exists and is gitignored. Adding a second hidden directory adds cognitive load. The cache is functionally indistinguishable from other dashboard state from the user's perspective — wipe `data/` and you start fresh.

### 2. Disk cache is a wrapper around the existing TickerResolver Protocol, not a new port

The existing `TickerResolver` Protocol (TICKET-020) stays unchanged. We add a **decorating adapter** in `app/adapters/ticker_resolver_cached.py`: `CachedTickerResolver(inner: TickerResolver, cache_path: Path)`. It implements `TickerResolver` itself, delegates to `inner` on cache misses, persists hits to disk.

Why decorate, not rewrite: the yfinance adapter is the single source of truth for *what data exists*. The disk cache is the source of truth for *what data we've already paid for*. These are orthogonal concerns. A decorator makes them composable — the same pattern can later wrap a different inner provider (OpenFIGI, broker API) without changing the disk-cache logic.

Wiring (`app/ui/wiring.py`) becomes:
```python
def get_ticker_resolver() -> TickerResolver:
    inner = _yfinance_adapter()  # already has 1h in-memory cache
    return CachedTickerResolver(inner=inner, cache_path=settings.ticker_cache_json_path)
```

### 3. Incremental autocomplete uses `streamlit-searchbox`

`st.text_input` does not support typeahead suggestions. Two options were considered:

- Build a custom Streamlit component (HTML + JS + Python bridge). Big undertaking. Rejected.
- Use `streamlit-searchbox` ([github.com/m-wrzr/streamlit-searchbox](https://github.com/m-wrzr/streamlit-searchbox)). Maintained, ~40 lines to integrate, exactly the right widget. **Chosen.**

`streamlit-searchbox` calls a Python callback on every keystroke (with debouncing). The callback returns a list of (label, value) tuples. We pass `lambda q: [(format_match(m), m) for m in resolver.resolve(q, limit=8)]` and the disk cache makes this fast.

Why not roll our own JavaScript: too much risk and maintenance. The library is small, well-tested, and has been stable for two years. Using it is a 1-line install + 1-line render.

### 4. Disk cache writes are best-effort, not blocking

If `data/ticker_cache.json` is locked / disk full / permissions fail, the write fails silently (logged via `logging.warning`, not raised). The user still gets the resolve result; only the persistence layer is degraded. The next attempt will try again. **This is a hard rule** — the cache is an optimisation, never a correctness boundary.

Atomic writes use the existing pattern from `JsonTransactionRepository` (write to `.tmp` file + `os.replace`). No corruption risk on partial writes.

### 5. The cache is invalidated by `clear_cache()` on the resolver, plus a TTL

`CachedTickerResolver.clear_cache()` clears both the in-memory inner cache *and* the disk cache (the JSON file is overwritten with `{}`). This is reachable from the existing Refresh button. TTL: any cache entry older than 30 days is treated as a miss on read (and overwritten on the subsequent network fetch).

Why a TTL at all: yfinance occasionally fixes metadata bugs (e.g., a ticker's listed currency changes). Letting the cache update once a month keeps us self-healing without the user having to think about it.

### 6. The form's submit pipeline is unchanged

The autocomplete dropdown is a UX layer on top of the existing resolve. When the user picks a match from the dropdown, the form already has a `TickerMatch` object (TICKET-020's type) — same downstream pipeline as today. The "use as-typed" fallback (TICKET-009-revised, section 3) also works unchanged: if no match is selected, the existing fallback path runs.

---

## Acceptance criteria

### `app/adapters/ticker_resolver_cached.py` — new decorating adapter

- [ ] Module-level imports: `json`, `logging`, `os`, `tempfile`, `datetime`, `pathlib.Path`, `app.ports.ticker_resolver.{TickerResolver, TickerMatch}`. No `yfinance` import (decorator is provider-agnostic).

- [ ] Constants:
  ```python
  CACHE_VERSION = 1
  CACHE_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days
  ```

- [ ] Class `CachedTickerResolver`:
  ```python
  class CachedTickerResolver:
      """Decorator that persists TickerResolver results to disk.

      Implements the TickerResolver Protocol by delegating to an inner provider
      and caching results to a JSON file. Cache hits avoid the network entirely.
      Cache misses fetch from the inner provider, persist, then return.
      """

      def __init__(self, inner: TickerResolver, cache_path: Path) -> None: ...
      def resolve(self, query: str, limit: int = 10) -> list[TickerMatch]: ...
      def lookup(self, symbol: str) -> TickerMatch | None: ...
      def clear_cache(self) -> None: ...
  ```

- [ ] On `__init__`:
  - Store `inner` and `cache_path`. Do NOT load the file at init time (defer to first call). The Streamlit app's startup path is performance-sensitive.

- [ ] On `resolve(query, limit)`:
  1. Normalise: `query = query.strip().upper()`. Empty query → return `[]` immediately (do not touch cache).
  2. Compute cache key: `key = f"resolve:{query.lower()}"`.
  3. Read cache (lazy-loaded into a private `self._cache: dict | None` field on first access). If file does not exist → `self._cache = {}`. If file exists but is malformed → log warning, `self._cache = {}`.
  4. If `key` in cache and entry's `fetched_at` is within TTL → deserialise the stored `list[TickerMatch]`, return up to `limit` items.
  5. On miss: call `self.inner.resolve(query, limit)`. Get `matches`.
  6. Persist: update `self._cache[key] = {"results": [m.model_dump(mode="json") for m in matches], "fetched_at": datetime.now(timezone.utc).isoformat()}`. Call `self._write_cache()` (best-effort; see acceptance below).
  7. Return `matches`.

- [ ] On `lookup(symbol)`:
  1. Normalise: `symbol = symbol.strip().upper()`. Empty → return `None`.
  2. Cache key: `key = f"lookup:{symbol}"`.
  3. Same read/TTL logic as resolve. On hit: deserialise the stored `TickerMatch` dict (or `None`) and return.
  4. On miss: call `self.inner.lookup(symbol)`. Persist the result (including `None` — negative caching is correct for unknown symbols; user typo doesn't trigger repeated network calls).
  5. Return the result.

- [ ] On `clear_cache()`:
  1. Call `self.inner.clear_cache()`.
  2. Set `self._cache = {}`.
  3. Atomically overwrite the cache file with `{"_version": CACHE_VERSION, "entries": {}}`.

- [ ] Private helper `_load_cache(self) -> None`:
  - If `self._cache is not None` → no-op.
  - If file does not exist → `self._cache = {}`. Don't error; it's normal.
  - Read JSON. If top-level `_version` does not match `CACHE_VERSION` → log info "ticker cache version mismatch, ignoring", `self._cache = {}`. (Future-proofs against schema changes.)
  - Otherwise `self._cache = data["entries"]`.
  - On any `JSONDecodeError` or `OSError` → log warning, `self._cache = {}`.

- [ ] Private helper `_write_cache(self) -> None`:
  - Try: write `{"_version": CACHE_VERSION, "entries": self._cache}` to a temp file in the same directory, then `os.replace` to the target path.
  - On any exception → `logging.warning("Ticker cache write failed: %s", exc)`. Do not raise. Do not clear `self._cache` (in-memory state is still correct).

- [ ] **TTL enforcement is on read, not write:** entries are kept on disk past TTL but treated as misses. This means the cache file grows unbounded. **Acceptable for v1** — even 10,000 entries is well under 1 MB. Compaction (drop expired entries) is deferred to a future ticket; add a `# TODO(TICKET-021b): periodic compaction` comment.

### `app/ports/ticker_resolver.py` — minor update

- [ ] `TickerMatch.model_dump(mode="json")` must serialise cleanly (Money fields, Currency enum). Verify the existing model already serialises round-trip — if not, add a small validator.
  - **Round-trip test in `tests/unit/ports/test_ticker_resolver_protocol.py`**: `m = TickerMatch(...); m2 = TickerMatch.model_validate(m.model_dump(mode="json")); assert m == m2`. This catches any future field that adds a non-JSON-safe type.

### `app/config.py` — new setting

- [ ] Add `ticker_cache_json_path: Path = Path("data/ticker_cache.json")` to the `Settings` class. Allow override via `TICKER_CACHE_JSON_PATH` env var. Document in `.env.example`.

### `app/ui/wiring.py` — wrap the resolver

- [ ] Replace direct `_yfinance_adapter()` return for `get_ticker_resolver()` with a wrapped version:
  ```python
  @lru_cache(maxsize=1)
  def get_ticker_resolver() -> TickerResolver:
      from app.adapters.ticker_resolver_cached import CachedTickerResolver
      inner = _yfinance_adapter()
      return CachedTickerResolver(inner=inner, cache_path=settings.ticker_cache_json_path)
  ```
- [ ] `_yfinance_adapter()` itself remains the inner; it still satisfies `PriceProvider` and `FxProvider` Protocols and is returned directly from `get_price_provider()` / `get_fx_provider()`. Only the resolver is decorated.

### `pyproject.toml` — add dependency

- [ ] Add `streamlit-searchbox = "^0.1.16"` to runtime dependencies. Pin minor version; the library is small and stable.
- [ ] Run `pip install -e .` and verify import works: `from streamlit_searchbox import st_searchbox`.

### `app/ui/components/ticker_searchbox.py` — new shared component

- [ ] New module wrapping `streamlit-searchbox` with the resolver. Single function:
  ```python
  def render_ticker_searchbox(
      key: str,
      resolver: TickerResolver,
      *,
      placeholder: str = "Type a ticker (e.g. APD, RHM)…",
      default_match: TickerMatch | None = None,
  ) -> TickerMatch | None:
      """Render an autocomplete ticker search field.

      Returns the selected TickerMatch, or None if nothing is selected.
      `key` must be unique per Streamlit page.
      """
      ...
  ```

- [ ] Internal `_search_callback(query: str) -> list[tuple[str, TickerMatch]]`:
  - On empty query → return `[]`.
  - On length 1 → return `[]` (avoid noisy single-letter searches; `streamlit-searchbox` debounces but single chars match too much).
  - On length 2+ → call `resolver.resolve(query, limit=8)`. Format each match as `f"{m.symbol} — {m.name} ({m.exchange}, {m.currency.value})"`. Return list of `(label, match)` tuples.
  - On any exception → log warning, return `[]`. The user typed something the resolver can't handle; better to show no suggestions than to crash the form.

- [ ] Render via `st_searchbox(_search_callback, placeholder=placeholder, key=key, default=default_label)`. The library returns the *value* of the selected tuple (the `TickerMatch` object), or `None` if nothing is selected.

- [ ] Expose `default_match`: when editing an existing transaction, the form already knows the ticker; passing a `default_match` pre-fills the searchbox so the user doesn't have to re-search.

### `app/ui/pages/manage.py` — replace the ticker text input

- [ ] In the Add Transaction form: replace the existing `st.text_input("Ticker")` with `render_ticker_searchbox(key="add_tx_ticker", resolver=resolver)`. The submit handler reads the result and proceeds exactly as today. **The downstream pipeline (TICKET-009-revised) is unchanged.**

- [ ] In the Edit Transaction form: replace likewise, with `default_match=resolver.lookup(tx.ticker)` so the searchbox starts pre-filled with the existing ticker. Editing the ticker requires explicit re-search (consistent with TICKET-009-revised's "ticker is read-only on edit" rule — but if the user wants to change it via re-search, that's fine; the FIFO check still runs).

- [ ] **Fallback for offline / network-down:** the existing "use as-typed" affordance from TICKET-009-revised stays in place. If `streamlit-searchbox` fails to render (import error, JS bridge dead), the fallback is a plain `st.text_input` rendered behind a try/except. Implementation:
  ```python
  try:
      match = render_ticker_searchbox(key="add_tx_ticker", resolver=resolver)
  except Exception:
      logging.warning("Searchbox failed; falling back to text input", exc_info=True)
      raw = st.text_input("Ticker (autocomplete unavailable)", key="add_tx_ticker_fallback")
      match = resolver.lookup(raw) if raw else None
  ```
  This is defensive — the library is mature and unlikely to fail — but the fallback prevents a single library bug from making the form unusable.

### `.gitignore` — add the cache file

- [ ] Add `data/ticker_cache.json` to `.gitignore` (alongside `data/portfolio.json` and `data/tax_profile.json`).

### Tests

#### `tests/unit/adapters/test_ticker_resolver_cached.py` — pure-data tests of the decorator

All tests use `tests/fakes/ticker_resolver.py` (`FakeTickerResolver` from TICKET-020) as the inner. Use `tmp_path` fixture for the cache file. **Zero network access.**

- [ ] **Cache miss → inner called, result persisted:** create `CachedTickerResolver(inner=fake, cache_path=tmp_path / "cache.json")`. Call `resolve("APD")`. Assert: fake's call count = 1, file exists, file's `entries["resolve:apd"]` contains the expected results.
- [ ] **Cache hit → inner NOT called:** prime cache with one call. Call `resolve("APD")` again. Fake's count still = 1.
- [ ] **TTL miss treats fresh-load as miss:** prime cache; manually edit the JSON to set `fetched_at` to 31 days ago. Call again — fake's count = 2.
- [ ] **Negative caching for `lookup`:** call `lookup("XQYZ")` (fake configured to return `None`). Cache file persists `None`. Second call: fake's count still = 1.
- [ ] **`clear_cache` clears both layers:** prime cache; call `clear_cache()`. Inner's `clear_cache` was called. JSON file content is `{"_version": 1, "entries": {}}`. Next `resolve` call fetches anew.
- [ ] **Best-effort write — readonly path doesn't raise:** point `cache_path` at a path that can't be written (e.g., `tmp_path / "ro_dir" / "cache.json"` with the dir set 0o500). Call `resolve("APD")`. Assert: returns the correct result, no exception, `logging.warning` was called.
- [ ] **Malformed cache file → ignored, fresh fetch:** write `{garbage` to the cache path. Call `resolve("APD")`. Assert: returns correct result, file is now valid JSON with one entry.
- [ ] **Wrong cache version → ignored:** write `{"_version": 999, "entries": {"resolve:apd": ...}}`. Call `resolve("APD")`. Inner is called (cache discarded).
- [ ] **Round-trip integrity:** prime cache with all of `Currency` enum values represented (EUR, USD, JPY). Reload `CachedTickerResolver` from a fresh instance pointing at the same file. Calls return identical `TickerMatch` objects (use `==`).
- [ ] **Empty query short-circuit:** call `resolve("")`. Returns `[]`. Inner's count = 0. File not touched.
- [ ] **Concurrent-write safety (basic):** simulate two writes by calling `_write_cache` twice in quick succession with different content. The final file is valid JSON (atomic-replace prevents corruption). Note: this is single-process; multi-process Streamlit isn't a real concern.

#### `tests/unit/ui/test_ticker_searchbox.py` — minimal UI helper test

- [ ] **`_search_callback` short-circuits on empty / single char:** `_search_callback("")` returns `[]`, `_search_callback("A")` returns `[]`, all without calling the resolver (use a counting fake).
- [ ] **`_search_callback` formats labels correctly:** with a fake returning one match `TickerMatch(symbol="APD", name="Air Products", exchange="NYSE", currency=USD, recent_price=None)`, the returned label is exactly `"APD — Air Products (NYSE, USD)"`.
- [ ] **`_search_callback` swallows resolver exceptions:** fake raises `RuntimeError`. Callback returns `[]`, no exception. `logging.warning` called.

(Full searchbox rendering is not unit-tested — it requires a real Streamlit runtime. Manual review checklist below covers it.)

#### `tests/integration/test_ticker_cache_e2e.py` — opt-in network test

- [ ] Marked `@pytest.mark.integration`, skipped without `--run-integration`. Uses real yfinance.
- [ ] **End-to-end cache priming:** create `CachedTickerResolver` pointing at `tmp_path`. Call `resolve("APD")`. Verify result has `currency=USD`. Reload from disk by constructing a *new* `CachedTickerResolver` instance against the same path. Call again. Time the call: assert it returns in under 50ms (disk read + deserialise — well under a network round-trip).

#### Manual review checklist (in PR template)

- [ ] Type "AP" in Add Transaction → dropdown shows APD, APP, APRN, APH within ~1 second.
- [ ] Restart Streamlit. Type "AP" again → dropdown shows the same results within ~150ms (disk cache hit).
- [ ] Pick APD from dropdown → form fills correctly, submit works end-to-end.
- [ ] Edit an existing transaction → ticker searchbox shows the existing ticker pre-filled.
- [ ] Click Refresh button on Live Overview → next ticker query in Manage Portfolio fetches anew (clear_cache propagated).
- [ ] Disconnect network. Type "APD" — fallback path: existing in-memory + disk cache still answers; if cache is empty, the form shows the offline-fallback text input gracefully.
- [ ] Look at `data/ticker_cache.json` after a session — readable, structured, has the expected entries.

### Lints / quality

- [ ] `pytest` — all new tests pass; existing test count goes up by ~14.
- [ ] `ruff check .` — passes.
- [ ] `mypy app/` — passes; `app/adapters/ticker_resolver_cached.py` typed strictly.
- [ ] `lint-imports` — passes:
  - `app/adapters/ticker_resolver_cached.py` imports from `app.ports` and stdlib only. **No yfinance import.** This is enforced by the decorator pattern.
  - `app/ui/components/ticker_searchbox.py` imports from `app.ports`, `app.domain`, `streamlit`, `streamlit_searchbox`.

### State updates (per CLAUDE.md session-end ritual)

- [ ] `docs/SESSION_LOG.md` appended.
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-021 → IN_REVIEW).
- [ ] `docs/TICKETS/BACKLOG.md` updated (TICKET-021 row → IN_REVIEW).
- [ ] Ticket file `Status: IN_REVIEW`.
- [ ] PR opened via `gh pr create --fill --base main`.

---

## Files created

```
app/adapters/ticker_resolver_cached.py
app/ui/components/ticker_searchbox.py
tests/unit/adapters/test_ticker_resolver_cached.py
tests/unit/ui/test_ticker_searchbox.py
tests/integration/test_ticker_cache_e2e.py
```

## Files modified

```
app/config.py                           ← add ticker_cache_json_path
app/ports/ticker_resolver.py            ← (verify) round-trip serialisation works
app/ui/wiring.py                        ← wrap resolver with CachedTickerResolver
app/ui/pages/manage.py                  ← swap st.text_input for render_ticker_searchbox
pyproject.toml                          ← add streamlit-searchbox dependency
.env.example                            ← document TICKER_CACHE_JSON_PATH
.gitignore                              ← add data/ticker_cache.json
docs/TICKETS/BACKLOG.md                 ← TICKET-021 row → IN_REVIEW
```

---

## Out of scope

- **Cache compaction (dropping expired entries on disk).** TODO marked in code; deferred to a follow-up ticket only if the file grows large enough to matter.
- **Pre-warming the cache from a curated ticker list** (e.g., S&P 500 + DAX 40). Possible future optimisation; not needed for v1 since usage organically warms the cache.
- **Multi-process / multi-tab cache safety.** Streamlit is effectively single-process from the user's perspective; multiple browser tabs share the same Python process. Atomic-replace writes are sufficient.
- **OpenFIGI or alternative metadata providers.** The decorator pattern allows them later; this ticket does not add them.
- **Persistent caching for prices or FX.** Out of scope — those are short-TTL by design (TICKET-004-005), and disk-caching them would create staleness bugs. Only the slow-changing ticker metadata gets persisted.
- **`streamlit-searchbox` styling to match the dark theme exactly.** The library inherits Streamlit's theme; a small visual mismatch is acceptable. If it looks bad in practice, a follow-up CSS tweak ticket can address it.
- **Ranking heuristics.** Results come back in yfinance's order (which favours active US equities). If a German user typing "RHM" gets US results first, that's a future ranking problem — not blocking.

---

## Notes (architectural and methodological — for future AI sessions)

### Why decorator pattern, not "extend the existing adapter"

The yfinance adapter (`app/adapters/yfinance_feed.py`) implements three Protocols (PriceProvider, FxProvider, TickerResolver) and has its own in-memory cache for all three. Adding disk persistence inside it would:

1. Bloat a single file with two distinct caching strategies (the existing in-memory cache for prices/FX, a new disk cache for ticker metadata).
2. Tightly couple disk persistence to one specific provider — making it impossible to decorate a future OpenFIGI adapter the same way.
3. Mix concerns (data fetching + persistence) in a way that is harder to test in isolation.

The decorator separates them. `CachedTickerResolver` is provider-agnostic: it doesn't care whether the inner is yfinance, OpenFIGI, or a hand-rolled in-memory mock. Tests prove this — they use `FakeTickerResolver` as inner and never touch yfinance.

### Why `streamlit-searchbox` and not a custom component

Custom Streamlit components are *expensive*. They require:
- A frontend dev environment (Node, npm, the Streamlit component template).
- Dual repos (Python + JS) or a careful monorepo.
- Versioning the JS asset.
- Testing the bridge.

For one widget that already exists in a maintained library, it's not worth it. `streamlit-searchbox` has been around since 2022, has steady commits, and is used by hundreds of projects. The risk of it dying is real but small; if it does, swapping to a custom component is a self-contained ticket. The fallback path (plain `st.text_input`) protects against acute breakage.

### Why TTL is read-side, not write-side

A TTL enforced on write would mean: "after 30 days, the cache forgets entries." That's wasteful (we have to re-fetch), and worse, it's silent — the user can't tell a cache miss from a fresh fetch. TTL on read means: "after 30 days, we treat it as a miss but still have the old data as a fallback if the network is down." Slightly more code in the read path, much better failure mode.

### Why we negative-cache `lookup` misses but not `resolve` misses

`lookup("XQYZ")` returns `None` because the symbol doesn't exist. Users typo. Caching `None` for "XQYZ" prevents repeated network calls when they keep typing it.

`resolve("XQYZ")` returns `[]` because nothing matches. We *do* cache empty lists too (as `{"results": [], "fetched_at": ...}`) — same logic. The negative-caching applies uniformly. The note above is just emphasising the lookup case because it's the more common typo path.

### Cache key collision: what if a user types "apd" and "APD" separately?

They produce the same key (`resolve:apd`) because we lowercase. This is correct — these are the same query semantically. `lookup` keys uppercase the symbol (`lookup:APD`) which is also correct because canonical ticker symbols are uppercase.

### How this ticket extends to future TICKET-022 (charts)

The cached metadata returned by `lookup(symbol)` includes `name` and `exchange`. The Research page (TICKET-022b) will need both: `name` for the page header, `exchange` for displaying market hours. The disk cache means the Research page can render those instantly even if the chart data is still loading.

### Pattern reuse

`CachedTickerResolver`'s decorator pattern is the same shape as a future `CachedPriceProvider` (deferred — not in scope). When/if we want to persist price history, the pattern carries over with no rethink: a decorating adapter, JSON file, atomic writes, best-effort persistence. This ticket is the first instance of the pattern and should be the reference for future cache decorators.
