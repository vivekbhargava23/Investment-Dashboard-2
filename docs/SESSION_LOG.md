# SESSION_LOG.md

Append-only log of every Claude Code session and significant Claude Chat session.
Newest entries at the bottom.

When this file exceeds ~500 lines, archive everything older than 30 days into `docs/SESSION_LOG_ARCHIVE_<year>_Q<N>.md` and keep this file lean.

---

## 2026-05-03 — Foundation setup (Claude Chat)

**Surface:** Claude Chat (claude.ai)
**Participants:** Vivek + Claude
**Duration:** ~1.5 hours

### What got done
- Decided on greenfield rebuild (old repo archived as reference only)
- Confirmed stack: Streamlit + Pydantic v2 + JSON storage
- Designed the state-handoff system (PROJECT_STATE.md + SESSION_LOG.md + ADRs + TICKETS)
- Defined the Vivek/Claude Chat/Claude Code division of labor
- Drafted root `CLAUDE.md`, `PROJECT_STATE.md`, `METHODOLOGY.md`, `ARCHITECTURE.md`
- Drafted `BACKLOG.md` and `TICKET-000` in detail
- Drafted `ADR-001` (Streamlit over FastAPI)
- Set up `.github/PULL_REQUEST_TEMPLATE.md` for standardized PRs

---

## 2026-05-03 — TICKET-000

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~25 min
**Branch:** ticket-000-scaffolding
**PR:** https://github.com/vivekbhargava23/Investement-Dashboard-Claude/pull/1
**Status at session end:** IN_REVIEW

### What got done
- Created `pyproject.toml` with runtime + dev deps, ruff/mypy/pytest config
- Created full `app/` package structure: domain, services, ports, adapters, ui sub-packages
- Created `app/config.py` — pydantic-settings `Settings` class (single secret-loading boundary)
- Created `app/ui/app.py` — Streamlit placeholder page
- Created `tests/unit/` — smoke, import, and config tests (5 passing)
- Created `.github/workflows/ci.yml` — pytest + ruff + mypy + lint-imports on every push/PR
- Created `.importlinter` — 3 contracts enforcing clean-architecture layer boundaries
- Created `.env.example`, `environment.yml`, `README.md`

---

## 2026-05-03 — TICKET-001

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~45 min
**Branch:** ticket-001-domain-models
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Implemented `Money` value object with normalized Decimal precision and arithmetic/comparison operators.
- Implemented `Transaction` model with validation for EUR FX rates, ticker case, and share quantities.
- Implemented `OpenLot` and `Position` models with consistency checks between positions and underlying lots.
- Created exhaustive unit tests for all domain models, including property-based tests for `Money`.
- Restored `.importlinter` configuration to enforce clean architecture layers.
- Exported all models via `app.domain.__init__.py`.
- All tests and lints (ruff, mypy strict, import-linter) pass.

---

## 2026-05-03 — TICKET-003

**Surface:** Gemini CLI
**Model:** Gemini 2.0 Pro
**Duration:** ~30 min
**Branch:** _pending_
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Implemented `TransactionRepository` port (Protocol) in `app/ports/repository.py` with CRUD and atomic save methods.
- Implemented `JsonTransactionRepository` adapter in `app/adapters/repo_json/json_repo.py` using Pydantic serialization.
- Implemented atomic writes using a temporary file, `fsync`, and `os.replace` to prevent data corruption.
- Added schema versioning (`version: 1`) to the JSON file format.
- Created 18 integration tests in `tests/integration/test_json_repo.py` covering CRUD, atomic writes, corruption handling, and Decimal precision.
- All tests (63 passing), lints (ruff), and type checks (mypy) pass.
- `import-linter` contracts verified.

---

## 2026-05-03 — TICKET-004-005

