# TICKET-RD1 — Overview & Tax HTML overhaul (verification)

Captured via `tools/app_sandbox.sh` (port 8599) against a throwaway data dir
seeded with four positions (NVDA, SAP.DE, ASML.AS, AAPL, all classified `AKTIE`
in the ISIN map). Live prices/FX from yfinance.

## `overview-before.png`
Pre-RD1 Live Overview. Note the **Thesis Status** KPI card, the thesis pills
under the Positions card, and the **Horizon** + **Thesis** columns in the
positions table.

## `overview-after.png`
Post-RD1 Live Overview. KPI tiles render through `render_metric_card` /
`build_metric_card`; the positions table renders through the new
`components/positions_table.py`. The Thesis Status card, thesis pills, and the
Horizon/Thesis columns are gone; the second KPI row is now 3 cards. Company
names resolve from the ISIN map; gains, weight bars, and 30-day trend arrows
render correctly. No inline styles, no HTML leak.

## `tax-after.png`
Post-RD1 Tax Dashboard. All four tile rows (YTD summary, tax exposure) plus the
harvest table, the right-aligned "Tax-free headroom" card, and the progress bar
render through the shared component + dark.css classes. No inline styles, no
HTML leak.

> Note: while seeding, the Tax page surfaced `StreamlitDuplicateElementKey`
> (`key='tax_open_mappings'`) when a ticker is *not* in the ISIN map and
> classification fails — this is the pre-existing **TICKET-TAX-1 (#154)**, not
> introduced by RD1. The shots above use a fully-classified ISIN map so the page
> renders end-to-end.
