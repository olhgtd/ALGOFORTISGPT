"""Upstox read-only boundary. No mutation SDK, transport method or credentials store."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Callable
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, HTTPRedirectHandler, build_opener

UTC = timezone.utc
READ_PATHS = {
    "profile": "/v2/user/profile",
    "funds": "/v2/user/get-funds-and-margin",
    "positions": "/v2/portfolio/short-term-positions",
    "holdings": "/v2/portfolio/long-term-holdings",
    "orders": "/v2/order/retrieve-all",
    "quotes": "/v2/market-quote/quotes",
}
READ_CAPABILITIES = ("MARKET_DATA_READ", "ACCOUNT_READ", "FUNDS_READ", "POSITIONS_READ", "HOLDINGS_READ", "ORDERS_READ")
EXECUTION_CAPABILITIES = ("ORDER_PLACE", "ORDER_MODIFY", "ORDER_CANCEL")


class BrokerReadError(RuntimeError):
    """Only controlled codes cross the boundary; never upstream exception bodies."""
    def __init__(self, code: str):
        allowed = {"BROKER_REDIRECT_REJECTED", "BROKER_RESPONSE_TOO_LARGE", "BROKER_AUTH_FAILED",
            "BROKER_READ_FAILED", "BROKER_NETWORK_ERROR", "BROKER_CAPABILITY_MISSING",
            "EXTERNAL_CONNECTION_REQUIRED", "INSTRUMENT_UNRESOLVED", "BROKER_ACCOUNT_MISMATCH",
            "BROKER_RESPONSE_INVALID", "BROKER_ACCOUNT_INACTIVE"}
        self.code = code if code in allowed else "BROKER_READ_FAILED"
        super().__init__(self.code)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BrokerReadError("BROKER_REDIRECT_REJECTED")


def read_http(url: str, headers: dict) -> dict:
    request = Request(url, headers=headers, method="GET")
    try:
        with build_opener(NoRedirect()).open(request, timeout=3) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise BrokerReadError("BROKER_RESPONSE_TOO_LARGE")
            return json.loads(raw)
    except HTTPError as exc:
        raise BrokerReadError("BROKER_AUTH_FAILED" if exc.code in (401, 403) else "BROKER_READ_FAILED") from None
    except BrokerReadError:
        raise
    except Exception:
        raise BrokerReadError("BROKER_NETWORK_ERROR") from None


def safe_fields(row: dict, keys: tuple[str, ...], secret: str) -> dict:
    """Allowlist scalar read fields; strip a credential even if echoed in a safe field."""
    result = {}
    for key in keys:
        value = row.get(key)
        if isinstance(value, str):
            value = value.replace(secret, "[REDACTED]") if secret else value
            if "bearer " in value.lower():
                value = "[REDACTED]"
            value = value[:256]
        elif value is not None and not isinstance(value, (bool, int, float)):
            value = None
        if isinstance(value, float) and not math.isfinite(value):
            value = None
        result[key] = value
    return result


@dataclass(frozen=True)
class UpstoxReadConnection:
    user_id: str
    expected_account_id: str
    token_provider: Callable[[], str] = field(repr=False, compare=False)
    requester: Callable = field(default=read_http, repr=False, compare=False)
    provider: str = "UPSTOX"

    def configured(self) -> bool:
        try:
            token = self.token_provider()
            return isinstance(token, str) and bool(token.strip()) and bool(self.expected_account_id)
        except Exception:
            return False

    def read_cycle(self):
        """Freeze one credential for the account-verified read cycle, in memory only."""
        try:
            token = self.token_provider()
            if not isinstance(token, str) or not token.strip():
                raise ValueError()
            return replace(self, token_provider=lambda: token)
        except Exception:
            raise BrokerReadError("EXTERNAL_CONNECTION_REQUIRED") from None

    def read(self, resource: str, *, instrument_tokens: tuple[str, ...] = ()):
        if resource not in READ_PATHS:
            raise BrokerReadError("BROKER_CAPABILITY_MISSING")
        try:
            token = self.token_provider()
            if not isinstance(token, str) or not token.strip():
                raise BrokerReadError("EXTERNAL_CONNECTION_REQUIRED")
            token = token.strip()
            url = "https://api.upstox.com" + READ_PATHS[resource]
            if resource == "quotes":
                if not instrument_tokens or len(instrument_tokens) > 500:
                    raise BrokerReadError("INSTRUMENT_UNRESOLVED")
                url += "?" + urlencode({"instrument_key": ",".join(instrument_tokens)})
            payload = self.requester(url, {"Authorization": f"Bearer {token}", "Accept": "application/json"})
            if not isinstance(payload, dict) or payload.get("status") != "success":
                raise BrokerReadError("BROKER_READ_FAILED")
            data = payload.get("data")
            if resource == "profile":
                if not isinstance(data, dict) or data.get("user_id") != self.expected_account_id:
                    raise BrokerReadError("BROKER_ACCOUNT_MISMATCH")
                return safe_fields(data, ("user_id", "broker", "is_active"), token)
            if resource == "funds":
                if not isinstance(data, dict) or not isinstance(data.get("equity"), dict):
                    raise BrokerReadError("BROKER_RESPONSE_INVALID")
                return safe_fields(data["equity"], ("available_margin", "used_margin", "exposure_margin"), token)
            if resource == "quotes":
                if not isinstance(data, dict):
                    raise BrokerReadError("BROKER_RESPONSE_INVALID")
                result = []
                for row in data.values():
                    if not isinstance(row, dict) or row.get("instrument_token") not in instrument_tokens:
                        raise BrokerReadError("INSTRUMENT_UNRESOLVED")
                    clean = safe_fields(row, ("instrument_token", "last_price", "last_trade_time"), token)
                    depth = row.get("depth") or {}
                    for side in ("buy", "sell"):
                        levels = depth.get(side) or []
                        clean["bid" if side == "buy" else "ask"] = safe_fields(levels[0], ("price",), token)["price"] if levels else None
                    result.append(clean)
                return result
            if not isinstance(data, list) or not all(isinstance(row, dict) for row in data):
                raise BrokerReadError("BROKER_RESPONSE_INVALID")
            keys = {
                "orders": ("order_id", "instrument_token", "trading_symbol", "transaction_type", "quantity", "filled_quantity", "pending_quantity", "average_price", "price", "order_type", "status", "order_timestamp", "exchange_timestamp"),
                "positions": ("instrument_token", "trading_symbol", "exchange", "product", "quantity", "average_price", "last_price", "value", "pnl", "realised", "unrealised"),
                "holdings": ("instrument_token", "trading_symbol", "exchange", "quantity", "average_price", "last_price", "pnl"),
            }[resource]
            return [safe_fields(row, keys, token) for row in data]
        except BrokerReadError:
            raise
        except Exception:
            raise BrokerReadError("BROKER_RESPONSE_INVALID") from None