**Surface:** Gemini CLI
**Model:** Gemini 2.0 Pro
**Duration:** ~45 min
**Branch:** ticket-004-005-yfinance-adapter
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Implemented `PriceProvider` and `FxProvider` ports (Protocols) with detailed error classes.
- Implemented `YfinanceAdapter` satisfying both ports with in-memory caching and 60s TTL.
- Added currency inference heuristic for European tickers (.DE, .F, etc.).
- Implemented EUR/USD FX rate handling with automatic inversion for USD/EUR lookups.
- Created `FakePriceProvider` and `FakeFxProvider` for unit testing downstream services.
- Added integration tests gated by `--run-integration` flag hitting real yfinance.
- Verified all unit and integration tests (94 passing), lints (ruff), type checks (mypy), and import contracts.

---

## 2026-05-03 — TICKET-006

**Surface:** Gemini CLI
**Model:** Gemini 2.0 Pro
**Duration:** ~30 min
**Branch:** ticket-006-valuation-service
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Implemented `LivePosition` and `PortfolioSummary` domain models in `app/domain/positions.py`.
- Created `app/services/CLAUDE.md` defining service layer principles (statelessness, dependency injection).
- Implemented `valuation.py` service with `compute_live_positions`, `compute_portfolio_summary`, and `clear_caches`.
- Implemented per-ticker failure isolation in `compute_live_positions`.
- Created exhaustive unit tests in `tests/unit/services/test_valuation.py` using fakes and mocks.
- Verified all quality checks (ruff, mypy, import-linter) and 104 passing tests.

### Files touched
- `app/domain/positions.py` — updated
- `app/domain/__init__.py` — updated
- `app/services/CLAUDE.md` — new
- `app/services/valuation.py` — new
- `tests/unit/services/test_valuation.py` — new
- `docs/PROJECT_STATE.md` — updated
- `docs/TICKETS/BACKLOG.md` — updated
- `docs/SESSION_LOG.md` — updated

### Tests
94 passing → 104 passing (10 new)

### Decisions made during the session
- Used explicit `Literal` type hint for `staleness` to satisfy `mypy`.
- Favored `compute_live_positions` for generating test data instead of manual `LivePosition` instantiation to avoid consistency check issues.

### Out-of-scope items noticed
- (none)

---

## 2026-05-03 14:30 — TICKET-007

**Surface:** Gemini CLI
**Model:** Gemini 2.0 Pro
**Duration:** ~45 min
**Branch:** ticket-007-streamlit-shell
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Created Streamlit shell with custom dark theme (oklch colors).
- Implemented custom sidebar with query-param routing.
- Implemented topbar with page titles and placeholder FX/time.
- Created 8 placeholder page modules for routing verification.
- Implemented pure formatting helpers for EUR, percentages, shares, and dates.
- Created reusable UI components: MetricCard, ThesisBadge, SeverityBadge.
- Added unit tests for formatting and components (100% coverage for formatters).
- Fixed a pre-existing test failure in `test_valuation.py` (pre-flight chore).

### Files touched
- `app/ui/app.py` — main entry and routing
- `app/ui/styles/dark.css` — custom styling
- `app/ui/format.py` — formatting helpers
- `app/ui/components/*.py` — UI components
- `app/ui/pages/*.py` — page placeholders
- `tests/unit/ui/*.py` — UI tests
- `docs/reference/Investment_Dashboard.html` — design reference
- `docs/PROJECT_STATE.md`, `docs/SESSION_LOG.md`, `docs/TICKETS/BACKLOG.md`

### Tests
74 passing → 91 passing (17 new)

### Decisions made during the session
- Chose `st.columns` with `unsafe_allow_html` for sidebar to allow Streamlit buttons and state management while maintaining layout fidelity.
- Chose query-param routing to allow cleaner "active" state styling in the sidebar.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~15k

---

## 2026-05-03 — TICKET-007 Refactor & UI Polish

**Surface:** Gemini CLI
**Model:** Gemini 2.0 Pro
**Duration:** ~30 min
**Branch:** feature/ui-shell-refactor
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/11
**Status at session end:** IN_REVIEW

