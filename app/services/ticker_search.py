"""
app/services/ticker_search.py

Local-first ticker search with curated catalogue and remote fallback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

import streamlit as st

from app.services.price_service import lookup_name
from app.utils.logger import get_logger

logger = get_logger(__name__)

class TickerEntry(TypedDict):
    ticker: str
    name: str

_CATALOGUE_PATH = Path("app/data/seeds/ticker_catalogue.json")

@st.cache_data(ttl=3600)
def _load_catalogue() -> list[TickerEntry]:
    """Load the local curated ticker catalogue."""
    if not _CATALOGUE_PATH.exists():
        logger.warning("catalogue_missing", path=str(_CATALOGUE_PATH))
        return []
    try:
        return json.loads(_CATALOGUE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("catalogue_load_failed", error=str(exc))
        return []

def search_tickers(query: str) -> list[TickerEntry]:
    """
    Search for tickers in the local catalogue by symbol or name.
    Ranking: exact ticker match first, then ticker starts with, then substring.
    """
    if not query:
        return []

    q = query.strip().upper()
    catalogue = _load_catalogue()
    
    results: list[TickerEntry] = []
    
    # 1. Exact ticker match
    exact = [e for e in catalogue if e["ticker"].upper() == q]
    # 2. Ticker starts with
    starts = [e for e in catalogue if e["ticker"].upper().startswith(q) and e not in exact]
    # 3. Name or Ticker substring
    substring = [
        e for e in catalogue 
        if (q in e["ticker"].upper() or q in e["name"].upper()) 
        and e not in exact and e not in starts
    ]
    
    return exact + starts + substring

def resolve_unknown_ticker(ticker: str) -> TickerEntry | None:
    """
    Check local catalogue first, then fall back to remote lookup (yfinance).
    """
    q = ticker.strip().upper()
    catalogue = _load_catalogue()
    
    # Local check
    local_match = next((e for e in catalogue if e["ticker"].upper() == q), None)
    if local_match:
        return local_match
    
    # Remote fallback
    remote_name = lookup_name(q)
    if remote_name:
        return {"ticker": q, "name": remote_name}
    
    return None
