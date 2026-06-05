# TICKET-PANEL-2 — Catalysts timeline (verification screenshots)

Captured against an isolated sandbox (`tools/app_sandbox.sh`-style launch) seeded
with a small portfolio (NVDA, MRVL, ANET) so both position events and book-wide
macro events appear. The catalysts data is the committed `data/catalysts.json`
seed from PANEL-1.

## `overview-catalysts-timeline.png`
The new portfolio-wide **Catalysts** section on Live Overview (`mode="portfolio"`):

- Legend of all six categories with their colour tokens and a `today · <as_of>` marker.
- Events grouped into time bands (`This week`, `This month`, `Next 3 months`);
  the empty `Later` band is omitted.
- Macro / `scope: portfolio` events marked **BOOK-WIDE**; position events show their ticker.
- `estimated` dates render as a hollow dot with a `~` prefix and muted italic date
  (e.g. US CPI, ECB, ANET/NVDA/MRVL earnings); `confirmed` dates (FOMC) have filled dots.
- High-impact earnings render heavier/larger than lower-impact rows.
- `catalysts as of 2026-06-05` surfaced below the timeline.
- Companion table: Date · Event · Ticker · Category · Impact, sorted by date.

## `overview-full.png`
Full Overview page showing the Catalysts section in context below the existing
KPI tiles, positions table, allocation treemap and performance heatmap.

## Per-position variant (`mode="position"`) — not screenshotted
The same component is wired into the Company Deep Dive page (Snapshot tab) via
`get_position_catalysts(...)`. It could not be screenshotted because the Company
Snapshot tab currently crashes on a **pre-existing, unrelated bug** in
`_render_price_chart` → `chart_theme.styled_line_trace` (the helper hardcodes
`mode="lines+markers"` while the caller also passes `mode="lines"`, raising
`TypeError: ... got multiple values for keyword argument 'mode'`). This bug exists
on `main` independent of PANEL-2 and is flagged for a separate fix ticket. The
position-mode rendering itself is covered by unit tests in
`tests/unit/ui/test_catalysts_timeline.py`.
