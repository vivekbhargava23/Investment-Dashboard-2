# DEPRECATED: The YfinanceAdapter god-class has been split into per-protocol adapters.
# Use the dedicated adapters instead:
#   app.adapters.yfinance_price    → PriceProvider
#   app.adapters.yfinance_ohlc     → OhlcDataProvider
#   app.adapters.yfinance_resolver → TickerResolver
#   app.adapters.fx_yfinance       → FxProvider (YfinanceLiveFxAdapter)
#
# YfinanceAdapter is an alias for YfinancePriceAdapter kept for one release.
# It will be removed in a future ticket.
from app.adapters.yfinance_price.adapter import YfinancePriceAdapter as YfinanceAdapter

__all__ = ["YfinanceAdapter"]
