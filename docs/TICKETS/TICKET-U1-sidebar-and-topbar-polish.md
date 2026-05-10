# TICKET-U1 — Sidebar and topbar visual polish

**Status:** IN_REVIEW
**Priority:** P1
**Estimated session length:** 90 min
**Drafted by:** Vivek + Claude (chat session 2026-05-09)
**Implemented by:** _pending_

---

## Problem

The current sidebar and topbar have accumulated visual debt. Concrete defects
visible in the running app (verified against screenshots taken 2026-05-09):

**Sidebar:**
1. **Ghost rows.** Two empty/blank rows appear directly below the "Analytics"
   nav entry. The user reports additional ghost rows elsewhere in the sidebar
   too (notably below "Tax Dashboard"). These are blank Streamlit elements
   leaking through — they have no label, no icon, no link.
2. **Every nav item is underlined.** Streamlit's default `<a>` styling is not
   being suppressed. Every link looks "active" because every link is underlined.
3. **Active state is too pale.** The soft green pill on the active entry
   (`Analytics` in the screenshot) is barely distinguishable from the
   surrounding underlined inactive entries.
4. **Inconsistent vertical rhythm.** Gaps between entries are uneven — some
   pairs are tight, others have ~2× spacing. There's no consistent padding rule.
5. **No section grouping.** Ten entries are presented as a single flat list
   except for a `SETTINGS` label at the bottom. The user wants the entries
   grouped into three labelled sections (see "Acceptance criteria #4" below).
6. **Brand block is cramped and over-specific.** Currently shows
   "Investment Panel" + "Scalable Capital · DE". The "Scalable Capital · DE"
   sub-line must be removed entirely (broker name should not appear in chrome).
   The brand mark icon needs to sit cleanly against the title.
7. **No footer.** The reference design has a "Live prices · YYYY-MM-DD" footer
   strip at the bottom of the sidebar with a pulsing green dot. Currently absent.

**Topbar:**
8. **Double titling.** The topbar shows "Analytics & Risk" (h1, large) and the
   page content immediately below shows another large title like "📊 Analytics"
   with a subtitle. This is the same information shown twice in two different
   visual treatments.
9. **Topbar spacing is loose.** Page title, FX/time meta, and Refresh button
   don't sit at consistent baselines.

---

## Acceptance criteria

### Sidebar — structure

- [ ] **#1 — No ghost rows.** No blank, empty, or unlabelled rows appear
      anywhere in the sidebar in any page state. Verified by visual inspection
      on every page (Live Overview, Performance, Tax Dashboard, Analytics,
      Research, Sell Simulator, Lot Ledger, Decision Gates, Behavioural Ledger,
      Manage Portfolio). Add a regression test that asserts the rendered
      sidebar HTML contains exactly `len(NAV_ITEMS)` `nav-item` elements and
      no empty `<div>` or `<p>` placeholders between them.

- [ ] **#2 — Three labelled sections.** Sidebar nav items are grouped under
      three uppercase muted section labels in this exact order:

      ```
      PORTFOLIO
        ◉  Live Overview
        ↗  Performance
        §  Tax Dashboard
        ⬡  Analytics & Risk
        📈 Research

      TOOLS
        ⚡ Sell Simulator
        ≡  Lot Ledger
        ▲  Decision Gates       [3 flags badge if applicable]
        ◎  Behavioural Ledger

      SETTINGS
        ⚙  Manage Portfolio
      ```

      Section labels use the styling `.nav-section-label` from the reference
      (10px, 600 weight, 0.08em letter-spacing, uppercase, muted text colour,
      10px-10px-4px padding). The first label has no top margin; subsequent
      labels get `margin-top: 12px`.

      Existing icons may be retained where present (e.g. `📈` for Research);
      otherwise use the unicode symbols listed above. **Do not** introduce
      coloured emoji icons beyond what's already in the codebase — the
      reference uses monochrome unicode glyphs deliberately.

- [ ] **#3 — Brand block.** Top of sidebar shows a brand block with:
      - A 28px square mark with the accent colour (the project's existing
        green) as background, white emoji icon (`📈` is fine — match existing).
      - "Investment Panel" as the title (13px, 600 weight, 0.01em
        letter-spacing).
      - **No subtitle.** No "Scalable Capital · DE", no broker reference, no
        country code. The brand block ends after the title.
      - Bottom border separating the brand block from the nav.

