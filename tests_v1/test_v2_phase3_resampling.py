from __future__ import annotations

from datetime import date, datetime, time, timedelta
from importlib import import_module
from zoneinfo import ZoneInfo

import pytest

from engine.data.calendar import ExchangeCalendar, TradingCalendarRule
from engine.data.quality import RawBar


def _api():
    try:
        return import_module("engine.data.resample")
    except ModuleNotFoundError:
        pytest.fail("engine.data.resample is missing", pytrace=False)


def _calendar() -> ExchangeCalendar:
    return ExchangeCalendar((TradingCalendarRule(
        market="NSE",
        timezone_name="Asia/Kolkata",
        effective_from=date(2026, 1, 1),
        effective_to=None,
        weekdays=(0, 1, 2, 3, 4),
        session_open=time(9, 15),
        session_close=time(15, 30),
        holidays=(),
    ),))


def _bar(minute: int, *, day: int = 23, open_: str = "100", high: str = "101", low: str = "99", close: str = "100.5", volume: str = "10") -> RawBar:
    return RawBar(
        symbol="NIFTY",
        timestamp=datetime(2026, 9, day, 9, minute, tzinfo=ZoneInfo("Asia/Kolkata")),
        open=open_, high=high, low=low, close=close, volume=volume,
    )


def test_five_minute_ohlcv_aggregation_is_session_anchored_and_decimal_preserving():
    api = _api()
    source = (
        _bar(15, open_="100", high="101", low="99", close="100.5", volume="10"),
        _bar(16, open_="100.5", high="103", low="100", close="102", volume="20"),
        _bar(17, open_="102", high="104", low="101", close="103", volume="30"),
        _bar(18, open_="103", high="105", low="102", close="104", volume="40"),
        _bar(19, open_="104", high="106", low="103", close="105", volume="50"),
    )
    result = api.DeterministicResampler(target_minutes=5).resample(source, calendar=_calendar(), market="NSE")

    assert result.issues == ()
    assert len(result.bars) == 1
    bar = result.bars[0]
    assert bar.timestamp == datetime(2026, 9, 23, 9, 15, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert str(bar.open) == "100"
    assert str(bar.high) == "106"
    assert str(bar.low) == "99"
    assert str(bar.close) == "105"
    assert str(bar.volume) == "150"
    assert bar.timeframe == "5m"
    assert bar.source_count == 5


def test_input_order_does_not_change_output_or_fingerprint():
    api = _api()
    source = tuple(_bar(minute) for minute in range(15, 20))
    first = api.DeterministicResampler(target_minutes=5).resample(source, calendar=_calendar(), market="NSE")
    second = api.DeterministicResampler(target_minutes=5).resample(tuple(reversed(source)), calendar=_calendar(), market="NSE")

    assert first.bars == second.bars
    assert first.fingerprint == second.fingerprint


def test_missing_source_minute_drops_incomplete_bucket_and_surfaces_issue():
    api = _api()
    source = tuple(_bar(minute) for minute in (15, 16, 18, 19))
    result = api.DeterministicResampler(target_minutes=5).resample(source, calendar=_calendar(), market="NSE")

    assert result.bars == ()
    assert any(issue.code is api.ResampleIssueCode.MISSING_INPUT for issue in result.issues)


def test_resampling_never_crosses_session_or_calendar_day_boundaries():
    api = _api()
    source = (
        RawBar("NIFTY", datetime(2026, 9, 23, 15, 29, tzinfo=ZoneInfo("Asia/Kolkata")), "100", "101", "99", "100", "10"),
        RawBar("NIFTY", datetime(2026, 9, 23, 15, 30, tzinfo=ZoneInfo("Asia/Kolkata")), "100", "101", "99", "100", "10"),
        _bar(15, day=24),
        _bar(16, day=24),
        _bar(17, day=24),
        _bar(18, day=24),
        _bar(19, day=24),
    )
    result = api.DeterministicResampler(target_minutes=5).resample(source, calendar=_calendar(), market="NSE")

    assert len(result.bars) == 1
    assert result.bars[0].timestamp.date() == date(2026, 9, 24)
    assert any(issue.code is api.ResampleIssueCode.INCOMPLETE_BUCKET for issue in result.issues)


def test_duplicate_source_timestamp_fails_closed_instead_of_choosing_one():
    api = _api()
    duplicate = _bar(15)
    source = (duplicate, duplicate, _bar(16), _bar(17), _bar(18), _bar(19))

    with pytest.raises(api.ResampleError, match="duplicate"):
        api.DeterministicResampler(target_minutes=5).resample(source, calendar=_calendar(), market="NSE")