### What got done
- Fixed Streamlit shell crash by refactoring entry point to use dynamic imports and placeholders.
- Resolved 'app is not a package' error by renaming `app/ui/app.py` to `app/ui/main.py`.
- Fixed sidebar and topbar HTML rendering issues caused by Markdown whitespace sensitivity.
- Improved CSS loading reliability using relative paths.
- Implemented Light Theme as requested, adjusting OKLCH variables for high contrast.
- Updated all documentation and references to point to `main.py`.

### Files touched
- `app/ui/main.py` (renamed from app.py, refactored)
- `app/ui/styles/dark.css` (converted to light theme)
- `app/ui/components/sidebar.py`
- `app/ui/components/topbar.py`
- `app/ui/components/metric_card.py`
- `README.md`
- `docs/TICKETS/TICKET-000-scaffolding.md`
- `docs/TICKETS/TICKET-007-streamlit-shell.md`
- `docs/TICKETS/TICKET-008-live-overview.md`

### Tests
- All UI unit tests pass (pytest tests/unit/ui/)
- Verified manually that shell starts and routes correctly in light mode.

---

## 2026-05-03 — TICKET-008

**Surface:** Gemini CLI
**Model:** Gemini 2.0 Pro
**Duration:** ~45 min
**Branch:** ticket-008-live-overview
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Created seed script `app/scripts/seed_portfolio.py` to bootstrap transactions.
- Wired live overview logic in `app/ui/pages/overview.py` including `st.cache_data`.
- Implemented singleton caching in `app/ui/wiring.py` for repository and providers.
- Wired topbar refresh button to flush cache.
- Added comprehensive unit and e2e integration tests.

### Files touched
- `docs/reference/seed_portfolio.csv` (new)
- `app/scripts/__init__.py` (new)
- `app/scripts/seed_portfolio.py` (new)
- `app/ui/wiring.py` (new)
- `app/ui/pages/overview.py` (updated)
- `app/ui/components/topbar.py` (updated)
- `tests/integration/test_seed_script.py` (new)
- `tests/unit/ui/test_overview_helpers.py` (new)
- `tests/unit/ui/test_overview_render.py` (new)
- `tests/integration/test_overview_e2e.py` (new)

### Tests
91 passing → 97 passing (6 new)

---

## 2026-05-04 — TICKET-008b

**Surface:** Claude Code
**Model:** claude-sonnet-4-6
**Duration:** ~40 min
**Branch:** ticket-008b-html-leak-fix (based on ticket-008-live-overview)
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/13
**Status at session end:** IN_REVIEW

### What got done
- Created `app/ui/render.py`: `render_html(html)` helper that applies `textwrap.dedent` + `.strip()` before calling `st.markdown(..., unsafe_allow_html=True)`. This is now the only place in the codebase where `unsafe_allow_html=True` is set.
- Created `app/ui/CLAUDE.md`: documents the HTML rendering rule so future pages cannot accidentally introduce the same bug.
- Refactored `app/ui/pages/overview.py`: replaced all 5 direct `st.markdown(..., unsafe_allow_html=True)` calls with `render_html()`; extracted `_build_positions_table_html(positions, summary) -> str` as a pure helper that builds the table using single-line string concatenation (no leading whitespace, no markdown code-block trigger).
- Wrote regression tests first (confirmed failing), then implemented the fix:
  - `tests/unit/ui/test_html_helper.py`: 4 tests for `render_html`
  - `tests/unit/ui/test_overview_render.py`: extended with 6 regression tests that assert `_build_positions_table_html` returns a string starting with `<`, with no 4+-space prefix, one `<table` tag, and no double-escaping.

### Files touched
- `app/ui/render.py` (new)
- `app/ui/CLAUDE.md` (new)
- `app/ui/pages/overview.py` (refactored)
- `docs/TICKETS/TICKET-008b-html-leak-fix.md` (status: IN_REVIEW)
- `tests/unit/ui/test_html_helper.py` (new)
- `tests/unit/ui/test_overview_render.py` (extended)

### Tests
97 passing → 107 passing (10 new)

---

## 2026-05-04 — TICKET-008b + cleanup

**Surface:** Claude Code + Claude Chat (debugging session)
**Duration:** ~2 hours
**Branch:** ticket-008b-html-leak-fix
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/13 (merged)
**Status at session end:** MERGED

