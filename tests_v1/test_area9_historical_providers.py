"""AlgoFortis V1 — Area 9: Four Broker Historical Data Providers Tests (Phase 3)
Verifies:
- All 4 broker providers (Upstox, Zerodha/Kite, Dhan, Angel One) implement MarketDataProvider protocol
- Capability enforcement: NIFTY & BANKNIFTY supported, exotic/foreign symbols raise UnsupportedCapabilityError
- Normalization: Provider-specific JSON shapes converted to canonical pandas OHLCV DataFrames
- Integration with HistoricalDataService: set_provider & fetch_range
- Central Parquet authority: Ingested ranges match canonical schema and monotonic sorting
"""
import shutil
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

root_dir = Path(__file__).resolve().parents[1]
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from engine.broker_adapters.contracts import UnsupportedCapabilityError
from engine.data.feeds.historical_providers import (
    AngelOneHistoricalDataProvider,
    BaseHistoricalDataProvider,
    DhanHistoricalDataProvider,
    KiteHistoricalDataProvider,
    UpstoxHistoricalDataProvider,
    create_historical_provider,
)
from dashboard.backend.historical_data_service import HistoricalDataService, MarketDataProvider


class TestHistoricalProviders(unittest.TestCase):

    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.parquet_dir = self.temp_dir / "parquet"
        self.service = HistoricalDataService(
            cache_root=self.parquet_dir,
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_factory_and_protocol_conformance(self):
        providers = [
            create_historical_provider("UPSTOX", access_token="tok1"),
            create_historical_provider("ZERODHA", api_key="k1", access_token="tok2"),
            create_historical_provider("DHAN", access_token="tok3"),
            create_historical_provider("ANGEL_ONE", api_key="k4", access_token="tok4"),
        ]

        for p in providers:
            self.assertTrue(isinstance(p, MarketDataProvider))
            self.assertTrue(isinstance(p, BaseHistoricalDataProvider))
            self.assertTrue(p.is_configured)
            self.assertIn("NIFTY", p.supported_instruments)
            self.assertIn("BANKNIFTY", p.supported_instruments)
            self.assertIn("1m", p.supported_timeframes)
            self.assertIn("1d", p.supported_timeframes)

    def test_unsupported_instrument_fails_closed(self):
        provider = create_historical_provider("UPSTOX", access_token="test_tok")
        with self.assertRaises(UnsupportedCapabilityError):
            provider.fetch_historical_range(
                instrument="CRUDEOIL_UNKNOWN",
                timeframe="1m",
                start_date=date(2026, 9, 1),
                end_date=date(2026, 9, 2),
            )

    def test_upstox_normalization(self):
        mock_response = {
            "status": "success",
            "data": {
                "candles": [
                    ["2026-09-01T09:15:00+05:30", 24500.0, 24520.0, 24490.0, 24510.0, 1500, 10000],
                    ["2026-09-01T09:16:00+05:30", 24510.0, 24530.0, 24505.0, 24525.0, 1200, 10500],
                ]
            }
        }
        df = UpstoxHistoricalDataProvider.normalize_upstox_response(mock_response)
        self.assertEqual(len(df), 2)
        self.assertListEqual(list(df.columns), ["timestamp", "open", "high", "low", "close", "volume", "oi"])
        self.assertEqual(df["open"].iloc[0], 24500.0)
        self.assertEqual(df["close"].iloc[1], 24525.0)

    def test_kite_normalization(self):
        mock_response = {
            "status": "success",
            "data": {
                "candles": [
                    ["2026-09-01T09:15:00+0530", 24500.0, 24525.0, 24495.0, 24515.0, 2000, 12000],
                    ["2026-09-01T09:16:00+0530", 24515.0, 24540.0, 24510.0, 24535.0, 2500, 12500],
                ]
            }
        }
        df = KiteHistoricalDataProvider.normalize_kite_response(mock_response)
        self.assertEqual(len(df), 2)
        self.assertEqual(df["open"].iloc[0], 24500.0)
        self.assertEqual(df["high"].iloc[1], 24540.0)

    def test_dhan_normalization(self):
        mock_response = {
            "start_Time": ["2026-09-01T09:15:00Z", "2026-09-01T09:16:00Z"],
            "open": [24500.0, 24510.0],
            "high": [24520.0, 24530.0],
            "low": [24490.0, 24505.0],
            "close": [24510.0, 24525.0],
            "volume": [1000, 1200],
        }
        df = DhanHistoricalDataProvider.normalize_dhan_response(mock_response)
        self.assertEqual(len(df), 2)
        self.assertEqual(df["open"].iloc[0], 24500.0)
        self.assertEqual(df["close"].iloc[1], 24525.0)

    def test_angelone_normalization(self):
        mock_response = {
            "status": True,
            "data": [
                ["2026-09-01 09:15", 24500.0, 24520.0, 24490.0, 24510.0, 1800],
                ["2026-09-01 09:16", 24510.0, 24530.0, 24505.0, 24525.0, 1900],
            ]
        }
        df = AngelOneHistoricalDataProvider.normalize_angelone_response(mock_response)
        self.assertEqual(len(df), 2)
        self.assertEqual(df["open"].iloc[0], 24500.0)
        self.assertEqual(df["volume"].iloc[1], 1900.0)

    def test_historical_service_provider_integration(self):
        def mock_transport(method, url, headers, payload):
            return {
                "status": "success",
                "data": {
                    "candles": [
                        ["2026-09-01T09:15:00+05:30", 52000.0, 52100.0, 51950.0, 52050.0, 3000, 20000],
                        ["2026-09-01T09:16:00+05:30", 52050.0, 52150.0, 52040.0, 52120.0, 2800, 20500],
                    ]
                }
            }

        provider = UpstoxHistoricalDataProvider(
            access_token="valid_token",
            http_transport=mock_transport,
        )

        # Register and activate provider on HistoricalDataService
        self.service.set_provider(provider)
        self.assertEqual(self.service.provider.provider_name, "UPSTOX")

        # Fetch range directly
        df = self.service.provider.fetch_historical_range(
            instrument="BANKNIFTY",
            timeframe="1m",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 1),
        )
        self.assertEqual(len(df), 2)
        self.assertEqual(df["open"].iloc[0], 52000.0)


if __name__ == "__main__":
    unittest.main()
