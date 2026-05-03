# TICKET-007 — Streamlit shell + dark CSS theme + sidebar/topbar/page placeholders

**Status:** MERGED
**Priority:** P1
**Estimated session length:** 2 – 2.5 hr
**Drafted by:** Vivek + Claude (chat 2026-05-03)
**Implemented by:** _pending_
**Depends on:** TICKET-000 (scaffolding) — no functional dependencies on TICKETs 001–006, this ticket is purely visual scaffolding
**Reference design:** `Investment_Dashboard.html` mockup (committed at `docs/reference/Investment_Dashboard.html` — see Notes section "Where the reference HTML lives")

---

## Problem

We have a backend (domain, FIFO, repository, valuation service) but no UI. Before any page wires real data, we need the **visual shell**: sidebar, topbar, dark theme, page-routing skeleton, reusable components. Building this in isolation from the data layer is deliberate — it lets us verify "does the styling work?" independently from "does the data flow work?", which means two independent debug sessions instead of one tangled one.

This ticket builds the shell to the visual fidelity of the user's HTML mockup, with all 8 nav items present (one of them, Analytics & Risk, is reserved for future implementation in TICKET-019). Every page is a placeholder for now; later tickets replace placeholders with real content.

After this ticket lands, you can run `streamlit run app/ui/main.py`, click between pages, see the sidebar highlight the active page, and the page changes — all with the dark theme of the reference mockup. No real data anywhere.

---

## Architectural decisions implemented by this ticket

These were decided in the chat session 2026-05-03:

1. **Single-page app with custom routing**, not Streamlit's native multi-page (`pages/` folder). Reason: the mockup's sidebar (with section labels, icons, badges, custom styling) cannot be reproduced inside Streamlit's auto-generated nav. We use `st.session_state.current_page` as the router. Each "page" is a Python module exposing `render()`.

2. **Visual scaffolding only — no data wiring.** Pages are placeholders that show "Coming in TICKET-XXX." The KPI tiles, positions table, charts, etc., come in later tickets. This separation is the entire point of having a separate ticket for the shell.

3. **Streamlit's default chrome is hidden via CSS.** The Streamlit header, footer, "Deploy" button, hamburger menu, and various overlays are all hidden so the app looks like the mockup, not a Streamlit demo. The hiding rules are documented inline so future Streamlit upgrades have a known checklist.

4. **`oklch()` color space is preserved from the mockup.** Modern color space, perceptually uniform, supported by all current browsers. Matches the design exactly.

5. **Sidebar Unicode glyphs match the mockup.** Icons are `◉ ⬡ ↗ § ▲ ◎ ≡ ⚙` — small monochrome glyphs that look professional and don't depend on an icon library. No emoji, no FontAwesome, no extra dependencies.

6. **Sidebar badges are static placeholders for now.** The "3 flags" badge on Decision Gates and the "new" badge on Analytics & Risk are hardcoded strings in this ticket. Future tickets (010, 016) will compute these dynamically.

7. **Refresh button in the topbar is a no-op for now.** It triggers `st.rerun()` and nothing else. Real refresh logic (calling `service.clear_caches()` + `st.cache_data.clear()`) lands in TICKET-008 when the data layer is wired in.

8. **The Analytics & Risk page exists as a placeholder navigation slot.** A new TICKET-019 entry is added to the BACKLOG so this page's implementation is tracked but deferred to Phase 4. The sidebar shows it from day one to lock in the layout.

---

## Acceptance criteria

### Streamlit chrome hiding (CSS rules)

- [ ] In `app/ui/styles/dark.css`, include explicit hiding rules with a comment block titled `/* === Hide Streamlit default chrome === */`. Each rule has a comment explaining which Streamlit element it targets:
  - `[data-testid="stHeader"] { display: none; }` — top Streamlit header bar
  - `[data-testid="stToolbar"] { display: none; }` — Deploy + hamburger toolbar
  - `[data-testid="stDecoration"] { display: none; }` — colored bar on the very top
  - `[data-testid="stStatusWidget"] { display: none; }` — running/stop indicator
  - `footer { display: none; }` — "Made with Streamlit" footer
  - `#MainMenu { visibility: hidden; }` — old hamburger menu (legacy)
  - Block selector: `.stApp` should have `padding: 0; background: var(--bg);`
