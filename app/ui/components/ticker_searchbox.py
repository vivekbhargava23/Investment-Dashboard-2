import logging
from collections.abc import Callable

from streamlit_searchbox import st_searchbox

from app.ports.ticker_resolver import TickerMatch, TickerResolver


def _format_label(m: TickerMatch) -> str:
    return f"{m.symbol} — {m.name} ({m.exchange}, {m.currency.value})"


def _search_callback_for(
    resolver: TickerResolver,
) -> Callable[[str], list[tuple[str, TickerMatch]]]:
    """Return a search callback bound to *resolver* for use with st_searchbox."""

    def _callback(query: str) -> list[tuple[str, TickerMatch]]:
        if not query or len(query) < 2:
            return []
        try:
            matches = resolver.resolve(query, limit=8)
            return [(_format_label(m), m) for m in matches]
        except Exception:
            logging.warning("Ticker resolver error for query %r", query, exc_info=True)
            return []

    return _callback


def render_ticker_searchbox(
    key: str,
    resolver: TickerResolver,
    *,
    placeholder: str = "Type a ticker (e.g. APD, RHM)…",
    default_match: TickerMatch | None = None,
) -> TickerMatch | None:
    """Render an autocomplete ticker search field.

    Returns the selected TickerMatch, or None if nothing is selected.
    `key` must be unique per Streamlit page.
    """
    default: tuple[str, TickerMatch] | None = (
        (_format_label(default_match), default_match) if default_match is not None else None
    )

    result = st_searchbox(
        _search_callback_for(resolver),
        placeholder=placeholder,
        key=key,
        default=default,
    )

    if isinstance(result, TickerMatch):
        return result
    if isinstance(result, tuple) and len(result) == 2:
        _, match = result
        if isinstance(match, TickerMatch):
            return match
    return None
