from functools import lru_cache
from pathlib import Path

from app.adapters.repo_json import JsonTransactionRepository
from app.adapters.yfinance_feed import YfinanceAdapter
from app.config import get_settings
from app.ports.fx_feed import FxProvider
from app.ports.price_feed import PriceProvider
from app.ports.repository import TransactionRepository


@lru_cache(maxsize=1)
def get_repository() -> TransactionRepository:
    settings = get_settings()
    return JsonTransactionRepository(Path(settings.portfolio_json_path))

@lru_cache(maxsize=1)
def get_price_provider() -> PriceProvider:
    return YfinanceAdapter()

@lru_cache(maxsize=1)
def get_fx_provider() -> FxProvider:
    # Same instance; YfinanceAdapter implements both PriceProvider and FxProvider.
    return get_price_provider()  # type: ignore[return-value]
