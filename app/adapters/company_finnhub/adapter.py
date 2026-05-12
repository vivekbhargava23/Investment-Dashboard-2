from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

import requests

from app.domain.company import (
    CompanyData,
    InsiderTransaction,
    InstitutionalHolder,
    NextCatalyst,
    OwnershipSnapshot,
)
from app.ports.company_data import CompanyDataError

_log = logging.getLogger(__name__)

_BASE = "https://finnhub.io/api/v1"
_TIMEOUT = 10

_INSIDER_CODE_MAP: dict[str, Literal["BUY", "SELL", "OPTION_EXERCISE", "OTHER"]] = {
    "P": "BUY",
    "S": "SELL",
    "A": "OTHER",   # award/grant
    "D": "OTHER",   # disposition
    "M": "OPTION_EXERCISE",
    "X": "OPTION_EXERCISE",
    "C": "OPTION_EXERCISE",
    "G": "OTHER",
    "F": "SELL",    # tax withholding / payment
    "I": "OTHER",
    "J": "OTHER",
    "Z": "OTHER",
}


class FinnhubCompanyAdapter:
    """Implements CompanyDataProvider using the Finnhub REST API."""

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        self._api_key = api_key

    def get_company(self, ticker: str) -> CompanyData:
        fetch_errors: dict[str, str] = {}
        next_catalyst = self._build_next_catalyst(ticker, fetch_errors)
        ownership = self._build_ownership(ticker, fetch_errors)

        now = datetime.now(UTC)
        return CompanyData(
            ticker=ticker,
            next_catalyst=next_catalyst,
            ownership=ownership,
            financials_fetched_at=now,
            fetch_errors=fetch_errors,
        )

    def refresh_section(
        self,
        ticker: str,
        section: Literal["profile", "prices", "financials"],
    ) -> CompanyData:
        return self.get_company(ticker)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{_BASE}{path}"
        p: dict[str, Any] = {"token": self._api_key}
        if params:
            p.update(params)
        resp = requests.get(url, params=p, timeout=_TIMEOUT)
        if resp.status_code == 401:
            raise CompanyDataError("Finnhub API key invalid")
        return resp

    def _build_next_catalyst(
        self, ticker: str, fetch_errors: dict[str, str]
    ) -> NextCatalyst | None:
        try:
            today = date.today()
            from_d = today.isoformat()
            to_d = (today + timedelta(days=365)).isoformat()
            resp = self._get(
                "/calendar/earnings",
                {"symbol": ticker, "from": from_d, "to": to_d},
            )
            if resp.status_code == 429:
                fetch_errors["financials"] = "rate limited"
                return None
            if resp.status_code != 200:
                return None
            data = resp.json()
            earnings_calendar = data.get("earningsCalendar", [])
            future = [
                e for e in earnings_calendar
                if e.get("date") and e["date"] >= today.isoformat()
            ]
            if not future:
                return None
            future.sort(key=lambda e: e["date"])
            next_e = future[0]
            return NextCatalyst(
                kind="EARNINGS",
                date=date.fromisoformat(next_e["date"]),
                detail=f"Earnings: {next_e.get('quarter', '')} {next_e.get('year', '')}".strip(),
            )
        except CompanyDataError:
            raise
        except Exception as exc:
            fetch_errors["financials"] = str(exc)
            return None

    def _build_ownership(
        self, ticker: str, fetch_errors: dict[str, str]
    ) -> OwnershipSnapshot | None:
        holders = self._build_institutional_holders(ticker, fetch_errors)
        insider_txns = self._build_insider_transactions(ticker, fetch_errors)
        insider_pct, inst_pct = self._get_ownership_pcts(ticker, fetch_errors)

        if holders is None and insider_txns is None and insider_pct is None and inst_pct is None:
            return None

        return OwnershipSnapshot(
            as_of=date.today(),
            insider_ownership_pct=insider_pct,
            institutional_ownership_pct=inst_pct,
            top_institutional_holders=holders or [],
            recent_insider_transactions=insider_txns or [],
        )

    def _build_institutional_holders(
        self, ticker: str, fetch_errors: dict[str, str]
    ) -> list[InstitutionalHolder] | None:
        try:
            resp = self._get("/institutional/ownership", {"symbol": ticker, "limit": 10})
            if resp.status_code == 429:
                fetch_errors["financials"] = "rate limited"
                return None
            if resp.status_code != 200:
                return None
            data = resp.json()
            ownership_list = data.get("ownership", [])
            if not ownership_list:
                return []
            result = []
            as_of_default = date.today()
            for item in ownership_list[:10]:
                try:
                    shares = int(item.get("share", 0))
                    pct = Decimal(str(float(item.get("percentOwned", 0)))) * Decimal("100")
                    change = item.get("changeInShare")
                    shares_change: int | None = int(change) if change is not None else None
                    report_date = item.get("reportDate")
                    as_of = date.fromisoformat(report_date) if report_date else as_of_default
                    result.append(
                        InstitutionalHolder(
                            name=item.get("name", ""),
                            shares_held=shares,
                            pct_of_shares_outstanding=pct,
                            shares_change_qoq=shares_change,
                            as_of=as_of,
                        )
                    )
                except Exception:
                    continue
            return result
        except CompanyDataError:
            raise
        except Exception as exc:
            fetch_errors["financials"] = str(exc)
            return None

    def _build_insider_transactions(
        self, ticker: str, fetch_errors: dict[str, str]
    ) -> list[InsiderTransaction] | None:
        try:
            cutoff = (date.today() - timedelta(days=365)).isoformat()
            resp = self._get("/stock/insider-transactions", {"symbol": ticker})
            if resp.status_code == 429:
                fetch_errors["financials"] = "rate limited"
                return None
            if resp.status_code != 200:
                return None
            data = resp.json()
            txns_raw = data.get("data", [])
            result = []
            for item in txns_raw:
                try:
                    txn_date = item.get("transactionDate", "")
                    if not txn_date or txn_date < cutoff:
                        continue
                    code = item.get("transactionCode", "")
                    txn_type = _INSIDER_CODE_MAP.get(code, "OTHER")
                    shares = abs(int(item.get("share", 0)))
                    price_raw = item.get("transactionPrice")
                    price_dec = Decimal(str(float(price_raw))) if price_raw else None
                    value_raw = item.get("transactionValue") or item.get("value")
                    value_dec = Decimal(str(float(value_raw))) if value_raw else None
                    result.append(
                        InsiderTransaction(
                            insider_name=item.get("name", ""),
                            insider_title=item.get("officerTitle"),
                            transaction_date=date.fromisoformat(txn_date),
                            transaction_type=txn_type,
                            shares=shares,
                            price_per_share=price_dec,
                            value=value_dec,
                        )
                    )
                except Exception:
                    continue
            return result
        except CompanyDataError:
            raise
        except Exception as exc:
            fetch_errors["financials"] = str(exc)
            return None

    def _get_ownership_pcts(
        self, ticker: str, fetch_errors: dict[str, str]
    ) -> tuple[Decimal | None, Decimal | None]:
        try:
            resp = self._get("/stock/profile2", {"symbol": ticker})
            if resp.status_code == 429:
                return None, None
            if resp.status_code != 200:
                return None, None
            data = resp.json()
            insider_pct: Decimal | None = None
            raw = data.get("insiderOwnershipPercentage") or data.get("insiderHoldingPercentage")
            if raw is not None:
                insider_pct = Decimal(str(float(raw))) * Decimal("100")
            return insider_pct, None
        except CompanyDataError:
            raise
        except Exception:
            return None, None