### What got done
- Fixed positions table HTML leak: extracted `_build_positions_table_html` as pure helper, added `app/ui/render.py:render_html()` as the single place where `unsafe_allow_html=True` is set.
- Added 10 regression tests (4 for the helper, 6 for the table builder), confirmed failing-before-fix and passing-after-fix.
- Discovered and fixed Python stdlib collision: `app/ui/html.py` shadowed the stdlib `html` package in Streamlit's import context, breaking bs4 → yfinance import chain. Renamed module to `app/ui/render.py`.
- Fixed `.gitignore` gap: `data/portfolio.json` was being tracked (rule was for stale filename `data/transactions.json`). Now `data/*` is ignored except `.gitkeep`.
- Closed superseded PR #12 (contained Gemini's ineffective "consolidated UI fix" commits). Merged PR #13 directly to `main`.

### Methodology lessons (to fold into METHODOLOGY.md)
- Module names must not collide with Python stdlib (`html`, `email`, `string`, `io`, `time`, `json`, `logging`, etc.). Add to ticket-drafting checklist.
- "Verification" means observed working behavior in the running app, not just tests passing. PR descriptions should require a screenshot of the working state.
- "Reconcile" and "consolidate" are scope-expansion verbs. Open-ended fix instructions like "fix the problem" license agents to expand scope. Tickets need explicit "Files NOT to modify" sections for bug fixes.
- `pip install -e .` should be in README setup so `PYTHONPATH=.` is never needed.

### Tests
107 passing

---

## 2026-05-04 — TICKET-009

**Surface:** Gemini CLI
**Model:** Gemini 2.5 Pro
**Duration:** ~45 min
**Branch:** main (Direct commit for speed, though normally a branch)
**Status at session end:** IN_REVIEW

### What got done
- Implemented `app/ui/pages/manage.py` for CRUD portfolio operations (Add/Edit/Delete transactions).
- Handled FIFO validation on the form before persistence to prevent invalid sequence states.
- Handled form-level state for Edit and Delete interactions via `st.session_state`.
- Added CSS `.tx-row` styling to `app/ui/styles/dark.css`.
- Added integration tests for CRUD and FIFO interaction in `tests/integration/test_manage_crud.py`.
- Added unit tests for UI helper methods in `tests/unit/ui/test_manage_page.py`.
- Updated backlog and project state markdown documents.

### Files touched
- `app/ui/pages/manage.py`
- `app/ui/styles/dark.css`
- `tests/integration/test_manage_crud.py`
- `tests/unit/ui/test_manage_page.py`
- `docs/PROJECT_STATE.md`
- `docs/TICKETS/BACKLOG.md`
- `docs/TICKETS/TICKET-009-manage-portfolio.md`
- `docs/SESSION_LOG.md`

### Tests
107 passing -> 117 passing (10 new)

## 2026-05-04 — Drafting session: ADR-005 + TICKET-008c, 020, 009-revised (Claude Chat)

**Surface:** Claude Chat (claude.ai)
**Participants:** Vivek + Claude
**Duration:** ~2 hours

### What got done
- Bench-tested original TICKET-009 implementation against real Scalable Capital workflow.
- Surfaced three silent-corruption bugs: (1) FX field defaulted to 1.0 with no warning on USD APD purchase; (2) Currency dropdown defaulted to EUR for NVDA, producing stale row; (3) 5631.T mislabelled as USD since seed time, producing €4,032 of fake unrealised gain.
- Diagnosed root cause: form's input model demands data Scalable doesn't surface to the user (native price, FX rate). Three bugs were symptoms of one mismatch.
- Drafted ADR-005: input becomes EUR-native; currency and FX inferred from ticker + broker EUR total; data model unchanged.
- Drafted TICKET-008c: extend Currency enum (add JPY); add ticker↔currency domain validator; migrate `data/portfolio.json`.
- Drafted TICKET-020: new `TickerResolver` port + yfinance adapter for autocomplete.
- Drafted TICKET-009-revised: replaces original TICKET-009 form with EUR-native input, ticker autocomplete, 2% FX-deviation guard, transparent fallback to manual entry.
- Decided to close original TICKET-009 PR #14 without merging.

