# TICKET-SYNC-2 — visual verification

Driven against an isolated sandbox data dir (`tools/app_sandbox.sh` paths, never
the real `data/`), seeded with:

- `US67066G1040` → `NVDA` (mapped), with a stored row **deliberately left on
  `NVDA.DE`** so the consistency check has something to find
- `US0378331005` → `AAPL` (mapped)
- `DE000A0F5UF5` unmapped, holding a placeholder row whose ticker is the ISIN

| File | Shows |
|---|---|
| `01-guard-refuses-shared-ticker.png` | Mapping `DE000A0F5UF5` onto `NVDA` is refused — `NVDA` is already NVIDIA's feed. Still `2 mapped · 1 unmapped`: nothing was written. |
| `02-merge-confirmed-rewrites-rows.png` | Same save with **Same instrument (ISIN change)** ticked: the mapping lands and the placeholder row is rewritten (`Rewrote 1 transaction(s)`). |
| `03-repair-banner-before.png` | The out-of-sync banner naming the mismatch: map says `NVDA`, book says `NVDA.DE`. |
| `04-repair-banner-after.png` | After **Repair** — one row rewritten, banner gone. `portfolio.json` on disk shows `NVDA`. |
