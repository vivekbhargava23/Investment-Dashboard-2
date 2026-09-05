"""In-app explanations for the Sync tab, in one place.

Everything on this page is obvious while you are building it and opaque three
weeks later: what a price feed actually is, why a holding can be valued at its
last trade price, what a write-off does to the tax year, when Undo stops being
offered. Rather than shipping that knowledge only in a PR description, each
control carries a one-click explainer that says three things: **what it is**,
**when to use it**, and **what it does not do**.

The copy lives here as data so it is written once, read in one place, and can be
tested. Rendering is a popover, collapsed by default — the page stays as quiet as
it is now until you ask.
"""
from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from app.domain.sync_tasks import TaskKind


@dataclass(frozen=True)
class Explainer:
    """One collapsed explanation: the button's label and what opens under it."""

    title: str
    body: str


def render_explainer(explainer: Explainer, *, key: str) -> None:
    """Render one explainer as a collapsed popover."""
    with st.popover(explainer.title, use_container_width=False):
        st.markdown(explainer.body)


# ─── the page ─────────────────────────────────────────────────────────────────

HOW_THIS_PAGE_WORKS = Explainer(
    title="❔ How this page works",
    body="""
**This is the only door for Scalable data.** Drop an export and every trade that
is new — matched by Scalable's own reference — is imported immediately, with no
further click. You do not review a list first; that is what **Undo last sync** is
for.

**Then the page tells you what needs a decision.** Anything it can settle alone,
it has already settled. What is left appears as a numbered task, each with the
buttons that resolve it. No tasks means nothing needs you.

**Export the full history, not a date range.** The app compares your whole book
against the file. If the file starts later than your book, it still imports the
new trades but skips the comparison and says so — it cannot tell a missing trade
from a trade that was never in the file.

**Re-uploading the same file is safe** and is the fastest way to check yourself:
it will say *0 new trades imported* and re-run the comparison.
""",
)

UNDO = Explainer(
    title="❔ What Undo restores",
    body="""
**What it is.** One click puts `portfolio.json` **and** `isin_map.json` back
exactly as they were immediately before you dropped this file — byte for byte,
including everything you did while the file was open: feed changes, tax kinds,
Use last trade price, write-offs, Repair.

**When to use it.** Whenever an upload did something you did not expect. It costs
nothing and it is complete; there is no partial undo.

**Why it is sometimes greyed out.** Undo is offered only while the app is certain
it owns both files. If something else changed them since the sync — an edit on
Manage Portfolio, a second browser tab — restoring would silently throw that
change away, so the button disables itself rather than guess. That is also why it
is unavailable once you leave and come back with no file open.

**What it does not do.** It does not undo the sync *before* the last one. One
level, always the most recent.
""",
)

HOLDINGS_TABLE = Explainer(
    title="❔ Reading this table",
    body="""
- **Shares Scalable** — what the export says you hold, computed from every
  executed row in the file.
- **Shares dashboard** — what your book says. These two matching is the whole
  point of the page; a difference always comes with a cause.
- **Feed** — the ticker used to *value* the holding. It is not part of the trade
  record and changing it never changes a share count or a cost basis.
- **Feed check** — the app compares your last three trade prices against what
  that ticker actually closed at on those days. More than 15 % apart and it says
  *looks wrong*, which usually means the ticker belongs to a different
  instrument. It is a warning, not proof — you judge it.
- **Tax kind** — the German tax category the holding is taxed under. `⚠ unset`
  means the Tax Dashboard cannot compute a year containing it.

**Cost is not compared.** Cost per open lot including fees is not derivable from
the export, so the cost you see everywhere comes from your book alone.
""",
)

CASH_EVENTS = Explainer(
    title="❔ About these cash figures",
    body="""
Dividends, interest, taxes and corporate-action payouts found **in this file**.
They are shown so the file is fully accounted for; they are **not** stored, not
imported, and not part of any number on the rest of the dashboard.
""",
)

ALL_INSTRUMENTS = Explainer(
    title="❔ What is in here",
    body="""
Everything the app knows about, not just what needs you today — including the
instruments that raise no task at all.

- **Mapped** — has a price feed. Select a row to change the feed, set the tax
  kind, write it off, or remove it entirely.
- **Closed, no feed** — nothing open and no feed. They cannot affect today's
  valuation, only the tax history, so they never raise a task. They still need a
  tax kind if they were sold in a year you care about.
- **Valued at last trade price** — the ones you told the app to stop asking
  about. **Restore** puts one back in the queue.
""",
)


