# TICKET-RD2 — Sortable tables (verification screenshots)

Driven against an **isolated sandbox** data dir (seeded with read-only copies of
the local portfolio/isin_map) via Playwright — the real `data/` was never
touched. Sorting is reached purely by URL query params, exactly as the clickable
column headers set them.

## Live Overview positions table (the ticket)

- `overview-default-value-desc.png` — no params → **value descending** (the
  pre-RD2 behaviour, regression guard). Top row MU €6,397.93.
- `overview-sorted-gain-desc.png` — `?sort=gain&dir=desc` → ordered by the Gain
  column (MU +3,818 … down to RHM.DE −171, 4062.T −236).
- `overview-sorted-ticker-asc.png` — `?sort=ticker&dir=asc` → A→Z by ticker;
  active header shows ▲.

## Manage Portfolio — All Transactions

- `manage-default-date-desc.png` — default **date descending**; headers are
  clickable, edit/delete actions preserved.
- `manage-sorted-ticker-asc.png` — `?txsort=ticker&txdir=asc` → A→Z by ticker
  (4062.T, AJINF×3, ANAV.DE …).

## ISIN Mappings — Mapped table

- `mappings-sorted-name-asc.png` — `?mapsort=name&mapdir=asc` → A→Z by company
  name; row actions (Edit/Kind/Unmap/Remove) preserved.
