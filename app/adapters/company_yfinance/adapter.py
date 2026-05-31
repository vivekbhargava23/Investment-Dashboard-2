from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import pandas as pd
import yfinance as yf

from app.domain.company import (
    AnnualFundamentals,
    CompanyData,
    CompanyProfile,
    CurrentMultiples,
    DividendEvent,
    LatestQuote,
    PriceHistoryPoint,
    QuarterlyFundamentals,
)
from app.domain.money import Currency, Money
from app.ports.company_data import CompanyDataError

_log = logging.getLogger(__name__)

_CURRENCY_MAP = {
    "EUR": Currency.EUR,
    "USD": Currency.USD,
    "JPY": Currency.JPY,
}


def _to_decimal(val: object) -> Decimal | None:
    if val is None:
        return None
    try:
        f = float(val)  # type: ignore[arg-type]
        if f != f:  # NaN
            return None
        return Decimal(str(f))
    except (TypeError, ValueError):
        return None


def _to_int(val: object) -> int | None:
    if val is None:
        return None
    try:
        return int(float(val))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _safe_currency(raw: str | None) -> str:
    return raw if raw else "USD"


class YfinanceCompanyAdapter:
    """Implements CompanyDataProvider using yfinance."""

    def get_company(self, ticker: str) -> CompanyData:
        t = yf.Ticker(ticker)
        try:
            info = t.info
        except Exception as exc:
            raise CompanyDataError(f"Ticker {ticker!r} not found: {exc}") from exc

        if not info or (info.get("regularMarketPrice") is None and info.get("symbol") is None):
            raise CompanyDataError(f"Ticker {ticker!r} not found")

        fetch_errors: dict[str, str] = {}
        profile = self._build_profile(ticker, info, fetch_errors)
        latest_quote = self._build_latest_quote(ticker, info, fetch_errors)
        price_history = self._build_price_history(ticker, t, fetch_errors)
        quarterly = self._build_quarterly_fundamentals(ticker, t, fetch_errors)
        annual = self._build_annual_fundamentals(ticker, t, fetch_errors)
        multiples = self._build_current_multiples(ticker, info, t, fetch_errors)
        dividends = self._build_dividends(ticker, t, fetch_errors)

        now = datetime.now(UTC)
        return CompanyData(
            ticker=ticker,
            quote_type=info.get("quoteType"),
            profile=profile,
            latest_quote=latest_quote,
            price_history=price_history,
            quarterly_fundamentals=quarterly,
            annual_fundamentals=annual,
            current_multiples=multiples,
            dividends=dividends,
            ownership=None,
            next_catalyst=None,
            profile_fetched_at=now,
            prices_fetched_at=now,
            financials_fetched_at=now,
            fetch_errors=fetch_errors,
        )

    def refresh_section(
        self,
        ticker: str,
        section: Literal["profile", "prices", "financials"],
    ) -> CompanyData:
        return self.get_company(ticker)

    def _build_profile(
        self,
        ticker: str,
        info: dict,  # type: ignore[type-arg]
        fetch_errors: dict[str, str],
    ) -> CompanyProfile | None:
        try:
            raw_currency = info.get("currency") or "USD"
            currency_str = _safe_currency(raw_currency)
            raw_mcap = info.get("marketCap")
            market_cap: Money | None = None
            if raw_mcap is not None:
                try:
                    c = _CURRENCY_MAP.get(currency_str, Currency.USD)
                    market_cap = Money(amount=Decimal(str(int(raw_mcap))), currency=c)
                except Exception:
                    pass

            return CompanyProfile(
                ticker=ticker,
                name=info.get("longName") or info.get("shortName") or ticker,
                isin=info.get("isin"),
                sector=info.get("sector"),
                industry=info.get("industry"),
                country=info.get("country"),
                currency=currency_str,
                employees=_to_int(info.get("fullTimeEmployees")),
                market_cap=market_cap,
                long_description=info.get("longBusinessSummary"),
            )
        except Exception as exc:
            fetch_errors["profile"] = str(exc)
            return None

    def _build_latest_quote(
        self,
        ticker: str,
        info: dict,  # type: ignore[type-arg]
        fetch_errors: dict[str, str],
    ) -> LatestQuote | None:
        try:
            raw_price = info.get("regularMarketPrice") or info.get("currentPrice")
            raw_prev = info.get("regularMarketPreviousClose") or info.get("previousClose")
            if raw_price is None or raw_prev is None:
                fetch_errors["prices"] = "regularMarketPrice or previousClose missing"
                return None
            currency_str = _safe_currency(info.get("currency"))
            currency = _CURRENCY_MAP.get(currency_str, Currency.USD)
            price = Money(amount=Decimal(str(float(raw_price))), currency=currency)
            prev = Money(amount=Decimal(str(float(raw_prev))), currency=currency)
            raw_change = info.get("regularMarketChangePercent")
            if raw_change is not None:
                change_pct = Decimal(str(float(raw_change)))
            elif float(raw_prev) != 0:
                change_pct = (price.amount - prev.amount) / prev.amount * Decimal("100")
            else:
                change_pct = Decimal("0")
            return LatestQuote(
                ticker=ticker,
                price=price,
                previous_close=prev,
                day_change_pct=change_pct,
                as_of=datetime.now(UTC),
            )
        except Exception as exc:
            fetch_errors["prices"] = str(exc)
            return None

    def _build_price_history(
        self,
        ticker: str,
        t: yf.Ticker,
        fetch_errors: dict[str, str],
    ) -> list[PriceHistoryPoint]:
        try:
            hist = t.history(period="5y")
            if hist.empty:
                return []
            result = []
            for idx, row in hist.iterrows():
                close = _to_decimal(row.get("Close"))
                if close is None:
                    continue
                volume = _to_int(row.get("Volume"))
                d = idx.date() if hasattr(idx, "date") else idx
                result.append(PriceHistoryPoint(date=d, close=close, volume=volume))
            return result
        except Exception as exc:
            fetch_errors["prices"] = str(exc)
            return []

    def _build_quarterly_fundamentals(
        self,
        ticker: str,
        t: yf.Ticker,
        fetch_errors: dict[str, str],
    ) -> list[QuarterlyFundamentals]:
        try:
            fin = t.quarterly_financials
            bal = t.quarterly_balance_sheet
            cf = t.quarterly_cashflow
            if fin is None or (hasattr(fin, "empty") and fin.empty):
                return []
            currency = _safe_currency(getattr(t, "info", {}).get("financialCurrency"))
            result = []
            for col in list(fin.columns)[:20]:
                try:
                    period_end = col.date() if hasattr(col, "date") else col
                    rev = _to_decimal(_get_row(fin, col, "Total Revenue"))
                    gp = _to_decimal(_get_row(fin, col, "Gross Profit"))
                    ebit = _to_decimal(_get_row(fin, col, "EBIT"))
                    if ebit is None:
                        ebit = _to_decimal(_get_row(fin, col, "Operating Income"))
                    ni = _to_decimal(_get_row(fin, col, "Net Income"))
                    eps = _to_decimal(_get_row(fin, col, "Diluted EPS"))
                    shares = _to_int(_get_row(fin, col, "Diluted Average Shares"))

                    fcf_raw = _to_decimal(_get_row(cf, col, "Free Cash Flow"))
                    if fcf_raw is None:
                        ops = _to_decimal(_get_row(cf, col, "Operating Cash Flow"))
                        capex = _to_decimal(_get_row(cf, col, "Capital Expenditure"))
                        if ops is not None and capex is not None:
                            fcf_raw = ops + capex  # capex is usually negative in yfinance

                    debt = _to_decimal(_get_row(bal, col, "Total Debt"))
                    if debt is None:
                        debt = _to_decimal(_get_row(bal, col, "Long Term Debt"))
                    cash = _to_decimal(_get_row(bal, col, "Cash And Cash Equivalents"))
                    if cash is None:
                        _cash_key = "Cash Cash Equivalents And Short Term Investments"
                        cash = _to_decimal(_get_row(bal, col, _cash_key))

                    net_debt = (debt - cash) if debt is not None and cash is not None else None

                    depr = _to_decimal(_get_row(cf, col, "Depreciation And Amortization"))
                    if depr is None:
                        depr = _to_decimal(_get_row(cf, col, "Depreciation Amortization Depletion"))
                    ebitda = (ebit + depr) if ebit is not None and depr is not None else None

                    result.append(
                        QuarterlyFundamentals(
                            period_end=period_end,
                            revenue=rev,
                            gross_profit=gp,
                            operating_income=ebit,
                            net_income=ni,
                            free_cash_flow=fcf_raw,
                            eps_diluted=eps,
                            shares_diluted=shares,
                            total_debt=debt,
                            cash_and_equivalents=cash,
                            net_debt=net_debt,
                            ebitda=ebitda,
                            currency=currency,
                        )
                    )
                except Exception:
                    continue
            return result
        except Exception as exc:
            fetch_errors["financials"] = str(exc)
            return []

    def _build_annual_fundamentals(
        self,
        ticker: str,
        t: yf.Ticker,
        fetch_errors: dict[str, str],
    ) -> list[AnnualFundamentals]:
        try:
            fin = t.financials
            bal = t.balance_sheet
            cf = t.cashflow
            if fin is None or (hasattr(fin, "empty") and fin.empty):
                return []
            currency = _safe_currency(getattr(t, "info", {}).get("financialCurrency"))
            result = []
            for col in list(fin.columns)[:10]:
                try:
                    period_end = col.date() if hasattr(col, "date") else col
                    fiscal_year = period_end.year
                    rev = _to_decimal(_get_row(fin, col, "Total Revenue"))
                    gp = _to_decimal(_get_row(fin, col, "Gross Profit"))
                    ebit = _to_decimal(_get_row(fin, col, "EBIT"))
                    if ebit is None:
                        ebit = _to_decimal(_get_row(fin, col, "Operating Income"))
                    ni = _to_decimal(_get_row(fin, col, "Net Income"))
                    eps = _to_decimal(_get_row(fin, col, "Diluted EPS"))
                    shares = _to_int(_get_row(fin, col, "Diluted Average Shares"))

                    ops = _to_decimal(_get_row(cf, col, "Operating Cash Flow"))
                    capex = _to_decimal(_get_row(cf, col, "Capital Expenditure"))
                    fcf: Decimal | None = None
                    if ops is not None and capex is not None:
                        fcf = ops + capex
                    elif ops is not None:
                        fcf = _to_decimal(_get_row(cf, col, "Free Cash Flow")) or ops

                    debt = _to_decimal(_get_row(bal, col, "Total Debt"))
                    if debt is None:
                        debt = _to_decimal(_get_row(bal, col, "Long Term Debt"))
                    cash = _to_decimal(_get_row(bal, col, "Cash And Cash Equivalents"))
                    if cash is None:
                        _cash_key = "Cash Cash Equivalents And Short Term Investments"
                        cash = _to_decimal(_get_row(bal, col, _cash_key))

                    net_debt = (debt - cash) if debt is not None and cash is not None else None

                    depr = _to_decimal(_get_row(cf, col, "Depreciation And Amortization"))
                    if depr is None:
                        depr = _to_decimal(_get_row(cf, col, "Depreciation Amortization Depletion"))
                    ebitda = (ebit + depr) if ebit is not None and depr is not None else None

                    buybacks = _to_decimal(_get_row(cf, col, "Repurchase Of Capital Stock"))
                    if buybacks is None:
                        buybacks = _to_decimal(_get_row(cf, col, "Common Stock Repurchased"))
                    divs_paid = _to_decimal(_get_row(cf, col, "Common Stock Dividend Paid"))
                    if divs_paid is None:
                        divs_paid = _to_decimal(_get_row(cf, col, "Payment Of Dividends"))
                    sbc = _to_decimal(_get_row(cf, col, "Stock Based Compensation"))

                    result.append(
                        AnnualFundamentals(
                            fiscal_year=fiscal_year,
                            period_end=period_end,
                            revenue=rev,
                            gross_profit=gp,
                            operating_income=ebit,
                            net_income=ni,
                            free_cash_flow=fcf,
                            eps_diluted=eps,
                            shares_diluted=shares,
                            total_debt=debt,
                            cash_and_equivalents=cash,
                            net_debt=net_debt,
                            ebitda=ebitda,
                            capex=capex,
                            buybacks=buybacks,
                            dividends_paid=divs_paid,
                            stock_based_compensation=sbc,
                            currency=currency,
                        )
                    )
                except Exception:
                    continue
            return result
        except Exception as exc:
            fetch_errors["financials"] = str(exc)
            return []

    def _build_current_multiples(
        self,
        ticker: str,
        info: dict,  # type: ignore[type-arg]
        t: yf.Ticker,
        fetch_errors: dict[str, str],
    ) -> CurrentMultiples | None:
        try:
            pe = _to_decimal(info.get("trailingPE"))
            ps = _to_decimal(info.get("priceToSalesTrailing12Months"))
            ev_ebitda = _to_decimal(info.get("enterpriseToEbitda"))
            p_book = _to_decimal(info.get("priceToBook"))
            div_yield = _to_decimal(info.get("dividendYield"))
            if div_yield is not None:
                div_yield = div_yield * Decimal("100")  # convert fraction to pct

            p_fcf: Decimal | None = None
            try:
                price_raw = info.get("regularMarketPrice") or info.get("currentPrice")
                shares_raw = info.get("sharesOutstanding")
                if price_raw and shares_raw:
                    price_d = Decimal(str(float(price_raw)))
                    shares_d = Decimal(str(int(shares_raw)))
                    mcap = price_d * shares_d
                    # Look for TTM FCF from cashflow
                    cf = t.cashflow
                    if cf is not None and not cf.empty and len(cf.columns) >= 1:
                        latest_col = cf.columns[0]
                        ops = _to_decimal(_get_row(cf, latest_col, "Operating Cash Flow"))
                        capex = _to_decimal(_get_row(cf, latest_col, "Capital Expenditure"))
                        if ops is not None and capex is not None:
                            ttm_fcf = ops + capex
                            if ttm_fcf and ttm_fcf > Decimal("0") and mcap > Decimal("0"):
                                p_fcf = mcap / ttm_fcf
            except Exception:
                pass

            return CurrentMultiples(
                as_of=datetime.now(UTC),
                pe_trailing=pe,
                ps_trailing=ps,
                ev_ebitda=ev_ebitda,
                p_fcf=p_fcf,
                p_book=p_book,
                dividend_yield_pct=div_yield,
            )
        except Exception as exc:
            fetch_errors["financials"] = str(exc)
            return None

    def _build_dividends(
        self,
        ticker: str,
        t: yf.Ticker,
        fetch_errors: dict[str, str],
    ) -> list[DividendEvent]:
        try:
            divs = t.dividends
            if divs is None or (hasattr(divs, "empty") and divs.empty):
                return []
            currency = _safe_currency(getattr(t, "info", {}).get("currency"))
            result = []
            for idx, amount in divs.items():
                try:
                    d = idx.date() if hasattr(idx, "date") else idx
                    amt = _to_decimal(amount)
                    if amt is None:
                        continue
                    result.append(DividendEvent(ex_date=d, amount_per_share=amt, currency=currency))
                except Exception:
                    continue
            return result
        except Exception as exc:
            fetch_errors["financials"] = str(exc)
            return []


def _get_row(df: pd.DataFrame, col: object, row_label: str) -> object:
    """Return df.loc[row_label, col] if it exists, else None."""
    if df is None or (hasattr(df, "empty") and df.empty):
        return None
    if row_label not in df.index:
        return None
    try:
        val = df.loc[row_label, col]
        if hasattr(val, "__float__") and float(val) != float(val):  # NaN
            return None
        return val
    except Exception:
        return None