- [ ] Document at the top of `dark.css` in a comment: "Tested with Streamlit X.Y. If chrome reappears after a Streamlit upgrade, inspect the DOM and add the new selector here."

### Color tokens and theme variables

- [ ] `app/ui/styles/dark.css` has the full set of CSS variables ported from the reference HTML, in `:root`:
  - `--bg`, `--surface`, `--surface2`, `--border`, `--border2`
  - `--text`, `--text2`, `--text3`
  - `--green`, `--green-bg`, `--red`, `--red-bg`, `--amber`, `--amber-bg`, `--blue`, `--blue-bg`
  - `--accent` (= green)
  - `--nav-w` = `220px`
- [ ] All values use `oklch(...)` exactly as in the reference. Do not convert to hex.

### Typography

- [ ] Google Fonts loaded via `@import` at the top of `dark.css`:
  - `DM Sans` weights 300, 400, 500, 600
  - `DM Mono` weights 400, 500
- [ ] Body uses `'DM Sans', sans-serif`; numeric/code uses `'DM Mono', monospace`. Defined as utility classes in CSS (`.font-mono`).

### `app/ui/main.py` — single-page entry

- [ ] Imports: `streamlit`, the sidebar/topbar components, the page modules.
- [ ] At the top: `st.set_page_config(page_title="Investment Panel", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")`. Wide layout is required to match the mockup's two-column body.
- [ ] After page config, load CSS via a helper:
  ```python
  def load_css() -> None:
      with open("app/ui/styles/dark.css") as f:
          st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
  load_css()
  ```
- [ ] Initialize `st.session_state.current_page` to `"overview"` if not present.
- [ ] Define `PAGE_REGISTRY: dict[str, callable]` mapping page id → `render` function.
- [ ] Layout:
  - Use `st.columns([0.18, 0.82])` for sidebar and main, OR use `unsafe_allow_html` to render a custom `<div class="root">` flex container that wraps both. **Prefer the flex container approach** — it matches the mockup exactly. Streamlit columns have padding/borders we can't fully control.
  - Render sidebar via `render_sidebar()` (component imported from `app.ui.components.sidebar`).
  - Render main pane: topbar via `render_topbar()`, then `PAGE_REGISTRY[st.session_state.current_page]()`.
- [ ] Run with: `streamlit run app/ui/main.py`. Confirms manually during the session that all 8 pages route correctly.

### `app/ui/components/sidebar.py`

- [ ] Module-level constants:
  ```python
  NAV_ITEMS: list[dict] = [
      {"id": "overview",    "label": "Live Overview",      "icon": "◉", "badge": None},
      {"id": "analytics",   "label": "Analytics & Risk",   "icon": "⬡", "badge": {"text": "new",     "color": "amber"}},
      {"id": "performance", "label": "Performance",        "icon": "↗", "badge": None},
      {"id": "tax",         "label": "Tax Dashboard",      "icon": "§", "badge": None},
      {"id": "decision",    "label": "Decision Gates",     "icon": "▲", "badge": {"text": "3 flags", "color": ""}},
      {"id": "behaviour",   "label": "Behavioural Ledger", "icon": "◎", "badge": None},
      {"id": "lots",        "label": "Lot Ledger",         "icon": "≡", "badge": None},
      {"id": "manage",      "label": "Manage Portfolio",   "icon": "⚙", "badge": None},
  ]
  ```
  These match the reference HTML exactly.