- [ ] **#4 — Active state.** The active nav item has a clearly distinguishable
      treatment: tinted pill background (use `var(--accent-bg)` or equivalent
      light-theme tint of the green), green text, 550 weight. Inactive items
      have no background, no underline, muted text colour, 450 weight, and
      darken to full text colour on hover.

- [ ] **#5 — No underlines.** No nav-item link is underlined in any state
      (default, hover, active, focus, visited). This applies to both Streamlit
      `st.page_link` rendering (if used) and any custom HTML links.
      Implementation hint: add a CSS rule scoped to `.sidebar a { text-decoration: none; }`
      and confirm via a unit test that asserts the rendered HTML contains no
      `<u>` tags and no `text-decoration: underline` inline styles.

- [ ] **#6 — Vertical rhythm.** Every `.nav-item` uses the same padding
      (`8px 10px`), gap (`9px`), and border-radius (`7px`). Verified by reading
      the CSS — there's exactly one `.nav-item` rule, not multiple overrides.

- [ ] **#7 — Footer.** Bottom of sidebar has a footer strip with:
      - Pulsing green dot (6px, `var(--accent)`, 2s pulse animation) +
        "Live prices" text.
      - Right-aligned: today's date in `YYYY-MM-DD` format using the existing
        date-format helper (do not introduce a new format).
      - 12px-16px padding, top border, 11px mono font, muted colour.

      The date is rendered server-side from `date.today()` (passed in via
      `as_of` for testability — domain layer rule). The pulse animation runs
      client-side via CSS.

### Topbar

- [ ] **#8 — Slim topbar.** Topbar is a single 52px row with three slots:
      page title (left, 15px, 600 weight, flex-grow:1), FX/time meta (middle,
      12px mono, muted), Refresh button (right). No wrapping, no second row.
      Visual reference: `Investment_Dashboard.html` lines 168–200.

