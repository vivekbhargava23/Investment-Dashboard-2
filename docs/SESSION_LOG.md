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

---

## 2026-05-06 14:00 — TICKET-010

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~90 min
**Branch:** ticket-010-tax-engine
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/22
**Status at session end:** IN_REVIEW

### What got done
- Created `app/domain/tax/` sub-package with 6 files:
  - `classification.py` — `InstrumentKind` enum + `TICKER_KIND` table (12 seed tickers) + `classify_instrument` (raises loudly on unknown)
  - `rates.py` — `TaxYearRates`, `TAX_RATES_2025`, `TAX_RATES_2026`, `RATES_BY_YEAR`, `UnsupportedTaxYearError`
  - `models.py` — `FilingStatus`, `TaxProfile`, `TaxImpact`, `LossPotState`, `TaxYearSummary` (all frozen Pydantic)
  - `pipeline.py` — internal `TaxYearLedger` dataclass + 8 ordered pipeline steps enforcing §20 EStG rule sequence
  - `engine.py` — `compute_tax_year_summary` (pure, referentially transparent)
  - `CLAUDE.md` — per-module rules
- Extended `app/domain/__init__.py` to re-export tax public API
- Created 50 unit tests across 5 test files in `tests/unit/domain/tax/`
- Created `tests/fixtures/tax/nrw_aktienfonds_2024.json`

### Files touched
- `app/domain/tax/` — entire sub-package (new)
- `app/domain/__init__.py` — added tax re-exports
- `tests/unit/domain/tax/` — 5 test files (new)
- `tests/fixtures/tax/nrw_aktienfonds_2024.json` — new
- `docs/TICKETS/TICKET-010-tax-engine.md` — status → IN_REVIEW

### Tests
161 passing → 211 passing (50 new)

### Decisions made during the session
- No architectural decisions required beyond what was drafted in the ticket spec.
- `TaxYearLedger` is a mutable dataclass (not frozen) since it is internal-only; pipeline steps mutate and return it.
- Tests import private pipeline functions (`_apply_*`) directly — acceptable since these functions are the primary test surface; the tests are in `tests/unit/domain/tax/` not in production code.

### Out-of-scope items noticed
- `tests/unit/domain/tax/test_known_scenarios.py::test_loss_pot_firewall_worked_example` uses TaxImpact with `teilfreistellung_pct=0.00` on an AKTIENFONDS to get an exact -€1000 taxable amount. This is a test construct only; in production, the classifier + rates always compute the correct percentage.

### Tokens used (rough)
~80k

## 2026-05-06 14:30 — TICKET-011

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~90 min
**Branch:** ticket-011-tax-dashboard
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/23
**Status at session end:** IN_REVIEW

### What got done
- Added `HarvestImpact`, `HarvestImpactReport` to `app/domain/tax/models.py`
- Added `current_year_losses_unconsumed_eur` property to `LossPotState`
- Created `app/ports/tax_profile_repo.py` — `TaxProfileRepository` Protocol, `TaxProfileDocument`, `YearlyTaxInputs`
- Created `app/adapters/repo_json/tax_profile_repo.py` — `JsonTaxProfileRepository` (atomic write, legacy version detection)
- Created `app/services/tax_planning.py` — three pure service functions:
  `compute_current_tax_summary`, `compute_per_position_harvest_impact`, `compute_tax_if_full_liquidation`
- Created `app/ui/cache_keys.py` — factored `transactions_signature` + added `file_mtime_key`
- Built Tax Dashboard page (`app/ui/pages/tax.py`): YTD tiles, Sparerpauschbetrag progress bar,
  total tax exposure section, harvest opportunity table (sequential), loss harvesting table,
  edit tax profile expander with Steuerbescheid guidance
- Wired Sparerpauschbetrag and Tax Headroom tiles on Live Overview (removed hardcoded TICKET-010 placeholders)
- Added `tax_profile_json_path` to `app/config.py` and `Settings`
- Added `get_tax_profile_repo()` lazy singleton to `app/ui/wiring.py`
- Added `.tax-progress-wrap` and `.harvest-table` CSS classes to `dark.css`
- Created `.env.example` (was missing from repo), added `data/tax_profile.json` to `.gitignore`
- Created `tests/fixtures/tax_profile_legacy_v0.json` for legacy version rejection test
- 12 new unit tests: 7 service tests, 5 UI helper tests
- 2 integration test files (skipped without `--run-integration` flag)

### Files touched
- `app/domain/tax/models.py` — added HarvestImpact, HarvestImpactReport, LossPotState property
- `app/domain/tax/__init__.py` — re-exported new types
- `app/ports/tax_profile_repo.py` — new
- `app/adapters/repo_json/tax_profile_repo.py` — new
- `app/config.py` — tax_profile_json_path setting
- `app/services/tax_planning.py` — new
- `app/ui/cache_keys.py` — new
- `app/ui/pages/tax.py` — full implementation (was stub)
- `app/ui/pages/overview.py` — wire two tiles; use transactions_signature from cache_keys
- `app/ui/styles/dark.css` — .tax-progress-wrap, .harvest-table
- `app/ui/wiring.py` — get_tax_profile_repo()
- `.env.example` — new
- `.gitignore` — data/tax_profile.json
- `tests/unit/services/test_tax_planning.py` — new
- `tests/unit/ui/test_tax_page_helpers.py` — new
- `tests/integration/test_tax_profile_repo.py` — new
- `tests/integration/test_tax_dashboard_e2e.py` — new
- `tests/fixtures/tax_profile_legacy_v0.json` — new
- `tests/unit/ui/test_overview_helpers.py` — updated import to cache_keys
- `docs/TICKETS/TICKET-011-tax-dashboard-page.md` — status → IN_REVIEW