- [ ] `render_sidebar()` function:
  - Renders the brand block: icon `📈`, name "Investment Panel", sub "Scalable Capital · DE". CSS class `.sidebar-logo`.
  - Renders a "Portfolio" section label, then the first 7 NAV_ITEMS as buttons (excluding `manage`).
  - Renders a "Settings" section label, then the `manage` item.
  - Footer: live-dot + "Live prices" + today's date (use `date.today().isoformat()`). CSS class `.sidebar-footer`.
- [ ] Each nav button:
  - Uses `st.button` for the click handler.
  - The button's label includes the icon and label glyph.
  - When clicked: sets `st.session_state.current_page = item.id` and calls `st.rerun()`.
  - The currently-active button has the `.active` CSS class — this requires a CSS hack since Streamlit doesn't let us set arbitrary classes on buttons. Use the `st.button(...)` inside an HTML wrapper trick, OR (preferred) render the entire sidebar as a single `st.markdown(unsafe_allow_html=True)` block where buttons are `<a href="?page=X">` links and we read query params.
  - **Implementation guidance:** start with the `st.button` approach for correctness, even if styling is imperfect. If active-state styling is impossible with native buttons, switch to the `<a>` + query param approach. Document the choice with a comment.
- [ ] Badges next to nav items: small pill on the right side. Color class from `badge.color` (`amber`, `red`, `blue`, or empty for default neutral).

### `app/ui/components/topbar.py`

- [ ] Module-level `PAGE_TITLES: dict[str, str]` matching the reference HTML.
- [ ] `render_topbar()` function:
  - Reads `st.session_state.current_page`.
  - Renders an `<h1>` with the title from `PAGE_TITLES`.
  - Renders meta line: "USD/EUR 1.0786 · 14:14" — these are **hardcoded placeholders** for now. A comment explains: "Replaced with live data in TICKET-008."
  - Renders Refresh button. On click: calls `st.rerun()`. A comment: "Real refresh logic (clear adapter + Streamlit caches) added in TICKET-008."
- [ ] All inside a `<div class="topbar">` container styled to match the mockup.

### `app/ui/pages/` — eight placeholder modules

Each is a Python module under `app/ui/pages/` exposing one function: `render() -> None`.

- [ ] `app/ui/pages/__init__.py` — empty
- [ ] `app/ui/pages/overview.py` — `render()` shows: an `<h2>Live Overview</h2>` and `st.info("Live Overview UI coming in TICKET-008")`.
- [ ] `app/ui/pages/analytics.py` — placeholder with `st.info("Analytics & Risk UI deferred to TICKET-019 (Phase 4)")`.
- [ ] `app/ui/pages/performance.py` — placeholder for TICKET-014.
- [ ] `app/ui/pages/tax.py` — placeholder for TICKET-011.
- [ ] `app/ui/pages/decision.py` — placeholder for TICKET-017.
- [ ] `app/ui/pages/behaviour.py` — placeholder for TICKET-018.
- [ ] `app/ui/pages/lots.py` — placeholder for TICKET-015.
- [ ] `app/ui/pages/manage.py` — placeholder for TICKET-009.

Each placeholder is ~5 lines. Their purpose is to verify routing works.

### `app/ui/format.py` — shared formatting helpers

- [ ] `format_eur(money: Money, signed: bool = False) -> str` — German format: `"€25.045,38"` (period thousands, comma decimal). For `signed=True`, prepend `+` for positive: `"+€4.003,60"`.
- [ ] `format_pct(value: Decimal, signed: bool = False) -> str` — `"19.0%"` or `"+19.0%"`. Always one decimal place.
- [ ] `format_shares(value: Decimal) -> str` — `"12,5000"` (4 dp, comma decimal).
- [ ] `format_date(value: date) -> str` — ISO `"2026-05-02"`.
- [ ] `gain_class(value: Decimal) -> str` — returns CSS class name: `"gain-positive"` if `> 0`, `"gain-negative"` if `< 0`, `"gain-neutral"` if `== 0`. The CSS classes are defined in `dark.css` mapping to `--green`, `--red`, `--text2` respectively.
- [ ] All functions are pure — no I/O, no streamlit, no state. Tested in isolation (see Tests section).