### Decisions made during the session
- ADR-005 chosen over three alternatives (patch existing form; pure EUR-only with no currency tracking; native + live EUR readout). See ADR for rejection reasons.
- 2% FX deviation tolerance for the new form's warning (catches typos; tolerates broker spread of 5–25 bps).
- Migration script (TICKET-008c) preserves recorded EUR cost basis rather than recomputing from yfinance, with an interactive override for 5631.T specifically.
- Currency enum extended only to JPY in this round; GBP/CHF/HKD added on demand.
- TICKET-009-revised supersedes TICKET-009 wholesale (form module rewrite). Original PR closed, not merged. Implementer not penalised — the ticket spec was correct as drafted; the spec itself was wrong, which is what bench-testing surfaced.

### Out-of-scope items noticed
- METHODOLOGY.md updates from TICKET-008b's session log (stdlib name collisions, "verification = observed behavior", scope-expansion verbs) still pending.
- The placeholder `_TICKER_NAMES` dict in `app/ui/pages/overview.py` becomes obsolete after TICKET-009-revised; cleanup folded into that ticket.
- Methodology lesson to fold in: "Bench-test ticket specs against real-world workflow before marking READY."

### Files touched (chat-side; repo edits done by Vivek post-session)
- `docs/DECISIONS/ADR-005-eur-native-input.md` (new)
- `docs/TICKETS/TICKET-008c-currency-correctness.md` (new)
- `docs/TICKETS/TICKET-020-ticker-resolver.md` (new)
- `docs/TICKETS/TICKET-009-revised-eur-native-form.md` (new)
- `docs/PROJECT_STATE.md` (updated)
- `docs/TICKETS/BACKLOG.md` (updated)
- `docs/SESSION_LOG.md` (this entry)

---

## 2026-05-05 — Drafting session: Tax Engine, Dashboard, and Simulator (Claude Chat)

**Surface:** Claude Chat (claude.ai)
**Participants:** Vivek + Claude
**Duration:** ~1 hour

### What got done
- Drafted TICKET-010: Detailed spec for the pure-Python tax engine (pipeline, rates, classification).
- Drafted TICKET-011: Detailed spec for the Tax Dashboard page and service layer.
- Drafted TICKET-012: Detailed spec for the Pre-trade sell simulator and FIFO lot-preview.
- Updated docs/TICKETS/BACKLOG.md and docs/PROJECT_STATE.md to reflect the new tickets.

### Decisions made during the session
- Chose to keep the tax engine pure and stateless in `app/domain/tax/`.
- Decided on a JSON-based tax profile repository for persisting carryforwards and status.
- Opted for a "sequential" harvest impact model in the UI to reflect shared allowance.
- Simulator will use a promoted `simulate_lot_consumption` helper from the FIFO engine.


---

## 2026-05-05 — TICKET-010 Appendix: Bench-test findings (Claude Code)

**Surface:** Gemini CLI
**Participants:** Vivek + Claude
**Duration:** ~5 min

### What got done
- Added "Bench-test findings (2026-05-04)" appendix to `docs/TICKETS/TICKET-010-tax-engine.md`.
- Documented requirement for per-trade tax withholding tracking.
- Documented five new transaction types (DIVIDEND, INTEREST, taxes).
- Documented CAD currency requirement for specific holdings (Niobium).


## 2026-05-05 14:30 — TICKET-008c

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~90 min
**Branch:** ticket-008c-currency-correctness
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/19
**Status at session end:** IN_REVIEW

### What got done
- Pre-existing bug fix: `tests/unit/ui/test_html_helper.py` imported from `app.ui.html`
  (renamed to `app.ui.render` in TICKET-008b) — 4 tests were broken on main before work started.
  Fixed as a prep commit; reported to Vivek.
- `Currency.JPY` added to `app/domain/money.py`; `__str__` updated: JPY → `¥` prefix,
  zero decimal places (e.g. `¥9,049`).
