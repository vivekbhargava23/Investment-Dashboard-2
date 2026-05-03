# app/domain/CLAUDE.md

Pure Python domain layer. Zero I/O imports.

## Hard rules for this module
- No `requests`, `httpx`, `urllib`, `aiohttp`
- No file I/O (`open`, `Path.read_*`, `json.load`)
- No `streamlit` or `pandas.read_*`
- No `datetime.now()` — pass `as_of: date` explicitly
- All models: Pydantic v2 with `model_config = ConfigDict(frozen=True)` where possible
- All money amounts: `Decimal`, never `float`

## Files (added as tickets land)
- `models.py` — TICKET-001: Lot, Transaction, Position, Money, Currency
- `fifo.py` — TICKET-002: FIFO engine with replay-on-edit
- `tax.py` — TICKET-002+: Sparerpauschbetrag, Verlustverrechnungstopf
- `thesis.py` — TICKET-009+: Thesis state, decision gates
