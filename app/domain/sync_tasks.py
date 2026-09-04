"""Turn reconciliation, feed checks and plan decisions into the six sync tasks.

A task is the only thing the Sync page asks the user about, so the rules here
are deliberately narrow: nothing that cannot change a number on screen becomes
a task (`docs/DESIGN/SYNC-TAB.md`, principle 3).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.domain.csv_import import FeedState, PlannedRow
from app.domain.feed_check import FeedCheck
from app.domain.reconcile import ReconcileRow
from app.domain.sync_completeness import CompletenessResult

TaskKind = Literal[
    "no_feed",
    "feed_suspicious",
    "shares_differ",
    "sell_exceeds",
    "possible_duplicate",
    "partial_file",
]

_ZERO = Decimal("0")


class SyncTask(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: TaskKind
    isin: str
    name: str
    headline: str
    detail: str
    impact_eur: Decimal


def _format_shares(value: Decimal) -> str:
    return f"{value.normalize():f}"


def _impact(shares: Decimal, price: Decimal | None) -> Decimal:
    return abs(shares) * (price if price is not None else _ZERO)


def build_tasks(
    rows: Sequence[ReconcileRow],
    checks: Mapping[str, FeedCheck],
    sell_errors: Mapping[str, str],
    decision_rows: Sequence[PlannedRow],
    completeness: CompletenessResult,
    feed_states: Mapping[str, FeedState],
) -> list[SyncTask]:
    """Build the task list for one analysed file, most expensive first.

    A partial file produces exactly one task: nothing else can be judged against
    a file that does not cover the book.

    ``feed_states`` carries the plan's per-ISIN feed state so an ``ignored`` ISIN
    stays silent — "Ignore" on a task means "stop asking", and a FeedCheck alone
    cannot tell an ignored ISIN from an unmapped one.
    """
    if completeness.partial:
        return [_partial_task(completeness)]

    tasks: list[SyncTask] = []
    claimed: set[str] = set()

    for decision in decision_rows:
        tasks.append(_duplicate_task(decision))
        claimed.add(decision.isin)

    for row in rows:
        if row.isin in sell_errors:
            tasks.append(_sell_exceeds_task(row, sell_errors[row.isin]))
            claimed.add(row.isin)

    for row in rows:
        if row.isin in claimed or row.shares_csv <= _ZERO:
            continue
        state = feed_states.get(row.isin)
        check = checks.get(row.isin)
        if state == "ignored":
            continue
        # A holding with no usable feed, whether because no ticker is mapped or
        # because the mapped one returns no closes. Both leave it at its last
        # trade price, so both deserve the same task — a mapping that fetches
        # nothing is not a feed, however mapped it looks.
        if state == "unmapped" or (check is not None and check.status == "no_feed"):
            tasks.append(_no_feed_task(row, check))
            claimed.add(row.isin)
        elif check is not None and check.status == "suspicious":
            tasks.append(_suspicious_task(row, check))
            claimed.add(row.isin)

    # A share difference is the least specific explanation there is, so it is only
    # raised when nothing more precise already covers the ISIN.
    for row in rows:
        if row.isin in claimed or row.matches:
            continue
        tasks.append(_shares_differ_task(row))

    tasks.sort(key=lambda t: (t.kind != "partial_file", -t.impact_eur, t.isin))
    return tasks


def _partial_task(completeness: CompletenessResult) -> SyncTask:
    file_start = completeness.file_start
    book_start = completeness.book_start
    headline = (
        f"This file looks partial (starts {file_start.isoformat() if file_start else '—'}; "
        f"your book starts {book_start.isoformat() if book_start else '—'})"
    )
    detail = (
        "New trades in this file were imported. The holdings comparison and the "
        "price-feed check were skipped, because this file does not cover your "
        "whole book. Export the full history and upload it again to compare."
    )
    if completeness.reason:
        detail = f"{completeness.reason} {detail}"
    return SyncTask(
        kind="partial_file",
        isin="",
        name="This file",
        headline=headline,
        detail=detail,
        impact_eur=_ZERO,
    )


def _duplicate_task(row: PlannedRow) -> SyncTask:
    shares = row.shares or _ZERO
    return SyncTask(
        kind="possible_duplicate",
        isin=row.isin,
        name=row.description,
        headline=(
            f"Possible duplicate: {row.description} on "
            f"{row.trade_date.isoformat()} matches a manual entry"
        ),
        detail=(
            "Nothing is imported until you choose. Replace with the Scalable row "
            "if this is the same trade you entered by hand, or keep both if they "
            "are two different trades."
        ),
        impact_eur=_impact(shares, row.price),
    )


def _sell_exceeds_task(row: ReconcileRow, message: str) -> SyncTask:
    return SyncTask(
        kind="sell_exceeds",
        isin=row.isin,
        name=row.name,
        headline=f"Sell exceeds shares held: {row.name}",
        detail=message,
        impact_eur=_impact(row.shares_csv, row.last_trade_price_eur),
    )


def _no_feed_task(row: ReconcileRow, check: FeedCheck | None = None) -> SyncTask:
    shares = _format_shares(row.shares_csv)
    detail = (
        "Every trade for this holding is in your book. Without a price feed it "
        "is valued at your last trade price, so its market value is stale — "
        "pick a feed to value it live, or ignore it to stop being asked."
    )
    if check is not None and check.status == "no_feed" and check.ticker:
        detail = (
            f"{check.ticker} is mapped to this holding but returns no prices, so it "
            f"is valued at your last trade price. {detail}"
        )
    return SyncTask(
        kind="no_feed",
        isin=row.isin,
        name=row.name,
        headline=(
            f"No price feed for {row.name} ({shares} shares, valued at last trade price)"
        ),
        detail=detail,
        impact_eur=_impact(row.shares_csv, row.last_trade_price_eur),
    )


def _suspicious_task(row: ReconcileRow, check: FeedCheck) -> SyncTask:
    avg_trade = check.avg_trade_price_eur or _ZERO
    avg_close = check.avg_close_eur or _ZERO
    return SyncTask(
        kind="feed_suspicious",
        isin=row.isin,
        name=row.name,
        headline=(
            f"Price feed for {row.name} looks wrong — your trades avg "
            f"€{avg_trade:.2f}, feed {check.ticker} closed €{avg_close:.2f}"
        ),
        detail=(
            f"{check.detail} The feed only sets the value on screen; your trades "
            "are unaffected either way."
        ),
        impact_eur=_impact(row.shares_csv, row.last_trade_price_eur),
    )


def _shares_differ_task(row: ReconcileRow) -> SyncTask:
    return SyncTask(
        kind="shares_differ",
        isin=row.isin,
        name=row.name,
        headline=(
            f"Shares differ: {row.name} — Scalable {_format_shares(row.shares_csv)}, "
            f"dashboard {_format_shares(row.shares_book)}"
        ),
        detail=row.cause or "unknown — check Details",
        impact_eur=_impact(row.diff, row.last_trade_price_eur),
    )
