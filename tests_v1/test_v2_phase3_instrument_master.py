from __future__ import annotations

from datetime import date, time
from decimal import Decimal
from importlib import import_module

import pytest


def _instrument_api():
    try:
        return import_module("engine.data.instruments")
    except ModuleNotFoundError:
        pytest.fail("engine.data.instruments is missing", pytrace=False)


def _calendar_api():
    try:
        return import_module("engine.data.calendar")
    except ModuleNotFoundError:
        pytest.fail("engine.data.calendar is missing", pytrace=False)


def test_option_terms_normalize_symbol_and_preserve_ce_pe_expiry_metadata():
    api = _instrument_api()
    terms = api.InstrumentTerms(
        instrument_id="nifty-opt-2026-09-24-22000-ce",
        market="nse",
        symbol=" nifty26sep22000ce ",
        segment="options",
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 9, 24),
        lot_size=75,
        tick_size="0.05",
        underlying="nifty",
        expiry=date(2026, 9, 24),
        strike="22000",
        option_type="ce",
        expiry_kind="weekly",
    )

    assert terms.market == "NSE"
    assert terms.symbol == "NIFTY26SEP22000CE"
    assert terms.segment == "options"
    assert terms.underlying == "NIFTY"
    assert terms.option_type == "CE"
    assert terms.expiry_kind == "weekly"
    assert terms.strike == Decimal("22000")
    assert terms.lot_size == Decimal("75")
    assert terms.tick_size == Decimal("0.05")


def test_instrument_master_resolves_historical_lot_size_by_as_of_date():
    api = _instrument_api()
    master = api.InstrumentMaster()
    master.register(
        api.InstrumentTerms(
            instrument_id="nifty-options-family",
            market="NSE",
            symbol="NIFTY-OPTIONS",
            segment="options_family",
            effective_from=date(2025, 1, 1),
            effective_to=date(2026, 6, 30),
            lot_size=75,
            tick_size="0.05",
        )
    )
    master.register(
        api.InstrumentTerms(
            instrument_id="nifty-options-family",
            market="NSE",
            symbol="NIFTY-OPTIONS",
            segment="options_family",
            effective_from=date(2026, 7, 1),
            effective_to=None,
            lot_size=65,
            tick_size="0.05",
        )
    )

    assert master.resolve("nifty-options", date(2026, 6, 30)).lot_size == Decimal("75")
    assert master.resolve(" NIFTY-OPTIONS ", date(2026, 7, 1)).lot_size == Decimal("65")


def test_instrument_master_rejects_overlapping_effective_ranges():
    api = _instrument_api()
    master = api.InstrumentMaster()
    first = api.InstrumentTerms(
        instrument_id="banknifty-family",
        market="NSE",
        symbol="BANKNIFTY-OPTIONS",
        segment="options_family",
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        lot_size=30,
        tick_size="0.05",
    )
    master.register(first)

    with pytest.raises(api.InstrumentMasterError, match="overlap"):
        master.register(
            api.InstrumentTerms(
                instrument_id="banknifty-family",
                market="NSE",
                symbol="BANKNIFTY-OPTIONS",
                segment="options_family",
                effective_from=date(2026, 6, 1),
                effective_to=None,
                lot_size=25,
                tick_size="0.05",
            )
        )


def test_master_fingerprint_is_registration_order_independent():
    api = _instrument_api()
    a = api.InstrumentTerms(
        instrument_id="nifty-index",
        market="NSE",
        symbol="NIFTY",
        segment="index",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        lot_size=1,
        tick_size="0.05",
    )
    b = api.InstrumentTerms(
        instrument_id="banknifty-index",
        market="NSE",
        symbol="BANKNIFTY",
        segment="index",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        lot_size=1,
        tick_size="0.05",
    )
    left = api.InstrumentMaster((a, b))
    right = api.InstrumentMaster((b, a))
    assert left.fingerprint == right.fingerprint


def test_exchange_calendar_applies_holidays_sessions_and_timezone():
    api = _calendar_api()
    rule = api.TradingCalendarRule(
        market="NSE",
        timezone_name="Asia/Kolkata",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        weekdays=(0, 1, 2, 3, 4),
        session_open=time(9, 15),
        session_close=time(15, 30),
        holidays=(date(2026, 1, 26),),
    )
    calendar = api.ExchangeCalendar((rule,))

    assert calendar.is_trading_day("NSE", date(2026, 1, 26)) is False
    assert calendar.is_trading_day("NSE", date(2026, 1, 27)) is True
    start, end = calendar.session_bounds("NSE", date(2026, 1, 27))
    assert start.tzinfo is not None and start.utcoffset() is not None
    assert start.hour == 9 and start.minute == 15
    assert end.hour == 15 and end.minute == 30
    assert getattr(start.tzinfo, "key", None) == "Asia/Kolkata"


def test_calendar_abstraction_accepts_future_seven_day_market_without_crypto_implementation():
    api = _calendar_api()
    rule = api.TradingCalendarRule(
        market="FUTURE_24X7",
        timezone_name="UTC",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        weekdays=(0, 1, 2, 3, 4, 5, 6),
        session_open=time(0, 0),
        session_close=time(23, 59, 59),
        holidays=(),
    )
    calendar = api.ExchangeCalendar((rule,))
    assert calendar.is_trading_day("FUTURE_24X7", date(2026, 9, 27)) is True


def test_calendar_rejects_overlapping_rule_ranges_for_same_market():
    api = _calendar_api()
    first = api.TradingCalendarRule(
        market="NSE",
        timezone_name="Asia/Kolkata",
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        weekdays=(0, 1, 2, 3, 4),
        session_open=time(9, 15),
        session_close=time(15, 30),
        holidays=(),
    )
    second = api.TradingCalendarRule(
        market="NSE",
        timezone_name="Asia/Kolkata",
        effective_from=date(2026, 6, 1),
        effective_to=None,
        weekdays=(0, 1, 2, 3, 4),
        session_open=time(9, 15),
        session_close=time(15, 30),
        holidays=(),
    )
    with pytest.raises(api.CalendarError, match="overlap"):
        api.ExchangeCalendar((first, second))