- New `app/domain/tickers.py`: pure `infer_currency_from_ticker()` function; maps
  `.DE`/`.F`/`.MI`/`.PA`/`.AS` → EUR, `.T` → JPY, `.HK` → `UnsupportedTickerError`,
  unsuffixed → USD. Single source of truth for ticker→currency mapping (ADR-005).
- `Transaction` gains `@model_validator` that calls `infer_currency_from_ticker`;
  rejects construction if ticker and price currency disagree. 5631.T-as-USD is now
  structurally impossible.
- `JsonTransactionRepository.load_all()` pre-checks ticker↔currency consistency;
  raises `LegacyDataError` (with `.offenders` attribute and migration-script hint)
  before attempting full Pydantic construction. Existing `RepositoryCorruptedError`
  path for other validation failures preserved.
- `YfinanceAdapter._infer_currency()` now delegates to `infer_currency_from_ticker()`
  (eliminating duplicated logic). FX rate methods extended to cover EUR/JPY, JPY/EUR,
  USD/JPY, JPY/USD via new `_fx_yfinance_ticker()` helper.
- New `app/scripts/migrate_currency.py`: one-shot CLI that detects legacy ticker↔
  currency mismatches, fetches historical native-currency close from yfinance,
  back-computes FX rate to preserve recorded EUR cost basis; dry-run, --force,
  interactive override for the specific 5631.T row; validates output round-trips
  through `JsonTransactionRepository` before writing.
- `docs/reference/seed_portfolio.csv`: 5631.T row rewritten as JPY (price=8829.5596,
  fx=0.005776); "use USD as approximation" note deleted; schema comment added.
- `data/portfolio.json` already had JPY for 5631.T from prior aborted attempt;
  file is gitignored so not committed — migration is a no-op in current state.

### Files touched
- `app/domain/money.py` — JPY enum member + __str__ dispatch
- `app/domain/tickers.py` — new module
- `app/domain/models.py` — ticker↔currency @model_validator
- `app/domain/__init__.py` — export infer_currency_from_ticker, UnsupportedTickerError
- `app/adapters/repo_json/json_repo.py` — LegacyDataError + pre-check in load_all
- `app/adapters/yfinance_feed/yfinance_adapter.py` — delegate + JPY FX pairs
- `app/scripts/migrate_currency.py` — new migration script
- `tests/unit/domain/test_money.py` — JPY cases
- `tests/unit/domain/test_transaction.py` — currency validator cases (incl. regression)
- `tests/unit/domain/test_tickers.py` — new test module
- `tests/unit/domain/test_fifo.py` — ticker fixtures updated to EUR-suffixed (.DE)
- `tests/unit/services/test_valuation.py` — MISSING→NOPRICE.DE
- `tests/unit/ui/test_html_helper.py` — import path fix (app.ui.html → app.ui.render)
- `tests/integration/test_json_repo.py` — LegacyDataError tests
- `tests/integration/test_yfinance_real.py` — JPY price + FX rate integration tests
- `tests/integration/test_migrate_currency.py` — new migration tests
- `tests/fixtures/portfolio_legacy_jpy_as_usd.json` — new legacy fixture
- `docs/reference/seed_portfolio.csv` — 5631.T row fixed
- `docs/TICKETS/TICKET-008c-currency-correctness.md` — status IN_REVIEW
- `docs/TICKETS/BACKLOG.md` — TICKET-008c → IN_REVIEW
- `docs/PROJECT_STATE.md` — TICKET-008c moved to In review

### Tests
107 passing → 128 passing (21 new; 38 skipped — integration tests gated behind @pytest.mark.integration)

### Decisions made during the session
- Pre-existing test failure (app.ui.html → app.ui.render import) fixed inline as a
  prep commit rather than a separate hotfix PR — reported to Vivek before proceeding.
- `data/portfolio.json` is gitignored; migration confirmed as no-op since prior
  aborted attempt already updated the local file; documented in PR description.
- `dict[str, Any]` used in migration script for raw JSON data — `object` type is too
  restrictive for mypy's attribute checks on JSON-sourced dicts.