### Tests
211 passing → 223 passing (12 new)

### Decisions made during the session
- `compute_per_position_harvest_impact` takes `transactions` + `as_of` in addition to `current_summary`
  because the engine computes FIFO gains from transactions internally; there's no way to reconstruct
  the per-gain breakdown from the summary alone without duplicating pipeline logic.
- `compute_headroom` uses `remaining_carryforward_eur` from each pot (not `prior_year_carryforward + unconsumed_current_losses`)
  because they are mathematically equivalent and simpler. The property `current_year_losses_unconsumed_eur`
  is added to `LossPotState` for completeness but is not used in the headroom formula.
- Test case for headroom with "mixed components" redesigned from ticket spec: the ticket's described
  scenario (€400 allowance remaining + €300 aktien pot + €200 general pot intact) is not achievable
  with the current engine pipeline (carryforward is consumed before allowance). Used a correct equivalent.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~100k

---

## 2026-05-07 — TICKET-012

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~90 min
**Branch:** ticket-012-pre-trade-sell-simulator
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/26
**Status at session end:** IN_REVIEW

### What got done
- Promoted `_consume_from_lots` to public `simulate_lot_consumption` (pure, tuple-in/tuple-out); refactored `compute_realised_gains` to call it internally.
- Added `MarginalTaxImpact` frozen Pydantic model to `app/domain/tax/models.py`.
- Added `compute_marginal_tax_for_realised_gains` to `app/services/tax_planning.py` — runs the engine before/after the proposed sell and returns per-field deltas.
- New `app/services/sell_simulator.py`: `SellSimulationRequest`, `LotConsumption`, `PositionAfterSnapshot`, `SellSimulation`, `simulate_sell` (read-only, deterministic — uses a stable transaction ID derived from request fields).
- New `app/ui/components/sell_simulator.py`: embeddable `render_sell_simulator` panel with lot table, tax impact tiles, and position-after tiles.
- New `app/ui/pages/simulator.py`: top-level Pre-trade Sell Simulator page; reads default ticker from `session_state.simulator_default_ticker` or `?ticker=` query param.
- Added ⚡ Simulate sell HTML links to Live Overview positions table and Tax Dashboard harvest table (navigates to `/?page=simulator&ticker=TICKER`).
- `manage.py`: added `_apply_simulator_handoff` that pre-fills the Add Transaction form and advances to preview step when `session_state.simulator_handoff` is set.
- Sidebar + PAGE_TITLES: added Simulator entry between Lot Ledger and Manage Portfolio.
- Tests: 21 new tests across domain, service, UI, and integration layers. 223 → 244 passing.

### Files touched
- `app/domain/fifo.py` — `simulate_lot_consumption` public function; refactored `compute_realised_gains`
- `app/domain/__init__.py` — export `simulate_lot_consumption`
- `app/domain/tax/models.py` — add `MarginalTaxImpact`
- `app/domain/tax/__init__.py` — export `MarginalTaxImpact`
- `app/services/tax_planning.py` — add `compute_marginal_tax_for_realised_gains`
- `app/services/sell_simulator.py` — new
- `app/ui/components/sell_simulator.py` — new
- `app/ui/pages/simulator.py` — new
- `app/ui/pages/overview.py` — add Sim column
- `app/ui/pages/tax.py` — add Sim column to harvest table
- `app/ui/pages/manage.py` — accept simulator handoff
- `app/ui/components/sidebar.py` — add Simulator nav entry
- `app/ui/components/topbar.py` — add "simulator" to PAGE_TITLES
- `tests/unit/domain/test_simulate_lot_consumption.py` — new (8 tests)
- `tests/unit/services/test_sell_simulator.py` — new (9 tests)
- `tests/unit/ui/test_sell_simulator_component.py` — new (4 tests)
- `tests/integration/test_simulator_e2e.py` — new (3 tests, 1 for each e2e scenario)
- `tests/unit/ui/test_components.py` — updated NAV_ITEMS count

### Tests
223 passing → 244 passing (21 new)

