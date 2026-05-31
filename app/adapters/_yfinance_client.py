"""Shared yfinance import.

All four per-protocol yfinance adapters import yfinance through here so
there is a single point of entry for the third-party library.
"""
import yfinance as yf

__all__ = ["yf"]