### `app/ui/components/metric_card.py` — KPI tile component

- [ ] `render_metric_card(label: str, value: str, subtitle: str | None = None, value_class: str | None = None, progress_pct: float | None = None) -> None`:
  - Renders a single KPI tile matching the mockup.
  - `label` — small grey caps label at top
  - `value` — large bold number
  - `subtitle` — small line beneath, optional
  - `value_class` — CSS class to apply to the value (e.g., `"gain-positive"`)
  - `progress_pct` — if set, render a progress bar at the bottom (used by Sparerpauschbetrag tile)
- [ ] All HTML rendered via `st.markdown(unsafe_allow_html=True)` for full styling control.
- [ ] **No data dependency in this ticket.** The function exists with the right API. TICKET-008 calls it with real data.

### `app/ui/components/badges.py` — thesis/severity pills

- [ ] `render_thesis_badge(status: Literal["intact", "watch", "broken"]) -> str` — returns an HTML string (not rendered directly) that can be embedded in tables or other markdown contexts. Color classes map: `intact` → green, `watch` → amber, `broken` → red.
- [ ] `render_severity_badge(severity: Literal["low", "med", "high"]) -> str` — same pattern.
- [ ] Returns string, not None — so callers can compose pills inside larger HTML blocks (e.g., the future positions table).

### Reference HTML committed for future tickets

- [ ] Move/copy the user's mockup file to `docs/reference/Investment_Dashboard.html`. This is the canonical visual reference for all later UI tickets. Add a `docs/reference/README.md` explaining: "This is the design reference. Do not run it. Use it for visual specification of the dark theme, KPI tile layouts, page composition. The Streamlit implementation lives in `app/ui/`."

### Tests

#### `tests/unit/ui/__init__.py`
- [ ] Empty init.

#### `tests/unit/ui/test_format.py` — pure formatting helpers
- [ ] `format_eur(Money(Decimal("25045.38"), EUR))` → `"€25.045,38"`
- [ ] `format_eur(Money(Decimal("4003.60"), EUR), signed=True)` → `"+€4.003,60"`
- [ ] `format_eur(Money(Decimal("-150.00"), EUR), signed=True)` → `"-€150,00"` (negative sign, not `+-`)
- [ ] `format_eur(Money(Decimal("0"), EUR))` → `"€0,00"`
- [ ] `format_pct(Decimal("19.0"))` → `"19.0%"`
- [ ] `format_pct(Decimal("19.0"), signed=True)` → `"+19.0%"`
- [ ] `format_pct(Decimal("-21.8"), signed=True)` → `"-21.8%"`
- [ ] `format_shares(Decimal("12.5"))` → `"12,5000"`
- [ ] `format_shares(Decimal("120.0000"))` → `"120,0000"`
- [ ] `format_date(date(2026, 5, 2))` → `"2026-05-02"`
- [ ] `gain_class(Decimal("100"))` → `"gain-positive"`
- [ ] `gain_class(Decimal("-100"))` → `"gain-negative"`
- [ ] `gain_class(Decimal("0"))` → `"gain-neutral"`

