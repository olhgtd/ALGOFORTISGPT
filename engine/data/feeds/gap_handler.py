import pandas as pd


OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
OUTPUT_COLUMNS = OHLCV_COLUMNS + ["is_gap_filled", "signal_eligible"]


def fill_missing_candles(data: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Insert and flag missing IST candles for indicator continuity only."""
    candles = data[OHLCV_COLUMNS].copy()
    timestamps = pd.to_datetime(candles["timestamp"])
    if timestamps.dt.tz is None:
        candles["timestamp"] = timestamps.dt.tz_localize("Asia/Kolkata")
    else:
        candles["timestamp"] = timestamps.dt.tz_convert("Asia/Kolkata")

    if candles.empty:
        candles["is_gap_filled"] = False
        candles["signal_eligible"] = True
        return candles[OUTPUT_COLUMNS]

    candles = candles.sort_values("timestamp")
    real_candles = candles.set_index("timestamp")
    expected_timestamps = pd.date_range(
        start=real_candles.index.min(),
        end=real_candles.index.max(),
        freq=pd.to_timedelta(timeframe),
    )
    filled_candles = real_candles.reindex(expected_timestamps)
    synthetic_rows = ~filled_candles.index.isin(real_candles.index)

    ohlc_columns = ["open", "high", "low", "close"]
    forward_filled_ohlc = filled_candles[ohlc_columns].ffill()
    filled_candles.loc[synthetic_rows, ohlc_columns] = forward_filled_ohlc.loc[
        synthetic_rows, ohlc_columns
    ]
    filled_candles.loc[synthetic_rows, "volume"] = 0
    filled_candles["is_gap_filled"] = synthetic_rows
    filled_candles["signal_eligible"] = ~synthetic_rows

    filled_candles.index.name = "timestamp"
    return filled_candles.reset_index()[OUTPUT_COLUMNS]
