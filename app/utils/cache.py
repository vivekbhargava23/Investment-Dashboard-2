"""
app/utils/cache.py

Unified cache management for the Investment Panel Dashboard.
Coordinates invalidation across Streamlit and individual service-level caches.
"""

from __future__ import annotations

import streamlit as st

from app.services import finnhub_client, history_service, yfinance_client


def clear_all() -> None:
    """
    Evict all cached data from memory.
    
    This includes:
      - Streamlit's @st.cache_data (UI-level results)
      - Finnhub price cache (live US prices)
      - yfinance price cache (live Non-US prices)
      - History service batch cache (historical price frames)
    """
    st.cache_data.clear()
    finnhub_client.clear_cache()
    yfinance_client.clear_cache()
    history_service.clear_cache()