- [ ] **#9 — Page-header dedup.** On every page, the large in-content
      page-header block (e.g. "📊 Analytics" with subtitle below the topbar)
      is removed. The topbar `<h1>` is now the only page title. Page subtitles
      (the descriptive line under the old in-content header, e.g. "Five lenses
      on your portfolio…") are preserved as small muted text immediately below
      the topbar, **not** as a second h1.

      Pages affected (verify all of these by walking the running app):
      - Live Overview
      - Performance
      - Tax Dashboard
      - Analytics & Risk
      - Research
      - Sell Simulator
      - Lot Ledger
      - Decision Gates
      - Behavioural Ledger
      - Manage Portfolio

      For each page, the change is: locate the `st.markdown` or component
      call that renders the duplicate large header, remove it, and (if the
      page had a subtitle) render the subtitle as a single muted-text line.

### Theme

- [ ] **#10 — Light theme preserved.** The app stays in light theme. Do not
      reintroduce dark-theme variables. The `Investment_Dashboard.html`
      reference is dark — translate its *structure and proportions* to the
      existing light-theme OKLCH variables in `app/ui/styles/dark.css`
      (despite the filename, the file currently holds light-theme values
      per TICKET-007 refactor). Do not rename the CSS file in this ticket.

### Tests and lint

- [ ] Tests pass: `pytest`
- [ ] Lints pass: `ruff check . && mypy app/ && lint-imports`
- [ ] CI green on the PR

---

## Files likely touched

- `app/ui/components/sidebar.py` — section grouping, brand block, footer,
  ghost-row elimination
- `app/ui/components/topbar.py` — slim 3-slot layout
- `app/ui/styles/dark.css` — `.nav-section-label`, `.sidebar-footer`,
  active-state pill, no-underline rule, hover transitions, pulse keyframe
- `app/ui/pages/overview.py` — remove duplicate page-header
- `app/ui/pages/performance.py` — remove duplicate page-header
- `app/ui/pages/tax.py` — remove duplicate page-header
- `app/ui/pages/analytics.py` — remove duplicate page-header
- `app/ui/pages/research.py` — remove duplicate page-header
- `app/ui/pages/simulator.py` — remove duplicate page-header
- `app/ui/pages/lots.py` (or equivalent) — remove duplicate page-header
- `app/ui/pages/decisions.py` (or equivalent) — remove duplicate page-header
- `app/ui/pages/behaviour.py` (or equivalent) — remove duplicate page-header
- `app/ui/pages/manage.py` — remove duplicate page-header
- `tests/unit/ui/test_components.py` — extend existing component tests
- `tests/unit/ui/test_sidebar_structure.py` — **new** file, dedicated regression
  tests for ghost rows, section grouping, and active-state behaviour

The exact filenames for some pages may differ from the list above — verify
during Phase 4 by listing `app/ui/pages/`. The intent is "every page's
duplicate header gets removed"; the file list is descriptive, not prescriptive.

---

## Files NOT to modify

This ticket is visual polish only. Do **not** modify:

- Any file under `app/domain/`
- Any file under `app/services/`
- Any file under `app/ports/`
- Any file under `app/adapters/`
- Any file under `tests/unit/domain/`, `tests/unit/services/`, `tests/integration/`
  except where component tests need a fixture update because a removed
  page-header changed an HTML smoke-test snapshot
- `app/ui/wiring.py`
- `app/ui/format.py`
- Any chart-rendering code in `app/ui/components/charts.py` or
  `app/ui/components/_chart_styles.py`

If a test under `tests/unit/ui/` breaks because the rendered HTML structure
changed, update the assertion to match the new structure — do not change the
component to make the old assertion pass. Note the change in the session log.

---

## Out of scope

- Renaming `app/ui/styles/dark.css` to `light.css` (separate cleanup ticket
  if wanted; not blocking)
- Changing the colour palette (light theme stays exactly as-is)
- Adding new nav entries
- Changing the order of nav entries within a section beyond what's specified
  in #2
- Changing the topbar's FX/time data source, refresh-button behaviour, or
  cache-flushing logic (purely visual layout change)
- Reorganising page content below the topbar (subtitles get preserved as
  small muted lines; the *content* of pages is untouched)
- Mobile responsive breakpoints (the app is desktop-only by design)
- Animating the sidebar (only the live-prices dot pulses; no other animation)

---

## Test cases

### Unit tests (`tests/unit/ui/test_sidebar_structure.py` — new)

1. **No ghost rows.** Render the sidebar with `page="overview"`. Parse the
   resulting HTML. Assert: number of `.nav-item` elements equals
   `len(NAV_ITEMS)` (currently 10). Assert no `<div>` between section labels
   is empty or contains only whitespace.

2. **Three section labels in order.** Rendered HTML contains exactly three
   `.nav-section-label` elements with text content `"PORTFOLIO"`, `"TOOLS"`,
   `"SETTINGS"` in that document order.

3. **Each nav item is in the correct section.** Walk the rendered DOM:
   between the `PORTFOLIO` label and the `TOOLS` label, the nav items are
   exactly Live Overview, Performance, Tax Dashboard, Analytics & Risk,
   Research. Between `TOOLS` and `SETTINGS`: Sell Simulator, Lot Ledger,
   Decision Gates, Behavioural Ledger. After `SETTINGS`: Manage Portfolio.

4. **Active state.** Render with `page="analytics"`. Assert: exactly one
   nav item has class `active`, its label is "Analytics & Risk", and its
   inline styles or computed class produce the green-pill treatment (assert
   the class list, not the resolved colour).

5. **No underlines.** Rendered HTML for the sidebar does not contain the
   substring `text-decoration: underline` and does not contain `<u>` tags.

6. **Brand block has no broker reference.** Rendered HTML for the brand block
   contains "Investment Panel" but does **not** contain "Scalable",
   "Capital", or " · DE".

7. **Footer present.** Rendered HTML contains the substring "Live prices",
   exactly one `.live-dot` element, and a date string matching
   `\d{4}-\d{2}-\d{2}`. The date passed in is `date(2026, 5, 9)` for
   determinism — test asserts `"2026-05-09"` appears.

### Unit tests (`tests/unit/ui/test_components.py` — extend)

8. **Topbar layout.** Render the topbar for `page="overview"`. Assert: exactly
   one `<h1>` element, its text is the page title from `PAGE_TITLES`, and the
   topbar contains exactly one Refresh button.

9. **Topbar nav-items count assertion update.** The existing test that
   asserts `len(NAV_ITEMS) == 10` may need to update to 10 (already 10 per
   session log — verify on branch).

### Page-header dedup tests

10. **No duplicate large header on each page.** For each page module
    (`overview`, `performance`, `tax`, `analytics`, `research`, `simulator`,
    `lots`, `decisions`, `behaviour`, `manage`): render the page in a
    Streamlit test harness or extract the page's render function output as
    HTML. Assert: there is at most one `<h1>` in the page output (which is
    the topbar's). The page itself emits at most one `<h2>` for major sections
    and uses muted-text spans for subtitles.

    If the page-header dedup is implemented by simply deleting the duplicate
    `st.markdown` call, this test reduces to: assert the substring
    "📊 Analytics", "📈 Research", etc. (the duplicated emoji headers) does
    not appear in the page module's source under `app/ui/pages/`.

### Edge cases

11. **Sidebar with a flagged Decision Gates entry.** Render with the badge
    payload `{"text": "3 flags", "color": "red"}`. Assert: the badge appears
    next to "Decision Gates", right-aligned, with the red colour class.
    Other entries have no badge.

12. **Sidebar without any badges.** Render with all badges `None`. Assert:
    no `.nav-badge` elements in the rendered HTML.

13. **Date-injection determinism.** Render the footer with `today=date(2024, 1, 1)`
    and `today=date(2026, 5, 9)`. The HTML differs only in the date string;
    everything else (dot, "Live prices" text) is identical.

---

## Notes

### Why this is one ticket

Sidebar and topbar share a CSS file, share a component file pattern, and the
topbar dedup forces walking every page anyway (so we get the ghost-row pass
on every page for free). Splitting would mean two PRs that touch the same
CSS file in series, with the second one resolving merge conflicts against
the first.

### Reference file

`Investment_Dashboard.html` (reference mockup, dark theme) is the structural
reference, not a colour reference. Translate proportions, spacing, and
component anatomy to the existing light-theme OKLCH variables. Specifically:

- `--bg`, `--surface`, `--surface2`, `--border`, `--border2`, `--text`,
  `--text2`, `--text3`, `--accent`, `--green-bg`, `--red-bg`, `--amber-bg`
  already exist in `app/ui/styles/dark.css` (light values). Reuse them.
- Do not introduce new colour variables.
- Do not change the existing values of these variables.

### Bench-test against the running app

Per the methodology checklist (lesson from TICKET-008b), "verification means
observed working behaviour in the running app, not just tests passing."

Before opening the PR, the agent must:

1. Run the app: `streamlit run app/ui/main.py`
2. Click through every page in the nav.
3. On each page: confirm no ghost rows appear in the sidebar, the active
   state is on the right entry, no duplicate page-header is visible, the
   topbar shows the right title.
4. Take a screenshot of the new Live Overview page (most-trafficked) and
   the new Analytics page (the one with the worst current ghost-row issue),
   and paste both into the PR description.

If any of those visual checks fails, **stop and report** — do not push.
This is exactly the failure mode TICKET-008b warned about: a fix that
makes tests green but leaves a visible defect in the running app.

### Streamlit ghost-row root cause (likely)

The most common cause of empty rows in a custom Streamlit sidebar is calling
`st.write("")`, `st.markdown("")`, an empty `st.container()`, or a control-flow
branch that conditionally renders nothing but still produces a `<div>` block.
The fix is usually to remove the empty call, not to add CSS to hide it. CSS
hiding is fragile and tends to hide *real* content later when something
shifts. Find and delete the empty calls.

### Rendering helper to use

`app/ui/render.py:render_html()` is the only place in the codebase that
sets `unsafe_allow_html=True` (per TICKET-008b). Any new HTML emitted by
the sidebar/topbar must go through `render_html()`. Do not add a second
call site for `unsafe_allow_html=True`.

### "📊 Analytics" duplicate header

The user specifically called out this duplicate. The Analytics page renders
both "Analytics & Risk" in the topbar AND "📊 Analytics" with a subtitle
("Five lenses on your portfolio…") in the page body. Remove the in-body
header. Preserve the subtitle as a muted text line directly under the
topbar (or above the tabs).
