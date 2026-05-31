"""Unit tests for isin_autoresolve service."""
from __future__ import annotations

from app.domain.money import Currency
from app.domain.tax.classification import InstrumentKind
from app.ports.ticker_resolver import TickerMatch
from app.services.isin_autoresolve import autoresolve_isin

# ─── Fakes ────────────────────────────────────────────────────────────────────

def _match(
    symbol: str,
    name: str = "",
    exchange: str = "XETRA",
    currency: Currency = Currency.EUR,
) -> TickerMatch:
    return TickerMatch(
        symbol=symbol, name=name, exchange=exchange, currency=currency, recent_price=None
    )


class FakeResolver:
    def __init__(self, results: list[TickerMatch]) -> None:
        self._results = results
        self.resolve_calls: list[tuple[str, int]] = []

    def resolve(self, query: str, limit: int = 10) -> list[TickerMatch]:
        self.resolve_calls.append((query, limit))
        return self._results

    def lookup(self, symbol: str) -> TickerMatch | None:
        return None

    def clear_cache(self) -> None:
        pass


class FakeCompanyProvider:
    def __init__(self, quote_types: dict[str, str | None] | None = None) -> None:
        self._quote_types = quote_types or {}
        self.get_quote_type_calls: list[str] = []

    def get_company(self, ticker: str) -> object:  # type: ignore[return]
        raise AssertionError("get_company must NOT be called from autoresolve_isin")

    def refresh_section(self, ticker: str, section: object) -> object:  # type: ignore[return]
        raise AssertionError("refresh_section must NOT be called from autoresolve_isin")

    def get_quote_type(self, ticker: str) -> str | None:
        self.get_quote_type_calls.append(ticker)
        return self._quote_types.get(ticker)


def _resolve(isin: str, desc: str, resolver: FakeResolver, provider: FakeCompanyProvider):  # type: ignore[return]
    return autoresolve_isin(isin, desc, resolver=resolver, company_provider=provider)


# ─── Tests: resolver outcomes ─────────────────────────────────────────────────

def test_no_matches_returns_low_confidence() -> None:
    result = _resolve("US0000000001", "Some Corp", FakeResolver([]), FakeCompanyProvider())

    assert result.ticker is None
    assert result.confidence == "low"
    assert result.instrument_kind is None


def test_single_match_returns_high_confidence() -> None:
    result = _resolve(
        "DE0007164600", "SAP SE",
        FakeResolver([_match("SAP.DE", "SAP SE")]),
        FakeCompanyProvider({"SAP.DE": "EQUITY"}),
    )

    assert result.ticker == "SAP.DE"
    assert result.confidence == "high"
    assert result.instrument_kind == InstrumentKind.AKTIE


def test_resolver_error_returns_low_confidence() -> None:
    class ErrorResolver:
        def resolve(self, query: str, limit: int = 10) -> list[TickerMatch]:
            raise RuntimeError("network error")

        def lookup(self, symbol: str) -> TickerMatch | None:
            return None

        def clear_cache(self) -> None:
            pass

    result = autoresolve_isin(
        "US0000000001", "Corp", resolver=ErrorResolver(), company_provider=FakeCompanyProvider()
    )

    assert result.ticker is None
    assert result.confidence == "low"
    assert "Resolver error" in result.reason


# ─── Tests: quoteType → InstrumentKind mapping ────────────────────────────────

def test_equity_maps_to_aktie() -> None:
    result = _resolve(
        "US67066G1040", "NVIDIA",
        FakeResolver([_match("NVDA", "NVIDIA", currency=Currency.USD)]),
        FakeCompanyProvider({"NVDA": "EQUITY"}),
    )
    assert result.instrument_kind == InstrumentKind.AKTIE


def test_etf_maps_to_aktienfonds() -> None:
    result = _resolve(
        "IE00B3XXRP09", "Vanguard S&P500",
        FakeResolver([_match("VUAA.DE", "Vanguard S&P500")]),
        FakeCompanyProvider({"VUAA.DE": "ETF"}),
    )
    assert result.instrument_kind == InstrumentKind.AKTIENFONDS


