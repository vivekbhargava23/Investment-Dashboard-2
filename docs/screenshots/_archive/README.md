# Archived screenshots

Verification screenshots of surfaces that no longer exist. Kept because they are
the record that the ticket which produced them was observed working, not because
they describe the app as it is today.

- `csv-18/` — the inline "Ignore" flow on the Import CSV workbench and the ISIN
  Mappings page. Both pages were retired in TICKET-SYNC-7; the same actions now
  live on the instrument card under **All instruments** on the Sync tab, where
  "Ignore" reads **Use last trade price**.
- `ticket-sync-2-mapping-write-path/` — the shared-ticker guard and the
  mapping-consistency Repair banner, shot on the ISIN Mappings page. The write
  path itself is unchanged (`services/isin_remap.change_feed`); only its screen
  moved to the Sync tab.