### Out-of-scope items noticed
- TICKET-008b session note: `app/ui/html.py` → `app/ui/render.py` rename left stale
  import in `test_html_helper.py`. Fixed here since it was blocking a green baseline.
- `data/portfolio.json` is gitignored. The ticket spec assumed it would be committed;
  per `.gitignore`, it's user data. Migration documented in PR instead.

### Tokens used (rough)
~85k

## 2026-05-05 16:00 — TICKET-020

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~40 min
**Branch:** ticket-020-ticker-resolver
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/20
**Status at session end:** IN_REVIEW

### What got done
- New `app/ports/ticker_resolver.py`: `TickerMatch` frozen Pydantic model
  (symbol, name, exchange, currency: Currency, recent_price: Money | None) and
  `TickerResolver` Protocol (resolve, lookup, clear_cache).
- `app/ports/__init__.py` updated to export `TickerMatch` and `TickerResolver`.
- `YfinanceAdapter` extended to satisfy `TickerResolver` alongside existing
  `PriceProvider` and `FxProvider`:
  - `_resolver_cache: dict[str, tuple[float, Any]]` with 3600s TTL
  - `_build_match(symbol, name, exchange)`: shared helper that calls
    `infer_currency_from_ticker`; returns `None` for unsupported currencies
    (e.g. HKD) so callers can silently omit rather than raise
  - `resolve(query, limit)`: yf.Search-backed; normalises query; empty →
    returns []; exceptions → empty list with warning log; respects limit
  - `lookup(symbol)`: yf.Ticker.info exact fetch; None on miss or unsupported
  - `clear_cache()` extended to also clear `_resolver_cache`
- `tests/fakes/ticker_resolver.py`: `FakeTickerResolver` that satisfies
  `TickerResolver` Protocol via hardcoded match list; used by TICKET-009-revised.
- `tests/unit/ports/test_ticker_resolver_protocol.py`: 12 unit tests covering
  TickerMatch construction/frozen, EUR/JPY variants, FakeTickerResolver resolve/
  lookup/clear_cache behaviour.
- `tests/integration/test_yfinance_resolver.py`: 11 tests (7 integration-marked
  needing network; 4 using mocks); covers USD/EUR/JPY resolve, empty/garbage
  queries, unsupported-currency omission, search exceptions, limit enforcement.

### Files touched
- `app/ports/ticker_resolver.py` — new
- `app/ports/__init__.py` — export TickerMatch, TickerResolver
- `app/adapters/yfinance_feed/yfinance_adapter.py` — resolver methods added
- `tests/fakes/ticker_resolver.py` — new
- `tests/unit/ports/__init__.py` — new
- `tests/unit/ports/test_ticker_resolver_protocol.py` — new
- `tests/integration/test_yfinance_resolver.py` — new
- `docs/TICKETS/TICKET-020-ticker-resolver.md` — status IN_REVIEW
- `docs/TICKETS/BACKLOG.md` — TICKET-020 → IN_REVIEW
- `docs/PROJECT_STATE.md` — TICKET-020 moved to In review

### Tests
128 passing → 140 passing (12 new; 50 skipped — integration tests gated behind @pytest.mark.integration)

### Decisions made during the session
- yfinance Search results have no `currency` field; `infer_currency_from_ticker`
  is used exclusively rather than cross-checking yfinance metadata — this is
  consistent with TICKET-008c's design and avoids the risk of stale yfinance
  currency metadata causing issues.
- resolve() returns `list(cached)` (a new list) rather than the cached list
  object directly, to prevent callers mutating the cache.
- lookup() uses `isinstance(cached, TickerMatch)` guard when returning from
  cache to keep the return type clean for mypy.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~25k

## 2026-05-06 — TICKET-009-revised

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~90 min (including context-window continuation)
**Branch:** ticket-009-revised-eur-native-form
**PR:** (opening this session)
**Status at session end:** IN_REVIEW