#### `tests/unit/ui/test_components.py` — light component smoke tests
Components are hard to test in Streamlit because rendering writes to the Streamlit context. We don't try to test rendering output. We test:
- [ ] `render_thesis_badge("intact")` returns a string containing `"intact"` and `"green"` (the CSS class).
- [ ] `render_thesis_badge("watch")` contains `"amber"`.
- [ ] `render_thesis_badge("broken")` contains `"red"`.
- [ ] `render_thesis_badge("invalid")` raises `ValueError`.
- [ ] Same set for `render_severity_badge`.
- [ ] `NAV_ITEMS` from sidebar module has exactly 8 entries with required keys: `id`, `label`, `icon`, `badge`.
- [ ] All `NAV_ITEMS[*].id` values are present as keys in `PAGE_TITLES`.
- [ ] Every page id has a corresponding `render` function in `app.ui.pages` (introspect, don't import-and-call to avoid Streamlit context issues).

#### Manual visual review (documented, not automated)
- [ ] In the PR description, Claude Code includes a small manual checklist that Vivek will verify after merging:
  - [ ] App opens to Live Overview
  - [ ] All 8 nav items visible in sidebar with icons + Settings section break
  - [ ] "3 flags" badge on Decision Gates, "new" badge on Analytics & Risk
  - [ ] Active page highlighted in sidebar
  - [ ] Topbar shows page title that updates with nav clicks
  - [ ] Refresh button reloads (no error)
  - [ ] Streamlit default chrome (header, footer, "Deploy") not visible
  - [ ] Dark theme applied: bg `oklch(0.13 ...)`, no white flashes
  - [ ] Fonts: DM Sans loads (verify in browser dev tools)
  - [ ] No console errors

These are not pytest tests — they're a checklist Vivek runs manually because Streamlit's rendering can't be unit-tested headlessly without significant fixture work that's not worth it for a personal app.

### Lints / quality
- [ ] `pytest` — all unit tests pass
- [ ] `ruff check .` — passes
- [ ] `mypy app/` — passes; UI layer is checked under standard mode (not strict — Streamlit's untyped API would flood it)
- [ ] `lint-imports` — passes; specifically:
  - `app.ui.*` imports from `app.services.*`, `app.domain.*`, `app.ui.components.*`, `app.ui.format` only
  - `app.ui.*` does NOT import from `app.adapters.*`, `app.ports.*`, or any external service directly

### State updates (per CLAUDE.md session-end ritual)
- [ ] `docs/SESSION_LOG.md` appended
- [ ] `docs/PROJECT_STATE.md` updated (TICKET-007 → IN_REVIEW)
- [ ] `docs/TICKETS/BACKLOG.md` updated (TICKET-007 row → IN_REVIEW; new TICKET-019 row added in Phase 4)
- [ ] Ticket file `Status: IN_REVIEW`
- [ ] PR opened via `gh pr create --fill --base main`

---

## Files created

```
app/ui/main.py
app/ui/styles/dark.css
app/ui/format.py
app/ui/components/__init__.py
app/ui/components/sidebar.py
app/ui/components/topbar.py
app/ui/components/metric_card.py
app/ui/components/badges.py
app/ui/pages/__init__.py
app/ui/pages/overview.py
app/ui/pages/analytics.py
app/ui/pages/performance.py
app/ui/pages/tax.py
app/ui/pages/decision.py
app/ui/pages/behaviour.py
app/ui/pages/lots.py
app/ui/pages/manage.py
docs/reference/Investment_Dashboard.html       ← copy of the mockup
docs/reference/README.md
tests/unit/ui/__init__.py
tests/unit/ui/test_format.py
tests/unit/ui/test_components.py
```

## Files modified

```
app/ui/__init__.py              ← may need empty/stub
docs/TICKETS/BACKLOG.md         ← TICKET-007 → IN_REVIEW; add TICKET-019 (Analytics & Risk)
```

---

## Out of scope

- **Real data wiring on any page** — every page is a placeholder. TICKET-008 wires Live Overview.
- **Refresh button behaviour beyond `st.rerun()`** — TICKET-008 makes it actually clear caches.
- **Topbar's live FX rate and time** — hardcoded placeholders. TICKET-008 makes them dynamic.
- **Dynamic sidebar badges** — "3 flags" is a hardcoded string. TICKET-016/017 wires it to real flag counts.
- **The Analytics & Risk page implementation** — placeholder slot only. TICKET-019 (deferred to Phase 4) builds it out.
- **Mobile responsive behavior** — desktop-only. The mockup is desktop, our use case is desktop, no breakpoint complexity.
- **Light mode** — dark only. The mockup is dark.
- **Charts of any kind** — no Plotly, no Recharts equivalent. TICKETs 008, 014 add charts where needed.
- **Forms** (add transaction, edit transaction) — TICKET-009.
- **Tables of real data** — every later ticket has its own table.

---

## Notes (architectural and methodological — for future AI sessions)

### Where the reference HTML lives

The user's mockup `Investment_Dashboard.html` is the visual spec for the entire app. It is committed to `docs/reference/` so:
1. Every future UI ticket can reference exact pixel values, color tokens, layout specs.
2. If Streamlit's behaviour drifts and we need to switch frameworks (FastAPI + React), we have the full design.
3. New AI sessions (Claude Code, Claude Chat, future you) can open it in a browser to see the target.

The HTML file is reference-only. Do not modify it. Do not run it as part of the app. Do not import its JavaScript (it uses React + Recharts; we use Streamlit + Plotly).

### Why custom routing instead of Streamlit's pages/

Streamlit's native multi-page nav uses a folder convention (`pages/01_foo.py`) and renders its own sidebar that we cannot fully style. The mockup's sidebar has:
- Section labels ("Portfolio", "Settings")
- Custom icons (Unicode glyphs)
- Color-coded badges
- An active-state highlight matching the dark theme
- A footer with live status

None of these are achievable with the auto-generated Streamlit nav without aggressive CSS hacks that break across Streamlit versions. Custom routing via `st.session_state.current_page` is ~30 lines, fully under our control, and version-stable.

### Why the chrome-hiding rules are documented inline

Streamlit's internal DOM (`data-testid` attributes, etc.) changes occasionally between major versions. When a Streamlit upgrade reveals previously-hidden chrome, the fix is to inspect the DOM, find the new selector, and add it to `dark.css`. Documenting WHICH selector hides WHICH element gives future maintainers a checklist instead of a mystery.

### Why oklch is preserved

`oklch()` is a perceptually uniform color space. It produces colors that look more consistent across the lightness spectrum than `hsl` or `hex`. The reference design uses it for a reason — converting to hex would visibly degrade some colors. Browser support is universal in modern Chrome/Safari/Firefox (the targets for a desktop dev tool). No conversion.

### Why a single CSS file, not Tailwind

The mockup uses one stylesheet. Tailwind would require adding a build step (PostCSS, JIT compilation) which fights with Streamlit's "edit Python file, see browser refresh" loop. One CSS file with hand-written rules is simpler, faster, and matches the mockup exactly.

### How later tickets extend this shell

When TICKET-008 wires the Live Overview, it:
1. Imports the existing `format_eur`, `format_pct`, etc.
2. Imports `render_metric_card` and calls it with real values.
3. Imports services from `app.services.valuation`.
4. Replaces the placeholder content of `app/ui/pages/overview.py` with real logic.

The shell does not change. Each later page-ticket follows this pattern.

### Styling discipline

- All CSS lives in `dark.css`. Components do not inline styles via `style=...` unless absolutely necessary (and never for color tokens — always use vars).
- No styling logic in Python. Python decides which CSS class to apply (via `gain_class()` etc.); CSS decides what the class means.
- New components add new CSS classes; they do not modify existing ones unless the modification is the point of the ticket.

### Why NAV_ITEMS is a module constant, not configuration

The mockup defines exactly 8 nav items. They are not user-customizable, they are not feature-flagged, they are not stored in a database. A frozen list in a Python module is the right level of abstraction. If we ever need dynamic nav (we won't, for a single-user personal tool), refactor then.

### Methodology note (for future AI sessions reading this)

This ticket is the first UI ticket and establishes patterns reused by every later UI ticket:
- Pages live in `app/ui/pages/<name>.py` with a `render()` function
- Components live in `app/ui/components/<name>.py`
- Formatting helpers live in `app/ui/format.py`
- All styling lives in `app/ui/styles/dark.css`
- Custom routing via `st.session_state.current_page`

Future UI tickets reference this ticket and follow these patterns rather than re-deriving them. The ticket is verbose because it sets the precedent; later UI tickets will be much shorter.
