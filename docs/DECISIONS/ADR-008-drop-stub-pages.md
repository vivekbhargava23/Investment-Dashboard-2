# ADR-008 — Drop the four stub pages from nav

**Status:** Proposed
**Date:** 2026-05-31
**Drafted by:** Vivek + Claude (Cowork session 2026-05-31)
**Supersedes / amends:** ARCHITECTURE.md "File layout" section (removes four page entries)

---

## Context

`ARCHITECTURE.md` lists ten Streamlit pages in `app/ui/pages/`. Four of them are 5-line stubs that render nothing useful:

- `decision.py` (5 lines) — was the "Decision Gates" thesis-tracking idea
- `lots.py` (5 lines) — was the "Lot Ledger"
- `performance.py` (5 lines) — duplicates the Performance *tab* now living inside Analytics
- `behaviour.py` (5 lines) — was the "Behavioural Ledger"

These shipped as placeholders during the Analytics & Risk milestone with intent to flesh out later. They never were. They still appear in the sidebar, render empty pages, and signal to the user that something is broken.

`docs/CONTEXT.md` regenerates from the actual file tree on every merge, so the stub pages keep getting re-advertised in the project state, which keeps draft tickets referring to them, which keeps the cycle alive.

User feedback (2026-05-31 Cowork session): *"lets make a concrete app with more of what works is shown not a lot of bullshit pseudo pages."*

## Decision

**Remove the four stub pages from nav and delete the stub files.** The sidebar shows only pages with real implementations.

If any of the four is worth building later, it gets a real ticket with a real spec at that time. No pre-emptive placeholders.

The four removed pages and their fate:

- **decision.py** — deleted. Decision-gates concept is unscoped; revisit only with a concrete v1 ticket.
- **lots.py** — deleted. The lot data is already visible in the Tax page's per-lot table; a separate page is redundant until proven otherwise.
- **performance.py** — deleted. Functionality lives in `Analytics → Performance` tab.
- **behaviour.py** — deleted. Behavioural ledger was a future-thesis idea; no real product spec exists.

ARCHITECTURE.md's file-layout section is updated to remove these four entries.

## Reasoning

1. **Empty pages signal broken software.** A user clicking "Decision Gates" expects something. Showing nothing teaches them not to trust the rest of the app.
2. **Speculative scaffolding fights real work.** Every CONTEXT.md regeneration re-advertises these pages as "in the architecture"; that pulls them into draft tickets and design conversations that go nowhere.
3. **No information is lost.** The git history retains the stub files; they were never more than placeholders.
4. **Methodology rule:** *"no documented approximation placeholders"* (METHODOLOGY.md). Stub pages are the UI equivalent — placeholders that have stayed. The same rule applies.

## Consequences

- **Pro:** Sidebar shows only working pages. User confidence improves.
- **Pro:** ARCHITECTURE.md aligns with what's actually built.
- **Pro:** Draft tickets stop referring to imaginary features.
- **Con:** If we want any of these back later, we need a real ticket. That is the point — the cost of bringing them back is paid only when there's a real spec.

## Reversal cost

Per-page: a new ticket with a real spec. There is no "undelete the stub" path; we don't want one.

## Alternatives considered

- **Keep stubs, just disable in nav.** Rejected — same speculative-scaffolding problem; the file tree still re-advertises them.
- **Build a v1 of Lots Ledger now.** Rejected for this batch — user wants clean-slate first, then build deliberately. Lots Ledger gets its own ticket when it's worth scoping. (User explicitly chose "Drop all four" over "Build Lots Ledger v1 in this batch".)

## Implementation ticket

TICKET-C2.