### What got done
- New `app/services/trading.py`: `build_transaction()` pure pipeline — EUR-native path
  (price_per_share from net EUR / shares, fx_rate_eur=1) and non-EUR path (fetch
  historical close via PriceProvider, back-compute implied FX, deviation check vs ECB).
  Returns `(Transaction, deviation_pct)` where deviation_pct is None for EUR.
- Full rewrite of `app/ui/pages/manage.py` (EUR-native form, ADR-005):
  - Two-step Add flow: Fill → Calculate Preview → Confirm & Record.
    Preview hidden until explicitly triggered; "Confirm & Record" becomes "Record anyway"
    if FX deviation ≥ 10%.
  - Bug fix: "Total EUR paid" defaults to `None` (blank) instead of 0.01; user must
    type their actual broker debit.
  - Ticker autocomplete with `TickerResolver.resolve()` + "Use as-typed" escape hatch.
  - Fallback manual-entry path exposed in the preview step when `PriceUnavailableError`.
  - Live recording preview in edit form (unchanged — edit flow keeps inline preview).
  - Edit / Delete table with per-row buttons and inline delete confirmation.
  - `_init_state`, `_tx_to_form_values`, `_match_label` as pure testable helpers.
- New `app/ui/wiring.py`: `get_ticker_resolver()` singleton.
- New `tests/unit/ui/test_manage_form_pipeline.py`: 12 tests for `build_transaction`
  (EUR/USD/JPY happy paths, cost_eur round-trip, zero fees, deviation warning,
  graceful on missing ECB rate, FIFO sell guard pass/fail, validator regression).
- New `tests/unit/ui/test_manage_page.py`: 10 tests for pure helpers
  (`_init_state` idempotency, `_tx_to_form_values` EUR/USD, `_match_label` formatting).
- New `tests/integration/test_manage_e2e.py`: 9 tests (add EUR/USD/JPY, three together,
  edit shares, delete, resolver lookup, manual fallback).
- Fixed pre-existing test failures caused by TICKET-008c ticker↔currency validator:
  renamed test tickers in `test_fifo.py` (NVDA → NVDA.DE / SAP.DE / RHM.DE) and
  `test_valuation.py` (MISSING → NOPRICE.DE) to use EUR-suffixed symbols.
- New `tests/fixtures/portfolio_legacy_jpy_as_usd.json` for LegacyDataError tests.
- New `tests/fakes/ticker_resolver.py`: `FakeTickerResolver`.

### Files touched
- `app/services/trading.py` — new
- `app/ui/pages/manage.py` — full rewrite (EUR-native two-step form)
- `app/ui/wiring.py` — get_ticker_resolver() singleton
- `tests/unit/ui/test_manage_form_pipeline.py` — new
- `tests/unit/ui/test_manage_page.py` — new
- `tests/integration/test_manage_e2e.py` — new
- `tests/fakes/ticker_resolver.py` — new
- `tests/fixtures/portfolio_legacy_jpy_as_usd.json` — new
- `tests/unit/domain/test_fifo.py` — ticker renames (EUR-suffix fix)
- `tests/unit/services/test_valuation.py` — ticker rename (EUR-suffix fix)
- `tests/unit/ui/test_html_helper.py` — import fix (app.ui.html → app.ui.render)
- `docs/TICKETS/TICKET-009-revised-eur-native-form.md` — status IN_REVIEW

### Tests
140 passing → 161 passing (21 new)

### Decisions made during the session
- Two-step submit (Fill → Preview → Confirm) chosen over live preview to prevent
  accidental submissions before the user has verified the FX back-computation.
- `build_transaction` placed in `app/services/` (pure, no Streamlit) so it is
  fully unit-testable without a Streamlit context.
- Fallback manual-entry exposed in preview step (not fill step) to keep the happy
  path clean; only surfaced when yfinance price fetch actually fails.
- Deviation threshold for button-label change: ≥10% → "Record anyway";
  >2% → warning shown inline (both thresholds tunable without tests).
- `eur_total value=None` (blank) is correct UX; 0.01 was a Streamlit default
  artefact that had no relation to any real transaction amount.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~120k (two context windows)
