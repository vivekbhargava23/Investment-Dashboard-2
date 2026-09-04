# ADR-014 — ISIN is the identity of a broker holding; the ticker is its price feed

**Status:** Proposed (2026-09-03, revised twice the same day after external review)
**Date:** 2026-09-03
**Drafted by:** Vivek + Claude (Cowork session 2026-09-03)
**Related:** Completes Stage 1 of TICKET-CSV-8 properly. Extends ADR-006 (classification as data).

## Context

`Transaction.ticker` is set at import time. Editing an ISIN→ticker mapping relies on
`rewrite_ticker_for_isin`, which only reaches transactions carrying `isin`. An audit on
2026-09-03 found 71 of 213 Scalable transactions with `isin: null` (the importer stopped
stamping it in TICKET-CSV-15), so the rewrite silently missed every trade imported since
May and the user fell back to editing tickers row by row in Manage Portfolio — which strips
`source`, `csv_reference` and fees and breaks dedupe on the next import.

A read-time join (repository overwriting tickers from `isin_map.json` on `load_all`) was
considered and rejected: a repository must return stored facts unchanged, and a silent
rewrite on read would also defeat byte-for-byte undo.

## Decision

1. Every Scalable-sourced transaction stores its ISIN (`Transaction.isin`). The ISIN is the
   identity of the holding from the broker's point of view.
2. The ticker on such a transaction is a **derived value kept in sync by the mapping
   write path**: whenever the ISIN→ticker mapping changes, every transaction with that ISIN
   is rewritten in the same operation (`rewrite_ticker_for_isin`). Reads never derive.
3. Tickers on Scalable-sourced transactions are not user-editable anywhere else. Type,
   date, shares and amounts of such rows are not editable either; only `notes` is.
4. A mapping may not assign a ticker already used by another `mapped` ISIN unless the user
   explicitly confirms "same instrument (ISIN change)". This prevents two different
   instruments from merging into one FIFO position by accident.
5. FIFO, cost basis and realised gains stay keyed by ticker for now. Keying them by ISIN
   (with a hybrid key for manual rows) is the theoretically cleaner model; it touches the
   FIFO engine, tax engine, NAV, valuation and every page, has no motivating case in the
   current data, and is deferred to its own ADR if a real case appears.
6. Manual transactions (other brokers) keep `isin = None` and an editable ticker; ADR-005
   currency inference applies to them only.
7. **Every executed Buy / Sell / Savings-plan row is imported, always.** A price feed is
   never a precondition for a trade to be in the book. An ISIN with no `mapped` entry gets
   the ISIN itself as placeholder ticker (it satisfies the uppercase-ticker rule and is what
   the user already did by hand for unpriceable ETPs). Choosing a feed later rewrites the
   placeholder via rule 2. `ignored` means "no feed wanted": rows are still imported, the
   position is valued at its last trade price, and no task is raised for it.
8. A position whose ticker has no live price is valued at the price of its latest lot
   (EUR), flagged `price_source = "last_trade"`, so totals never silently exclude it.
9. Changing a mapping writes in a fixed order — transactions first, then the map — inside
   a sync snapshot; a stored-ticker-vs-map mismatch is therefore always detectable and is
   repaired by re-running the (idempotent) rewrite.

## Consequences

- Changing a mapping is one write that also rewrites the affected rows; cache keys that
  depend on tickers (`_tx_sig` in `services/valuation.py`) must include tickers.
- A consistency check (stored ticker == mapping ticker for every mapped ISIN) is part of
  the verification checklist; a mismatch means the write path was bypassed.
- Undo of a sync must restore `portfolio.json` and `isin_map.json` together, byte-for-byte.