# ─── the instrument card ──────────────────────────────────────────────────────

PRICE_FEED = Explainer(
    title="❔ What a price feed is",
    body="""
**What it is.** The ticker used to look up a live price for this holding. That is
*all* it is. The ISIN is the identity of the holding; the ticker is only how the
app values it.

**When to change it.** When the feed check says *looks wrong*, when the holding
shows no live price, or when the app guessed a ticker that belongs to a different
company. Saving rewrites the ticker on every transaction with this ISIN in one
operation, so it is always all-or-nothing.

**What it does not do.** It never changes which trades are in your book, how many
shares you hold, or what they cost. A holding with no feed is still fully
imported — it is just valued at the price you last traded it at.

**"Same instrument (ISIN change)".** Tick this only when an instrument genuinely
changed its ISIN. Without it the app refuses to point two ISINs at one ticker,
because that silently merges two holdings into one FIFO position.
""",
)

USE_LAST_TRADE_PRICE = Explainer(
    title="❔ What this button does",
    body="""
**What it is.** "This holding has no price feed, and that is fine — value it at
the price I last paid for it, and stop asking me." The app marks it and it stops
raising a task.

**When to use it.** Certificates, turbos and small ETPs that no free price source
covers. Reaching for it because the search box has not found the right ticker yet
is usually the wrong call — pick the feed instead.

**What it does not do.** It does not hide the holding, delete anything, or
exclude it from your totals. It stays in the book, on the Overview and in the tax
figures, valued at its last trade price and labelled as such.

**Reversible.** All instruments → *Valued at last trade price* → **Restore**.
""",
)

TAX_KIND = Explainer(
    title="❔ Why the tax kind matters",
    body="""
**What it is.** The German tax category (`Aktie`, `Aktienfonds`, `Sonstige`, …).
It decides the Teilfreistellung — the share of a gain that is exempt — and which
loss pot a loss feeds. Getting it wrong misstates the tax on that holding by up
to 30 % of the gain.

**When to set it.** As soon as an instrument appears. The Tax Dashboard refuses
to compute a whole year if a single holding sold in it has no kind, rather than
quietly assuming one.

**It is independent of the price feed.** A holding with no feed still has a tax
kind, and setting one here never touches the feed. This selector saves the moment
you change it — there is no Save button to miss.
""",
)

WRITE_OFF = Explainer(
    title="❔ When to write a holding off",
    body="""
**What it is.** A sale at €0 on a date you choose. The shares leave your open
positions and the loss becomes a realised loss in that tax year, under this
holding's tax kind.

**When to use it.** When something is genuinely worthless and the broker never
booked a closing trade: a certificate that expired, an issuer that went under, a
delisting Scalable never reported. If Scalable *did* book it, do nothing — the
next sync imports it and closes the position by itself.

**What it does not do.** It does not delete anything. Every buy stays where it
is, which is exactly why the loss can be computed at all. Compare **Remove**,
which erases the history and the loss with it.

**Reversible.** Undo, while the file is still open — or delete the write-off row
later on Manage Portfolio, where it is the one broker-shaped row you are allowed
to delete.

**The date matters.** The loss lands in that date's tax year, so it changes which
year's allowance and loss pot it touches. Pick the day it actually became
worthless, not today, if you know it.
""",
)

REMOVE_INSTRUMENT = Explainer(
    title="⚠️ Remove is not a write-off",
    body="""
**What it is.** Permanent deletion of the instrument and **every transaction that
references it**. A timestamped backup of `portfolio.json` is written first, and
that backup is the only way back.

**When to use it.** Almost never — really only for something that should never
have entered the book: a test row, a duplicate import, an instrument that is not
yours.

**What it destroys.** The buys, the sells, and therefore the realised gain or
loss the tax year was counting on. If the holding is real but worthless, you want
**Write off**, which keeps all of that.
""",
)


# ─── the six tasks ────────────────────────────────────────────────────────────