### Decisions made during the session
- Deterministic transaction ID for hypothetical sell (derived from request fields) to make `simulate_sell` a pure function (same input → same output).
- `marginal_taxable_gain_eur` is the delta in `total_taxable_after_loss_offset_eur` (before allowance deduction), per ticket spec — consistent with how the engine fields are named.
- Simulator → Manage Portfolio handoff uses `st.query_params` (`?ticker=`) for HTML table links (since HTML `<a>` tags can't set session_state), plus `session_state.simulator_default_ticker` for button-triggered navigation.
- Carryforward params added to `compute_marginal_tax_for_realised_gains` and `simulate_sell` (not in original ticket spec, but required for correct marginal analysis with real carryforward losses).

### Out-of-scope items noticed
- (none — stayed within ticket scope)

### Tokens used (rough)
~180k

---

## 2026-05-07 14:00 — TICKET-021

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~90 min
**Branch:** ticket-021-smooth-ticker-autocomplete
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/27
**Status at session end:** IN_REVIEW

### What got done
- Added `CachedTickerResolver` decorating adapter (`app/adapters/ticker_resolver_cached.py`) — disk-backed JSON cache with 30-day TTL, lazy load, atomic writes, best-effort persistence (never raises)
- Added `render_ticker_searchbox` UI component (`app/ui/components/ticker_searchbox.py`) wrapping `streamlit-searchbox`, with `_search_callback_for` factory (testable without Streamlit runtime)
- Replaced `st.text_input + st.selectbox` ticker block in Add Transaction form with `render_ticker_searchbox`; "use as-typed" escape hatch retained
- Updated Edit Transaction form with pre-filled searchbox (`default_match=resolver.lookup(tx.ticker)`)
- Added `ticker_cache_json_path` to `app/config.py` and `.env.example`
- Updated `app/ui/wiring.py` to wrap the yfinance resolver with `CachedTickerResolver`
- Added `streamlit-searchbox>=0.1.16` to `pyproject.toml`; added `data/ticker_cache.json` to `.gitignore`
- Added call counters (`resolve_call_count`, `lookup_call_count`) to `FakeTickerResolver`

### Files touched
- `app/adapters/ticker_resolver_cached.py` — new
- `app/ui/components/ticker_searchbox.py` — new
- `app/ui/wiring.py` — wrap resolver with CachedTickerResolver
- `app/ui/pages/manage.py` — swap ticker input for searchbox (add + edit forms)
- `app/config.py` — add ticker_cache_json_path
- `pyproject.toml` — add streamlit-searchbox dependency + mypy override
- `.gitignore` — add data/ticker_cache.json
- `.env.example` — document TICKER_CACHE_JSON_PATH
- `tests/fakes/ticker_resolver.py` — add resolve_call_count, lookup_call_count
- `tests/unit/ports/test_ticker_resolver_protocol.py` — 3 new round-trip tests
- `tests/unit/adapters/test_ticker_resolver_cached.py` — new (13 tests)
- `tests/unit/ui/test_ticker_searchbox.py` — new (5 tests)
- `tests/integration/test_ticker_cache_e2e.py` — new (1 integration test, skipped without --run-integration)

### Tests
244 passing → 265 passing (21 new); 68 skipped (integration tests including new one)

### Decisions made during the session
- `_search_callback_for(resolver)` factory pattern makes the callback testable without a Streamlit runtime (imported directly in unit tests)
- `manage_add_form_key` counter in session state resets the searchbox widget after a transaction is recorded (Streamlit widget-reset pattern)
- `cast(TickerResolver, get_price_provider())` in wiring.py avoids a type: ignore while correctly expressing that YfinanceAdapter satisfies both protocols

### Out-of-scope items noticed
- (none — stayed within ticket scope)

### Tokens used (rough)
~120k

---

## 2026-05-07 — TICKET-023

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~30 min
**Branch:** ticket-023-eur-price-check
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/28
**Status at session end:** IN_REVIEW

### What got done
- `app/domain/tickers.py`: promoted `_UNSUPPORTED_SUFFIXES` from a local tuple
  to a module-level dict mapping suffix → currency name. Added `.KS`/`.KQ` (KRW),
  `.TW`/`.TWO` (TWD), `.BK` (THB). These now raise `UnsupportedTickerError` instead
  of silently defaulting to USD. `.HK` retained with the same error message.
- `app/ui/pages/manage.py` (`_render_recording_preview`): replaced the EUR branch
  early-return (no price check) with a real `get_historical_close` call. Computes
  `eur_deviation_pct`; shows ⚠ warning when >2%, ✓ confirmation when within 2%,
  or a "Couldn't fetch" warning on `PriceUnavailableError`. Form remains usable in
  all cases (`price_available=True`).
- `app/ui/pages/manage.py`: broad `except Exception: return True, None` now logs
  at WARNING with `exc_info=True` before returning, so unexpected errors are visible.

### Files touched
- `app/domain/tickers.py` — `_UNSUPPORTED_SUFFIXES` dict with 6 suffixes
- `app/ui/pages/manage.py` — EUR price check; logging in broad except
- `tests/unit/domain/test_tickers.py` — 5 new cases (.KS, .KQ, .TW, .TWO, .BK)
- `tests/unit/ui/test_manage_form_pipeline.py` — 4 new _render_recording_preview tests

### Tests
265 passing → 274 passing (9 new); 68 skipped

### Decisions made during the session
- Used distinct variable names (`eur_price_per_share`, `eur_deviation_pct`) in the EUR
  branch to avoid mypy type conflicts with identically-named variables in the non-EUR
  path that carry different types (`Money` vs `Decimal`).
- `price_available=True` on `PriceUnavailableError` for EUR path (unlike non-EUR which
  returns `False`): EUR total is always self-consistent without a price check, so the
  form remains fully submittable.

### Out-of-scope items noticed
- (none — stayed within ticket scope)

### Tokens used (rough)
~60k

---

## 2026-05-07 20:18 — TICKET-024

**Surface:** ChatGPT Codex
**Model:** GPT-5
**Duration:** ~30 min
**Branch:** ticket-024-sell-simulator-cold-start
**PR:** https://github.com/vivekbhargava23/Investment-Dashboard-2/pull/29
**Status at session end:** MERGED

### What got done
- Added a 60-second Streamlit cache wrapper around sell simulator live-position computation, keyed by transaction IDs.
- Added a fallback to the existing uncached computation if Streamlit cache serialisation fails at runtime.
- Made yfinance search-result matching skip `fast_info` price enrichment; exact lookup still keeps the richer price path.
- Added unit coverage for sell simulator live-position cache reuse/invalidation and lightweight resolver search.

### Files touched
- `app/ui/components/sell_simulator.py` — `_live_positions_cached`; cached render path with fallback
- `app/adapters/yfinance_feed/yfinance_adapter.py` — optional `_build_match(fetch_price=False)` path for resolver search
- `tests/unit/ui/test_sell_simulator_component.py` — live-position cache-key tests
- `tests/unit/adapters/test_yfinance_adapter_caching.py` — resolver search avoids `yfinance.Ticker`
- `docs/TICKETS/TICKET-024-sell-simulator-cold-start.md` — status updates

### Tests
274 passing → 277 passing (3 new); 68 skipped
Full gate: `pytest && ruff check . && mypy app/ && lint-imports`

### Decisions made during the session
- Kept the live-position cache at the UI layer to preserve the service layer's stateless contract.
- Search results now omit `recent_price`; exact lookup remains the enrichment path for places that need detailed metadata.

### Out-of-scope items noticed
- Persistent live-price caching across Streamlit restarts remains deferred to the daily NAV/cache work noted in the ticket.

### Tokens used (rough)
~45k
*** End of File

---

## 2026-05-08 — TICKET-022a

**Surface:** Claude Code
**Model:** claude-sonnet-4-6
**Duration:** ~90 min
**Branch:** ticket-022a-chart-service-components
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- New `app/domain/market_data.py`: `ChartPeriod` StrEnum (9 periods + `is_intraday` property),
  `OhlcBar` frozen Pydantic model (OHLC integrity + positive-price + tz-aware validators),
  `OhlcSeries` frozen Pydantic model (`latest_close`, `period_change_pct` properties),
  `OhlcUnavailableError` exception.
- New `app/ports/market_data.py`: `OhlcDataProvider` Protocol.
- Extended `app/adapters/yfinance_feed/yfinance_adapter.py`: `_ohlc_cache`,
  `_interval_for_period`, `_ttl_for_period`, `get_ohlc_history` (15-min TTL intraday / 24h daily),
  bad-row skip with warning, `clear_cache()` extended.
- New `app/services/market_data.py`: module-level OHLC cache with TTL, `get_ohlc_history`,
  `clear_market_data_caches`. Documented deviation from stateless-service convention.
- New `app/ui/components/_chart_styles.py`: `CHART_BG`, `CANDLE_UP/DOWN`, `LINE_COLOR_DEFAULT`, `base_layout()`.
- New `app/ui/components/charts.py`: `render_candlestick`, `render_line_chart`, `render_sparkline`.
- Updated `app/ui/wiring.py`: `get_ohlc_data_provider()` singleton.
- Updated `app/domain/__init__.py`, `app/ports/__init__.py`: export new types.
- Updated `pyproject.toml`: added `pandas.*` to mypy `ignore_missing_imports` (pandas is already
  a dep via yfinance; direct import was new in this ticket).
- New `tests/fakes/ohlc.py`: `FakeOhlcDataProvider` with call counting and raise-for support.
- 41 new tests across 4 test files.

### Files touched
- `app/domain/market_data.py` — new
- `app/ports/market_data.py` — new
- `app/services/market_data.py` — new
- `app/ui/components/_chart_styles.py` — new
- `app/ui/components/charts.py` — new
- `app/adapters/yfinance_feed/yfinance_adapter.py` — extended with OHLC support
- `app/domain/__init__.py` — new exports
- `app/ports/__init__.py` — new export
- `app/ui/wiring.py` — get_ohlc_data_provider()
- `pyproject.toml` — pandas mypy ignore
- `tests/fakes/ohlc.py` — new
- `tests/unit/domain/test_market_data.py` — new (24 tests)
- `tests/unit/services/test_market_data.py` — new (8 tests)
- `tests/unit/adapters/test_yfinance_ohlc.py` — new (9 tests)
- `tests/unit/ui/test_chart_components.py` — new (5 tests)
- `docs/TICKETS/TICKET-022a-chart-service-and-components.md` — status → IN_REVIEW

### Tests
277 passing → 318 passing (41 new)

### Decisions made during the session
- `base_layout()` returns separate dicts for xaxis/yaxis (not a shared reference) to prevent
  mutations in `render_candlestick` (adding `rangeslider` to xaxis) from corrupting yaxis.
- `pandas` added to mypy `ignore_missing_imports` (was already a transitive dep via yfinance,
  now directly imported in the adapter for `pd.notna`).
- Session included rollback of ChatGPT Codex 022a/022b (PR #36, merged by Vivek) before reimplementation.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~120k

## 2026-05-08 14:00 — TICKET-022b

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~90 min
**Branch:** ticket-022b-research-page-overview-charts
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- New `app/ui/pages/research.py`: ticker searchbox + period selector (1D–YTD,
  default 6M), candlestick chart (height=500), header metrics row (latest price,
  period change pct, period label), Simulate buy handoff → simulator page, disabled
  watchlist button, quick-pick buttons for 5 example tickers.
- `app/ui/pages/overview.py`: Trend 30D column added to HTML table (text ↑/↓ + pct
  from 30D sparkline data); new Position Trends section below table using st.columns
  (one sparkline per position, actual Plotly charts, st.button per row); mini chart
  panel below (6-month line chart for selected ticker, Close button); per-ticker error
  isolation throughout.
- `app/ui/components/charts.py` (quality fixes discovered as first consumer):
  - `rangebreaks` added to x-axis for daily-bar charts → Sat/Sun gaps eliminated.
  - `render_line_chart` now uses dynamic y-range (min/max ± 5% margin) so price
    movements are visible regardless of absolute price level (no more $800 stock
    collapsing against zero baseline).
- `app/ui/components/sidebar.py`: 📈 Research added after Tax Dashboard.
- `app/ui/components/topbar.py`: "research" added to PAGE_TITLES.
- `tests/fakes/ticker_resolver.py`: FAKE_TICKER_NVDA and FAKE_TICKER_RHM constants added.
- 15 new tests: 6 research page smoke tests, 9 overview chart integration tests.
- Existing test updated: test_nav_items_consistency count 9→10 (Research added).

### Files touched
- `app/ui/pages/research.py` — new
- `app/ui/pages/overview.py` — trend column + sparklines + mini chart
- `app/ui/components/charts.py` — rangebreaks + dynamic y-range
- `app/ui/components/sidebar.py` — Research nav entry
- `app/ui/components/topbar.py` — Research page title
- `tests/unit/ui/test_research_page.py` — new (6 tests)
- `tests/unit/ui/test_overview_chart_integration.py` — new (9 tests)
- `tests/unit/ui/test_components.py` — count fix (9→10)
- `tests/fakes/ticker_resolver.py` — FAKE_TICKER_NVDA + FAKE_TICKER_RHM
- `docs/TICKETS/TICKET-022b-research-page-and-overview-charts.md` — IN_REVIEW

### Tests
318 passing → 333 passing (15 new)

### Decisions made during the session
- Sparklines rendered in separate st.columns section below the HTML table (not
  inside table cells, which is impossible with st.plotly_chart inside HTML strings).
  Trend 30D column in HTML table is text-based (↑/↓ + pct) for alignment; actual
  Plotly sparklines appear below the table.
- rangebreaks and dynamic y-range fixes to charts.py are in scope: this ticket is
  the first real consumer of those render functions, so rendering correctness issues
  are discovered and fixed here.
- Weekend gap fix applies only to non-intraday periods (daily bars); intraday data
  from yfinance already contains only market-hours bars.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~90k

---

## 2026-05-08 — TICKET-022b continuation — Overview chart overhaul + OHLC aggregation

**Ticket:** TICKET-022b (continuation of previous session)
**Surface:** Claude Code
**Model:** sonnet-4.6
**Branch:** ticket-022b-research-page-overview-charts
**PR:** #38
**Status at session end:** IN_REVIEW

### What got done
- `app/domain/market_data.py`: Added `AggregationFreq` type alias and
  `aggregate_ohlc_series()` — groups bars by calendar bucket (hour/day/week/month),
  producing one OHLC bar per bucket (open=first, high=max, low=min, close=last,
  volume=sum). Raises `OhlcUnavailableError` if no bars remain. Fixed mypy
  `tuple` type annotation to `tuple[int, ...]`.
- `app/services/market_data.py`: Added `_AGGREGATION` dict mapping each `ChartPeriod`
  to its aggregation freq (5D→day, 1Y/2Y→week, 5Y→month, YTD→week, others→None).
  Aggregation applied post-fetch before caching, so cached series are display-ready.
- `app/ui/components/charts.py`: Replaced static `not series.period.is_intraday`
  rangebreaks check with `_needs_weekend_rangebreaks()` heuristic (8h ≤ avg bar
  gap < 100h identifies daily bars; weekly/monthly bars skip rangebreaks to avoid
  x-axis compression).
- `app/ui/pages/overview.py`: Replaced all-sparklines section + mini chart panel
  with a single candlestick chart: `st.selectbox` for ticker, `st.radio` (1D–YTD,
  default 6M) for period, `render_candlestick` at height=400. Renamed
  `_fetch_sparklines` → `_fetch_trend_texts` (returns `dict[str, str]` only).
- New/updated tests: 8 `aggregate_ohlc_series` domain tests, 5 service-layer
  aggregation tests, 4 `_needs_weekend_rangebreaks` chart component tests.
  Rewrote `test_overview_chart_integration.py` (removed stale mini-chart color
  tests, updated to `_fetch_trend_texts` API).

### Files touched
- `app/domain/market_data.py` — aggregate_ohlc_series + AggregationFreq
- `app/services/market_data.py` — _AGGREGATION + service-layer aggregation
- `app/ui/components/charts.py` — _needs_weekend_rangebreaks heuristic
- `app/ui/pages/overview.py` — single candlestick chart replaces sparklines panel
- `tests/unit/domain/test_market_data.py` — 8 new aggregation tests
- `tests/unit/services/test_market_data.py` — 5 new aggregation tests
- `tests/unit/ui/test_chart_components.py` — 4 new _needs_weekend_rangebreaks tests
- `tests/unit/ui/test_overview_chart_integration.py` — rewritten for new API

### Tests
333 passing → 348 passing (15 new)

### Decisions made during the session
- Aggregation lives in the service layer (not UI), so the cache always holds
  display-ready data; aggregation cost is paid once per TTL, not per render.
- `_needs_weekend_rangebreaks` uses avg bar spacing rather than period label because
  after aggregation the period label (e.g. ONE_YEAR) no longer tells us whether bars
  are daily or weekly — the spacing does.
- Overview page uses same `_PERIOD_LABELS` dict pattern as research page for
  consistency; default period is SIX_MONTH (index=4) matching research page default.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~40k

---

## 2026-05-09 14:00 — TICKET-013

**Agent:** Claude Code (sonnet-4.6)
**Duration:** ~90 min
**Branch:** ticket-013-daily-nav-snapshot
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Added `DailyNavPoint` frozen Pydantic model in `app/domain/nav.py` with EUR-only and non-negative validators
- Added `NavSnapshotRepository` Protocol in `app/ports/nav_repository.py`
- Added `JsonNavSnapshotRepository` adapter in `app/adapters/repo_json/nav_repo.py` — atomic writes, schema v1, `clear()` deletes file
- Added `get_nav_series` service in `app/services/nav.py` — reconstructs historical NAV from OHLC/FX history, caches in nav_repo, today's NAV computed live and never persisted
- Added `clear_nav_cache(nav_repo)` service function called via `JsonTransactionRepository.save_all` on every save
- Wired `JsonTransactionRepository` constructor to accept optional `nav_repo`; wiring module creates real repo with nav_repo injected
- Added `FakeNavSnapshotRepository` in `tests/fakes/nav.py` for downstream analytics tests (A1–A5)

### Files touched
- `app/domain/nav.py` — new: DailyNavPoint model
- `app/ports/nav_repository.py` — new: NavSnapshotRepository Protocol
- `app/adapters/repo_json/nav_repo.py` — new: JsonNavSnapshotRepository
- `app/services/nav.py` — new: get_nav_series, clear_nav_cache, helpers
- `app/domain/__init__.py` — export DailyNavPoint
- `app/ports/__init__.py` — export NavSnapshotRepository
- `app/adapters/repo_json/__init__.py` — export JsonNavSnapshotRepository
- `app/adapters/repo_json/json_repo.py` — optional nav_repo injection; clear on save_all
- `app/config.py` — added nav_snapshots_json_path setting
- `app/ui/wiring.py` — added get_nav_snapshot_repo(); get_repository() now injects it
- `tests/fakes/nav.py` — new: FakeNavSnapshotRepository
- `tests/fakes/__init__.py` — export FakeNavSnapshotRepository
- `tests/unit/domain/test_nav.py` — new: 11 domain tests
- `tests/unit/services/test_nav.py` — new: 17 service tests
- `tests/integration/test_nav_repo.py` — new: 13 integration tests (skip without --run-integration)

### Tests
348 passing → 376 passing (28 new)

### Decisions made during the session
- `clear_nav_cache` takes a `NavSnapshotRepository` parameter (cleanest injectable design)
- `clear()` deletes the file entirely (simpler than zeroing it; same effect on next load)
- Trading days = union of all dates present in OHLC bars across all tickers in portfolio
- `_period_covering` picks smallest ChartPeriod to cover start→today for OHLC fetches
- `FlexibleFakeOhlcProvider` in tests ignores the period parameter (tests don't depend on internal period selection)
- Logging is used in the service as an explicit exception to the no-logging rule; missing OHLC data would silently corrupt NAV if not surfaced

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~80k

---

## 2026-05-09 — TICKET-A0

**Surface:** Claude Code
**Model:** sonnet-4.6
**Duration:** ~1 hr
**Branch:** ticket-A0-analytics-shell
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Created `app/domain/analytics.py` with eight pure stat primitives: `daily_returns`,
  `volatility_annualised`, `drawdown_series`, `max_drawdown`, `sharpe`, `sma`, `rsi`
  (Wilder smoothing), and `correlation_matrix`. Decimal arithmetic throughout; float
  used only internally in `correlation_matrix` for efficiency, with Decimal boundary.
- Created `app/ui/pages/analytics.py`: five-tab shell with `st.info` placeholders for
  TICKET-A1 through A5. No data fetches, no service imports, no state writes.
- Updated `app/ui/components/sidebar.py`: analytics entry relabelled to "📊 Analytics",
  repositioned after Tax Dashboard and before Research.
- Created `tests/unit/domain/test_analytics.py`: 46 tests covering happy paths,
  edge cases (empty, single, mismatched), ValueError raises, hypothesis-based invariant
  tests (drawdown ≤ 0, RSI in [0,100], correlation symmetry).
- Created `tests/unit/ui/test_analytics_page.py`: 4 smoke tests verifying tab labels,
  per-tab info messages, and header icon.
- Marked TICKET-013 as MERGED (it had merged before this session started).

### Files created
- `app/domain/analytics.py`
- `tests/unit/domain/test_analytics.py`
- `tests/unit/ui/test_analytics_page.py`

### Files modified
- `app/ui/pages/analytics.py` — rewritten from stub
- `app/ui/components/sidebar.py` — analytics entry updated + reordered
- `docs/PROJECT_STATE.md` — TICKET-A0 → IN_REVIEW
- `docs/SESSION_LOG.md` — this entry
- `docs/TICKETS/BACKLOG.md` — TICKET-013 MERGED, TICKET-A0 IN_REVIEW
- `docs/TICKETS/TICKET-A0-analytics-shell.md` — IN_REVIEW
- `docs/TICKETS/TICKET-013-daily-nav-snapshot.md` — MERGED

### Tests
376 passing → 426 passing (50 new)

### Decisions made during the session
- `correlation_matrix` uses float arithmetic internally (documented in docstring).
  Pure Decimal sqrt chains for matrix-scale inputs accumulate more error than a
  single float→Decimal boundary conversion.
- RSI returns `list[Decimal | None]` with first `period` entries as None (same
  convention as `sma`), not a shorter list. `len(closes) < period+1` → `[]`.
- Sidebar update: analytics moved after Tax Dashboard and before Research; all
  other existing entries retained to avoid navigation regressions.

### Out-of-scope items noticed
- (none)

---

## 2026-05-09 — TICKET-A1

**Agent:** GPT Codex (GPT-5)
**Duration:** ~2 hr
**Branch:** ticket-A1-performance-tab
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Added `app/services/analytics_performance.py` with `PerformancePeriod`,
  `PerformanceView`, benchmark mapping, NAV/benchmark date alignment, indexing to
  100, and KPI computation.
- Filled the Analytics Performance tab with period/benchmark selectors, KPI strip,
  indexed portfolio-vs-benchmark line chart, benchmark failure warning, empty state,
  and drawdown area chart.
- Extended chart components with `ChartSeries`, optional secondary line support,
  and `render_drawdown_chart`.
- Updated `render_metric_card` to apply value classes, support tooltips, and route
  HTML through `render_html`.
- Marked TICKET-A0 as MERGED on `main` before starting A1, after confirming PR #41
  was merged.

### Files touched
- `app/services/analytics_performance.py` — new performance-tab service/view model
- `app/ui/pages/analytics.py` — Performance tab implementation
- `app/ui/components/charts.py` — secondary line + drawdown chart support
- `app/ui/components/_chart_styles.py` — grey chart constant
- `app/ui/components/metric_card.py` — value classes, tooltips, render helper
- `tests/unit/services/test_analytics_performance.py` — new service tests
- `tests/unit/ui/test_performance_tab.py` — new Performance tab smoke tests
- `tests/unit/ui/components/test_charts_extension.py` — new chart extension tests
- `tests/unit/ui/test_analytics_page.py` — analytics shell expectations updated
- `docs/TICKETS/TICKET-A1-performance-tab.md` — IN_REVIEW

### Tests
426 passing → 449 passing (23 new)

### Decisions made during the session
- Current NAV service is a function, not a `NavService` class; A1 uses a small
  `NavSeriesProvider` Protocol and UI wiring wrapper instead of modifying the
  locked TICKET-013 surface.
- Added a lightweight `ChartSeries`/`ChartPoint` render model in the chart
  component because drawdown values can be zero or negative and cannot be modeled
  as `OhlcSeries` bars.
- Date alignment carries the previous benchmark close across short benchmark gaps
  only when the surrounding benchmark gap is at most 3 calendar days; longer gaps
  are dropped from both series.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~70k

---

## 2026-05-09 14:34 — TICKET-A5

**Agent:** GPT Codex (GPT-5)
**Duration:** ~1.5 hr
**Branch:** ticket-A5-concentration-tab
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Added Herfindahl concentration analytics and frozen Concentration view models.
- Added a Concentration service that computes Top-1, Top-3, HHI, sorted weights,
  native-currency exposure, rows, and stale-position handling from live positions.
- Implemented the Analytics Concentration tab with KPI cards, weight bar chart,
  currency donut, stale-data banner, empty state, and per-position table.
- Extracted the Live Overview weight bar into a shared component and migrated
  Overview to use it.
- Updated analytics shell tests to no-op the now-real A5 tab while keeping
  dedicated A5 coverage.
- Marked TICKET-A1 as MERGED on `main` before starting A5, after confirming PR #42
  was merged.

### Files touched
- `app/domain/analytics.py` — added `herfindahl_index`
- `app/domain/analytics_views.py` — new Concentration view models
- `app/services/analytics_concentration.py` — new Concentration service and constants
- `app/ui/pages/analytics.py` — Concentration tab implementation
- `app/ui/components/charts.py` — weight bar chart and currency donut renderers
- `app/ui/components/weight_bar.py` — shared weight-bar HTML component
- `app/ui/pages/overview.py` — migrated weight bar to shared component
- `tests/fixtures/concentration_fixtures.py` — reusable concentration fixtures
- `tests/unit/domain/test_herfindahl.py` — new domain tests
- `tests/unit/domain/test_analytics_views.py` — new view-model tests
- `tests/unit/services/test_analytics_concentration.py` — new service tests
- `tests/unit/ui/test_weight_bar_component.py` — new component tests
- `tests/unit/ui/components/test_concentration_charts.py` — new chart tests
- `tests/unit/ui/test_concentration_tab.py` — new tab tests
- `tests/unit/ui/test_analytics_page.py` — shell tests adjusted for real A5 tab

### Tests
449 passing → 482 passing (33 new)

### Decisions made during the session
- Kept `MAX_POSITION_WEIGHT_PCT` and related KPI thresholds in
  `analytics_concentration.py` as specified, so A4 can import them.
- Stale positions are retained in Concentration rows but contribute zero to
  weights and currency split.
- Generic analytics shell tests patch `_render_concentration_tab`; dedicated A5
  tests cover the real Concentration layout.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~65k

---

## 2026-05-09 14:49 — TICKET-A4

**Agent:** GPT Codex (GPT-5)
**Duration:** ~1 hr
**Branch:** ticket-A4-position-sizer-tab
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Added pure domain sizing formulas for risk-based and target-weight share calculations.
- Extended analytics view models with frozen Position Sizer models.
- Added a Position Sizer service that computes current-position, risk-based, weight-based, and post-trade weight preview results from live positions.
- Implemented the Analytics Position Sizer tab with ticker/direction controls, sizing inputs, result cards, empty/degraded states, and A5 weight-bar reuse.
- Marked TICKET-A5 as MERGED on `main` before starting A4, after confirming PR #43 had merged.

### Files touched
- `app/domain/sizing.py` — new pure sizing formulas
- `app/domain/analytics_views.py` — added Sizer view models
- `app/domain/__init__.py` — exported Sizer view models
- `app/services/analytics_sizer.py` — new Position Sizer service and FX helper
- `app/ui/pages/analytics.py` — Position Sizer tab implementation
- `tests/unit/domain/test_sizing.py` — new domain sizing tests
- `tests/unit/domain/test_analytics_views.py` — Sizer model tests
- `tests/unit/services/test_analytics_sizer.py` — service tests
- `tests/unit/ui/test_sizer_tab.py` — UI tab tests
- `tests/unit/ui/test_analytics_page.py` — analytics shell expectations updated

### Tests
482 passing → 523 passing (41 new)

### Decisions made during the session
- Kept share math unrounded in domain/service models; display continues through `format_shares`.
- Used `LivePosition.model_construct` only in one service test to exercise the planned stale-price warning path, because the current `LivePosition` model only validates fully live or missing-price states.
- Reused A5's cached live-position helpers in the Analytics page rather than adding another Streamlit cache path.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~45k

---

## 2026-05-09 21:24 — TICKET-A2

**Agent:** GPT Codex (GPT-5)
**Duration:** ~1.5 hr
**Branch:** ticket-A2-analytics-correlation
**PR:** _pending_
**Status at session end:** IN_REVIEW

### What got done
- Added pure connected-component correlation cluster detection to `app/domain/analytics.py`.
- Added the Correlation service with frozen view models, live-position universe selection, insufficient-history skipping, trading-date intersection, average-correlation computation, and diversification buckets.
- Implemented the Analytics Correlation tab with 30D/60D/90D window selector, skipped-history warning, Plotly heatmap, sortable average-correlation table, and cluster warnings.
- Added the correlation heatmap renderer and diverging Plotly colorscale.
- Marked TICKET-A4 as MERGED on `main` before starting A2, after confirming PR #45 had merged.

### Files touched
- `app/domain/analytics.py` — added `correlation_clusters`
- `app/services/analytics_correlation.py` — new Correlation service and view models
- `app/ui/pages/analytics.py` — Correlation tab implementation
- `app/ui/components/charts.py` — correlation heatmap renderer
- `app/ui/components/_chart_styles.py` — correlation colorscale
- `tests/unit/domain/test_analytics.py` — cluster tests
- `tests/unit/services/test_analytics_correlation.py` — service tests
- `tests/unit/ui/test_correlation_tab.py` — tab tests
- `tests/unit/ui/components/test_correlation_heatmap.py` — heatmap tests
- `tests/unit/ui/test_analytics_page.py` — shell expectations updated

### Tests
523 passing → 547 passing (24 new)

### Decisions made during the session
- Used connected components for cluster warnings exactly as specified; the warning text stays conservative rather than implying strict cliques.
- The service treats a single included ticker as a valid one-by-one matrix but leaves average correlation empty because there are no peers.
- The heatmap colorscale uses Plotly's normalized `[-1, 1]` range, with correlation 0.5 anchored at the neutral point.

### Out-of-scope items noticed
- (none)

### Tokens used (rough)
~55k

### Follow-up (2026-05-09) — layout cleanup on same PR
Post-review layout fixes applied to `ticket-A2-analytics-correlation` (no new ticket):
- Vertical full-width stack: heatmap → avg-correlation table. Removed two-column layout.
- Section headings: `st.subheader("Pairwise correlation")` above controls; `st.subheader("Average correlation to portfolio")` above table.
- Controls row: window radio (3/4 width) + compact color-scheme selectbox (1/4 width, labels "1"–"4", full names in `help=` tooltip).
- Expander replaced with `st.popover("ⓘ")` next to the avg-correlation table heading.
- KPI strip (Mean ρ, Highest Pair, Lowest Pair, Clusters) stays between controls and heatmap.
- Deleted `_render_correlation_side_panel`; help text promoted to module-level `_CORRELATION_HELP_TEXT` constant.
- Updated `_correlation_colorscale` to use short code lookup ("1"→"4") instead of full name strings.
- Updated three UI unit tests to match new layout (popover instead of expander, `[10,1]` columns, code-based color scheme).

### Follow-up (2026-05-09) — polish round 2 on same PR
Further polish applied to `ticket-A2-analytics-correlation` (same branch, no new ticket):
- Color scheme picker relocated: selectbox removed from controls row; replaced with a `st.popover("🎨")` icon below the heatmap, containing a `st.radio` keyed to `correlation_color_scheme` session state.
- Color schemes consolidated: replaced the 4-option code-based list with a 3-entry `CORRELATION_COLORSCALES` dict in `_chart_styles.py` (Diverging, Financial, Sequential). Default is "Financial (red–neutral–green)".
- `CHART_AXIS_LABEL_COLOR = "#374151"` added to `_chart_styles.py` for readable dark-text axis labels.
- Heatmap axis labels: `tickfont` updated to `{"size": 12, "color": CHART_AXIS_LABEL_COLOR}` on both axes; `tickangle` changed from -45° to -30°.
- Avg-correlation table: `st.dataframe` + pandas Styler replaced with `render_html()` HTML table using CSS badge classes `.diversification-badge.high|moderate|low|very-low`.
- CSS: added `--orange` / `--orange-bg` variables and `.diversification-badge.*` rules to `dark.css`.
- Updated 3 UI unit tests: import changed to `CORRELATION_COLORSCALES`, `render_html` patched in place of `st.dataframe`, sort-order test rewired to assert HTML content ordering.
