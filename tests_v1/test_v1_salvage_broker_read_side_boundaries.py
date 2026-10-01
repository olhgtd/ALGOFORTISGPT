"""Manual-V1 four-broker read-side salvage guards.

These tests preserve provider-edge quote normalization while explicitly keeping
legacy mutation-capable adapters out of sensitive V2 Live/Risk modules.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from engine.data.feeds.broker_live_feeds import (
    AngelOneQuoteNormalizer,
    DhanQuoteNormalizer,
    KiteQuoteNormalizer,
    UpstoxQuoteNormalizer,
)
from engine.portfolio.model import InstrumentIdentity


_REPO_ROOT = Path(__file__).resolve().parents[1]
_IDENTITY = InstrumentIdentity("NSE", "NIFTY", "index")


def test_upstox_quote_normalizer_preserves_canonical_prices_and_source() -> None:
    quote = UpstoxQuoteNormalizer().normalize(
        {
            "timestamp": "2026-09-29T09:15:00+05:30",
            "bid": "24600.10",
            "ask": "24600.25",
            "last_price": "24600.20",
        },
        _IDENTITY,
    )

    assert quote.instrument_identity == _IDENTITY
    assert quote.bid_price == Decimal("24600.10")
    assert quote.ask_price == Decimal("24600.25")
    assert quote.last_price == Decimal("24600.20")
    assert quote.source == "UPSTOX"


def test_kite_quote_normalizer_preserves_canonical_prices_and_source() -> None:
    quote = KiteQuoteNormalizer().normalize(
        {
            "timestamp": "2026-09-29T09:16:00+05:30",
            "bid": "24601.00",
            "ask": "24601.20",
            "last_price": "24601.10",
        },
        _IDENTITY,
    )

    assert quote.bid_price == Decimal("24601.00")
    assert quote.ask_price == Decimal("24601.20")
    assert quote.last_price == Decimal("24601.10")
    assert quote.source == "ZERODHA_KITE"


def test_dhan_quote_normalizer_supports_ltp_and_naive_exchange_time_as_ist() -> None:
    quote = DhanQuoteNormalizer().normalize(
        {
            "time": "2026-09-29T09:17:00",
            "bid": "24602.00",
            "ask": "24602.30",
            "LTP": "24602.15",
        },
        _IDENTITY,
    )

    assert quote.last_price == Decimal("24602.15")
    assert quote.source == "DHAN"
    assert quote.exchange_timestamp.utcoffset() == timedelta(hours=5, minutes=30)


def test_angel_one_quote_normalizer_supports_provider_alias_fields() -> None:
    quote = AngelOneQuoteNormalizer().normalize(
        {
            "time": "2026-09-29T09:18:00",
            "best_buy": "24603.00",
            "best_sell": "24603.40",
            "last_traded_price": "24603.20",
        },
        _IDENTITY,
    )

    assert quote.bid_price == Decimal("24603.00")
    assert quote.ask_price == Decimal("24603.40")
    assert quote.last_price == Decimal("24603.20")
    assert quote.source == "ANGEL_ONE"
    assert quote.exchange_timestamp.utcoffset() == timedelta(hours=5, minutes=30)


def test_quote_normalizers_do_not_fabricate_absent_optional_prices() -> None:
    quote = UpstoxQuoteNormalizer().normalize(
        {"timestamp": "2026-09-29T09:19:00+05:30"},
        _IDENTITY,
    )

    assert quote.bid_price is None
    assert quote.ask_price is None
    assert quote.last_price is None


def test_sensitive_v2_live_and_risk_modules_do_not_import_legacy_concrete_adapters() -> None:
    forbidden = (
        "engine.broker_adapters.upstox_adapter",
        "engine.broker_adapters.kite_adapter",
        "engine.broker_adapters.dhan_adapter",
        "engine.broker_adapters.angel_adapter",
        "engine.broker_adapters.factory",
    )

    violations: list[str] = []
    for relative_root in (Path("engine/live"), Path("engine/risk")):
        for path in (_REPO_ROOT / relative_root).rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            for module in forbidden:
                if module in source:
                    violations.append(f"{path.relative_to(_REPO_ROOT).as_posix()}: {module}")

    assert violations == []
