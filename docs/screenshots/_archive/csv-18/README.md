# TICKET-CSV-18 — Inline "Ignore" verification screenshots

Captured by driving the running Streamlit app (Playwright) against a throwaway
data dir, with a CSV containing two deliberately-unresolvable ISINs
(`XX0000099991`, `XX0000099992`).

| File | Shows |
|---|---|
| `01-panel-save-and-ignore.png` | Manual-review panel: each unmapped ISIN now has **Save** (disabled until ticker+kind picked) and the new **Ignore** button. |
| `02-row-dropped-after-ignore.png` | After clicking Ignore on `XX0000099991`: header drops to "(1)", that row is gone, the other remains. |
| `03-mappings-count-one-ignored.png` | Mappings page header reads "1 mapped · 0 unmapped · **1 ignored**" — the workbench ignore persisted. |
| `04-mappings-ignored-with-restore.png` | Ignored ISINs section lists the ignored entry with a working **Restore** — identical to a Mappings-page ignore. |
