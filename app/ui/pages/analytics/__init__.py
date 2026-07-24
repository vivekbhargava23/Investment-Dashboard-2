"""Analytics & Risk page package.

The router imports ``app.ui.pages.analytics`` and calls ``render()``; this
package re-exports the shell's ``render`` so the route is unchanged after the
per-tab split (TICKET-RD4).
"""

from __future__ import annotations

from app.ui.pages.analytics._shell import render

__all__ = ["render"]
