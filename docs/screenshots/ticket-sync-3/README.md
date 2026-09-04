# TICKET-SYNC-3 visual verification

Scenario: the Manage Portfolio page runs against an isolated sandbox containing one
Scalable Capital transaction for 3.5 NVDA shares, with ISIN `US67066G1040` and broker
provenance fields populated.

- `before-edit-form.png` shows the previous broker edit surface exposing type, date,
  shares, total, fees, and notes.
- `after-edit-form.png` shows the replacement notes-only surface, including the imported
  transaction summary and the instruction to change ticker mappings on the ISIN Mappings
  page.

The same Playwright run confirmed that the selected broker row's Delete button is disabled.