def test_mutualfund_maps_to_mischfonds() -> None:
    result = _resolve(
        "IE00B00001", "Some Fund",
        FakeResolver([_match("FUND.DE", "Some Fund")]),
        FakeCompanyProvider({"FUND.DE": "MUTUALFUND"}),
    )
    assert result.instrument_kind == InstrumentKind.MISCHFONDS


def test_unknown_quote_type_drops_to_low_confidence() -> None:
    result = _resolve(
        "DE000A27Z304", "Bitcoin ETP",
        FakeResolver([_match("BTCX.DE", "Bitcoin ETP")]),
        FakeCompanyProvider({"BTCX.DE": "CRYPTOCURRENCY"}),
    )
    assert result.instrument_kind is None
    assert result.confidence == "low"


def test_unavailable_quote_type_gives_low_confidence() -> None:
    result = _resolve(
        "DE0007164600", "SAP SE",
        FakeResolver([_match("SAP.DE", "SAP SE")]),
        FakeCompanyProvider({"SAP.DE": None}),
    )
    assert result.confidence == "low"
    assert result.instrument_kind is None


# ─── Tests: get_company is NEVER called ───────────────────────────────────────

def test_get_company_is_never_called() -> None:
    """Verifies get_quote_type() is called, not get_company()."""
    provider = FakeCompanyProvider({"SAP.DE": "EQUITY"})
    _resolve(
        "DE0007164600", "SAP SE",
        FakeResolver([_match("SAP.DE", "SAP SE")]),
        provider,
    )
    assert provider.get_quote_type_calls == ["SAP.DE"]
    # FakeCompanyProvider.get_company raises if called — reaching here means it wasn't.


# ─── Tests: multi-match scoring ───────────────────────────────────────────────

def test_eur_preferred_over_usd() -> None:
    eur_match = _match("SAP.DE", "SAP SE", currency=Currency.EUR)
    usd_match = _match("SAP", "SAP SE ADR", currency=Currency.USD)
    result = _resolve(
        "DE0007164600", "SAP SE",
        FakeResolver([usd_match, eur_match]),  # USD listed first
        FakeCompanyProvider({"SAP.DE": "EQUITY", "SAP": "EQUITY"}),
    )
    assert result.ticker == "SAP.DE"


def test_de_suffix_preferred() -> None:
    de_match = _match("BMW.DE", "BMW AG", currency=Currency.EUR)
    us_match = _match("BMWYY", "BMW AG ADR", currency=Currency.USD)
    result = _resolve(
        "DE0005190003", "BMW AG",
        FakeResolver([us_match, de_match]),
        FakeCompanyProvider({"BMW.DE": "EQUITY", "BMWYY": "EQUITY"}),
    )
    assert result.ticker == "BMW.DE"


def test_name_similarity_used() -> None:
    close_match = _match("SIEMENS.DE", "Siemens AG", currency=Currency.EUR)
    poor_match = _match("SIE.DE", "Unrelated Corp", currency=Currency.EUR)
    result = _resolve(
        "DE0007236101", "Siemens AG",
        FakeResolver([poor_match, close_match]),
        FakeCompanyProvider({"SIEMENS.DE": "EQUITY", "SIE.DE": "EQUITY"}),
    )
    assert result.ticker == "SIEMENS.DE"


# ─── Tests: result fields ─────────────────────────────────────────────────────

def test_result_includes_isin() -> None:
    isin = "DE0007164600"
    result = _resolve(isin, "SAP", FakeResolver([]), FakeCompanyProvider())
    assert result.isin == isin


def test_result_name_from_match_when_available() -> None:
    result = _resolve(
        "DE0007164600", "SAP SE",
        FakeResolver([_match("SAP.DE", "SAP SE")]),
        FakeCompanyProvider({"SAP.DE": "EQUITY"}),
    )
    assert result.name == "SAP SE"


def test_result_name_falls_back_to_description_hint() -> None:
    result = _resolve(
        "DE0000001", "My Corp",
        FakeResolver([_match("X.DE", name="")]),  # empty name in match
        FakeCompanyProvider({"X.DE": "EQUITY"}),
    )
    assert result.name == "My Corp"
