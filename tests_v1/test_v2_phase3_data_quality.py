from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from importlib import import_module
from zoneinfo import ZoneInfo

import pytest

from engine.data.calendar import ExchangeCalendar, TradingCalendarRule


def _api():
    try:
        return import_module("engine.data.quality")
    except ModuleNotFoundError:
        pytest.fail("engine.data.quality is missing", pytrace=False)


def _calendar() -> ExchangeCalendar:
    return ExchangeCalendar(
        (
            TradingCalendarRule(
                market="NSE",
                timezone_name="Asia/Kolkata",
                effective_from=date(2026, 1, 1),
                effective_to=None,
                weekdays=(0, 1, 2, 3, 4),
                session_open=time(9, 15),
                session_close=time(15, 30),
                holidays=(),
            ),
        )
    )


def _bar(api, minute: int, *, open_: str = "100", high: str = "102", low: str = "99", close: str = "101", volume: str = "1000", hour: int = 9):
    return api.RawBar(
        symbol="NIFTY",
        timestamp=datetime(2026, 9, 23, hour, minute, tzinfo=ZoneInfo("Asia/Kolkata")),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def test_clean_bars_receive_full_quality_score_and_no_quarantine():
    api = _api()
    pipeline = api.QualityPipeline(expected_interval=timedelta(minutes=1), outlier_return_threshold="0.20")
    bars = (_bar(api, 15), _bar(api, 16), _bar(api, 17))

    report = pipeline.analyze(bars, calendar=_calendar(), market="NSE")

    assert report.issues == ()
    assert report.accepted == bars
    assert report.quarantined == ()
    assert report.scorecard.quality_score == Decimal("100.0000")
    assert report.scorecard.coverage_ratio == Decimal("1.0000")


def test_duplicate_gap_and_out_of_order_are_detected_deterministically():
    api = _api()
    pipeline = api.QualityPipeline(expected_interval=timedelta(minutes=1), outlier_return_threshold="0.20")
    bars = (
        _bar(api, 17),
        _bar(api, 15),
        _bar(api, 15),
    )
    report = pipeline.analyze(bars, calendar=_calendar(), market="NSE")
    codes = tuple(issue.code for issue in report.issues)

    assert api.QualityIssueCode.OUT_OF_ORDER in codes
    assert api.QualityIssueCode.DUPLICATE in codes
    assert api.QualityIssueCode.GAP in codes
    assert len(report.quarantined) == 2  # duplicate timestamp is ambiguous; quarantine both copies
    assert report.scorecard.quality_score < Decimal("100")


def test_impossible_ohlc_and_negative_volume_are_quarantined_not_silently_fixed():
    api = _api()
    pipeline = api.QualityPipeline(expected_interval=timedelta(minutes=1), outlier_return_threshold="0.20")
    impossible = _bar(api, 15, open_="100", high="90", low="95", close="98")
    negative_volume = _bar(api, 16, volume="-1")

    report = pipeline.analyze((impossible, negative_volume), calendar=_calendar(), market="NSE")
    codes = {issue.code for issue in report.issues}

    assert api.QualityIssueCode.INVALID_OHLC in codes
    assert api.QualityIssueCode.NEGATIVE_VOLUME in codes
    assert report.accepted == ()
    assert report.quarantined == (impossible, negative_volume)


def test_off_session_bar_is_quarantined():
    api = _api()
    pipeline = api.QualityPipeline(expected_interval=timedelta(minutes=1), outlier_return_threshold="0.20")
    off_session = _bar(api, 0, hour=8)

    report = pipeline.analyze((off_session,), calendar=_calendar(), market="NSE")

    assert any(issue.code is api.QualityIssueCode.OFF_SESSION for issue in report.issues)
    assert report.quarantined == (off_session,)


def test_large_close_to_close_move_is_reported_as_outlier_without_rewriting_bar():
    api = _api()
    pipeline = api.QualityPipeline(expected_interval=timedelta(minutes=1), outlier_return_threshold="0.20")
    first = _bar(api, 15, open_="100", high="101", low="99", close="100")
    second = _bar(api, 16, open_="130", high="131", low="129", close="130")

    report = pipeline.analyze((first, second), calendar=_calendar(), market="NSE")

    assert any(issue.code is api.QualityIssueCode.OUTLIER for issue in report.issues)
    assert report.accepted == (first, second)
    assert second.close == Decimal("130")


def test_quality_scorecard_fingerprint_is_repeatable_and_binds_dataset_identity():
    api = _api()
    pipeline = api.QualityPipeline(expected_interval=timedelta(minutes=1), outlier_return_threshold="0.20")
    bars = (_bar(api, 15), _bar(api, 16))

    first = pipeline.analyze(bars, calendar=_calendar(), market="NSE", dataset_id="ds_demo", version_id="dsv_demo")
    second = pipeline.analyze(bars, calendar=_calendar(), market="NSE", dataset_id="ds_demo", version_id="dsv_demo")
    changed = pipeline.analyze(bars, calendar=_calendar(), market="NSE", dataset_id="ds_demo", version_id="dsv_other")

    assert first.scorecard.fingerprint == second.scorecard.fingerprint
    assert first.scorecard.fingerprint != changed.scorecard.fingerprint
    assert first.scorecard.dataset_id == "ds_demo"
    assert first.scorecard.version_id == "dsv_demo"