TASK_EXPLAINERS: dict[TaskKind, Explainer] = {
    "no_feed": Explainer(
        title="❔ What this means",
        body="""
**What happened.** Every trade for this holding is in your book — nothing is
missing. There is just no ticker that returns a live price for it, so it is
valued at the price you last traded it at. That value is real, but it is frozen
at your last trade date.

**What to do.** Search for the right ticker and **Save feed**. If no free source
carries this instrument — common for certificates, turbos and small ETPs — press
**Use last trade price** and the app stops asking.

**Either way your share counts and cost basis are already correct.**
""",
    ),
    "feed_suspicious": Explainer(
        title="❔ What this means",
        body="""
**What happened.** The app compared the prices you actually paid on your last
three trades against what the mapped ticker closed at on those same days. They
are more than 15 % apart. Usually that means the ticker belongs to a *different*
instrument — a similarly named company, or a listing in another currency.

**What to do.** Look at the two averages in the headline and judge. If the ticker
is wrong, search for the right one and **Save feed**. If it is right and the gap
is real — a thin listing, a stock split, a genuinely volatile week — ignore this
task; nothing is broken.

**Nothing is at stake but the displayed value.** Your trades are unaffected
either way.
""",
    ),
    "shares_differ": Explainer(
        title="❔ What this means",
        body="""
**What happened.** The export says you hold one number of shares and your book
says another. The sentence under the headline is the app's best explanation — a
row that failed validation, an unpaired transfer, a row edited by hand, a
possible duplicate.

**What to do.** Read the cause first; it usually names the fix. Open **Details**
to see every row of the file and what the app decided about each. If the cause
reads *unknown*, that is worth investigating rather than dismissing — it means
nothing the app knows about accounts for the gap.

**Nothing is imported or changed by this task.** It is telling you, not asking.
""",
    ),
    "sell_exceeds": Explainer(
        title="❔ What this means",
        body="""
**What happened.** The file sells more shares of this holding than the book ever
bought, so the FIFO engine cannot match the sale to any lots. This almost always
means buys are missing — an export that does not go back far enough, or a holding
transferred in from another broker without its history.

**What to do.** Export your **full** history from Scalable and upload that. If
the buys genuinely happened elsewhere, add them on Manage Portfolio so the lots
exist to sell.

**Until it is resolved this holding's gains cannot be computed**, so it is worth
fixing rather than living with.
""",
    ),
    "possible_duplicate": Explainer(
        title="❔ What this means",
        body="""
**What happened.** A row in the file looks exactly like a trade you once entered
by hand: same instrument, date, share count and price. It could be the same trade
recorded twice, or two genuinely separate trades that happen to match.

**Nothing has been imported for this row.** It is the one case the app refuses to
decide on its own, because both answers are destructive in one direction.

**What to do.** **Replace with the Scalable row** if it is the same trade — the
broker's version is better, since it carries the fees and the reference. **Keep
both** if you really did trade twice that day.
""",
    ),
    "partial_file": Explainer(
        title="❔ What this means",
        body="""
**What happened.** This export starts later than your book does, so it cannot
describe your whole position. New trades in it *were* imported, but the holdings
comparison and the price-feed check were skipped: against a partial file the app
cannot tell a missing trade from one that was never in the file, and reporting a
false mismatch would be worse than reporting nothing.

**What to do.** In Scalable, export the full transaction history with no date
filter, and drop that here. Nothing you just imported is lost — the next upload
recognises it and reports *already known*.
""",
    ),
}


# ─── short widget tooltips ────────────────────────────────────────────────────

FEED_SEARCH_HELP = (
    "The ticker used to value this holding. It never changes your trades, "
    "share counts or cost basis."
)

KIND_HELP = (
    "The German tax category. Decides the Teilfreistellung and which loss pot "
    "applies. Saves as soon as you change it — no button."
)

WRITE_OFF_HELP = (
    "Record a sale at €0. The shares leave your open positions and the loss "
    "is realised; the history is kept."
)

USE_LAST_TRADE_HELP = (
    "No feed for this holding — value it at the price you last traded it, "
    "and stop asking."
)

REMOVE_HELP = (
    "Permanently deletes this instrument and every transaction referencing it. "
    "Use Write off instead if the holding is real but worthless."
)
