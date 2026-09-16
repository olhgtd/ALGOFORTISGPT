"""AlgoFortis V1 — Area 10: Live Market Data Feeds & Per-User Isolation Tests (Phase 4, 5, 6)
Verifies:
- All 4 broker live feeds (Upstox, Zerodha/Kite, Dhan, Angel One) implement LiveMarketDataFeed
- Out-of-order tick protection & malformed tick handling
- Bounded backoff reconnect & staleness/heartbeat checks
- UserLiveFeedManager multi-broker concurrency per user
- Strict cross-user isolation: User A feed failure never affects User B
- Live Paper Auto-Pipe: live ticks routed directly to PaperService.process_live_quote
"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

root_dir = Path(__file__).resolve().parents[1]
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from engine.data.feeds.broker_live_feeds import (
    AngelOneLiveMarketFeed,
    DhanLiveMarketFeed,
    KiteLiveMarketFeed,
    UpstoxLiveMarketFeed,
    create_live_market_feed,
)
from engine.data.feeds.live_feed import FeedConnectionState, LiveMarketDataFeed, LiveQuoteEvent
from engine.orchestration.user_feed_manager import UserLiveFeedManager
from engine.portfolio.model import InstrumentIdentity


def _make_nifty_identity() -> InstrumentIdentity:
    return InstrumentIdentity(
        market="NSE",
        instrument="NIFTY",
        segment="INDEX",
    )


def _make_banknifty_identity() -> InstrumentIdentity:
    return InstrumentIdentity(
        market="NSE",
        instrument="BANKNIFTY",
        segment="INDEX",
    )


class MockPaperService:
    def __init__(self):
        self.received_quotes = []

    def process_live_quote(self, session_id: str, event: LiveQuoteEvent) -> dict:
        self.received_quotes.append((session_id, event))
        return {"processed": True, "event_id": event.event_id}


class TestLiveFeedsAndIsolation(unittest.TestCase):

    def test_live_feeds_conformance_and_normalization(self):
        ident = _make_nifty_identity()
        now = datetime.now(timezone.utc)

        # 1. Upstox
        up_feed = create_live_market_feed("UPSTOX")
        self.assertTrue(isinstance(up_feed, LiveMarketDataFeed))
        up_feed.connect()
        up_feed.subscribe(ident)
        up_events = []
        up_feed.add_quote_listener(lambda ev: up_events.append(ev))

        up_feed.ingest_tick({
            "timestamp": now.isoformat(),
            "bid": 24500.0,
            "ask": 24501.0,
            "last_price": 24500.5,
            "event_id": "UP-EV-1",
        }, ident)
        self.assertEqual(len(up_events), 1)
        self.assertEqual(up_events[0].quote.bid_price, Decimal("24500.0"))

        # 2. Kite
        kite_feed = create_live_market_feed("KITE")
        kite_feed.connect()
        kite_events = []
        kite_feed.add_quote_listener(lambda ev: kite_events.append(ev))
        kite_feed.ingest_tick({
            "timestamp": now.isoformat(),
            "bid": 24502.0,
            "ask": 24503.0,
            "last_price": 24502.5,
            "event_id": "KITE-EV-1",
        }, ident)
        self.assertEqual(len(kite_events), 1)
        self.assertEqual(kite_events[0].quote.bid_price, Decimal("24502.0"))

        # 3. Dhan
        dhan_feed = create_live_market_feed("DHAN")
        dhan_feed.connect()
        dhan_events = []
        dhan_feed.add_quote_listener(lambda ev: dhan_events.append(ev))
        dhan_feed.ingest_tick({
            "time": now.isoformat(),
            "bid": 24504.0,
            "ask": 24505.0,
            "LTP": 24504.5,
            "event_id": "DHAN-EV-1",
        }, ident)
        self.assertEqual(len(dhan_events), 1)
        self.assertEqual(dhan_events[0].quote.last_price, Decimal("24504.5"))

        # 4. Angel One
        angel_feed = create_live_market_feed("ANGEL_ONE")
        angel_feed.connect()
        angel_events = []
        angel_feed.add_quote_listener(lambda ev: angel_events.append(ev))
        angel_feed.ingest_tick({
            "time": now.isoformat(),
            "best_buy": 24506.0,
            "best_sell": 24507.0,
            "last_traded_price": 24506.5,
            "event_id": "ANGEL-EV-1",
        }, ident)
        self.assertEqual(len(angel_events), 1)
        self.assertEqual(angel_events[0].quote.ask_price, Decimal("24507.0"))

    def test_out_of_order_and_malformed_protection(self):
        ident = _make_nifty_identity()
        feed = create_live_market_feed("UPSTOX")
        feed.connect()
        events = []
        feed.add_quote_listener(lambda ev: events.append(ev))

        t1 = datetime(2026, 9, 1, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 9, 1, 10, 0, 1, tzinfo=timezone.utc)
        t_stale = datetime(2026, 9, 1, 9, 59, 59, tzinfo=timezone.utc)

        # Ingest t1
        feed.ingest_tick({"timestamp": t1, "bid": 24000, "ask": 24001, "last_price": 24000.5}, ident)
        self.assertEqual(len(events), 1)

        # Ingest t2
        feed.ingest_tick({"timestamp": t2, "bid": 24002, "ask": 24003, "last_price": 24002.5}, ident)
        self.assertEqual(len(events), 2)

        # Ingest t_stale (out-of-order): must be dropped
        feed.ingest_tick({"timestamp": t_stale, "bid": 23999, "ask": 24000, "last_price": 23999.5}, ident)
        self.assertEqual(len(events), 2)
        self.assertEqual(feed.out_of_order_dropped, 1)

        # Malformed tick: missing price info, must be dropped without crash
        feed.ingest_tick({"timestamp": "invalid_date", "bid": "bad_price"}, ident)
        self.assertEqual(len(events), 2)
        self.assertEqual(feed.malformed_dropped, 1)

    def test_reconnect_bounded_backoff_and_staleness(self):
        feed = create_live_market_feed("DHAN", initial_backoff_sec=0.5, max_backoff_sec=4.0)
        feed.connect()
        self.assertEqual(feed.connection_state, FeedConnectionState.CONNECTED)
        self.assertFalse(feed.is_stale(max_age_sec=10.0))

        # First reconnect
        w1 = feed.reconnect()
        self.assertEqual(feed.connection_state, FeedConnectionState.RECONNECTING)
        self.assertEqual(w1, 0.5)

        # Subsequent reconnects scale with backoff
        w2 = feed.reconnect()
        self.assertEqual(w2, 1.0)
        w3 = feed.reconnect()
        self.assertEqual(w3, 2.0)
        w4 = feed.reconnect()
        self.assertEqual(w4, 4.0)
        w5 = feed.reconnect()
        self.assertEqual(w5, 4.0)  # capped at max_backoff_sec

        # Reconnect restores connection state
        feed.connect()
        self.assertEqual(feed.connection_state, FeedConnectionState.CONNECTED)

    def test_user_feed_manager_isolation(self):
        manager = UserLiveFeedManager()
        ident_nifty = _make_nifty_identity()
        ident_bn = _make_banknifty_identity()

        # User A has 2 feeds: Upstox and Kite
        feed_a_up = manager.get_or_create_feed("user_A", "CONN-A-UP", "UPSTOX")
        feed_a_kite = manager.get_or_create_feed("user_A", "CONN-A-KT", "KITE")
        feed_a_up.connect()
        feed_a_kite.connect()

        # User B has 1 feed: Dhan
        feed_b_dhan = manager.get_or_create_feed("user_B", "CONN-B-DH", "DHAN")
        feed_b_dhan.connect()

        # Verify active feed list
        all_feeds = manager.list_active_feeds()
        self.assertEqual(len(all_feeds), 3)

        user_a_feeds = manager.list_active_feeds(user_id="user_A")
        self.assertEqual(len(user_a_feeds), 2)

        user_b_feeds = manager.list_active_feeds(user_id="user_B")
        self.assertEqual(len(user_b_feeds), 1)

        # Disconnecting User A Upstox does NOT affect User A Kite or User B Dhan
        disconnected = manager.disconnect_feed("user_A", "CONN-A-UP")
        self.assertTrue(disconnected)
        self.assertEqual(feed_a_up.connection_state, FeedConnectionState.DISCONNECTED)
        self.assertTrue(feed_a_kite.is_connected)
        self.assertTrue(feed_b_dhan.is_connected)

        # Disconnecting all User A feeds does NOT touch User B
        manager.disconnect_user_feeds("user_A")
        self.assertEqual(len(manager.list_active_feeds(user_id="user_A")), 0)
        self.assertEqual(len(manager.list_active_feeds(user_id="user_B")), 1)
        self.assertTrue(feed_b_dhan.is_connected)

    def test_live_paper_auto_pipe(self):
        manager = UserLiveFeedManager()
        ident = _make_nifty_identity()
        now = datetime.now(timezone.utc)

        feed = manager.get_or_create_feed("user_trader", "CONN-UP-01", "UPSTOX")
        feed.connect()

        paper_service = MockPaperService()
        session_id = "PAP-SES-777"

        # Attach auto-pipe
        manager.attach_paper_service_pipe("user_trader", "CONN-UP-01", session_id, paper_service)

        # Ingest live tick on feed
        feed.ingest_tick({
            "timestamp": now.isoformat(),
            "bid": 24600.0,
            "ask": 24601.0,
            "last_price": 24600.5,
            "event_id": "PIPE-TICK-01",
        }, ident)

        # Verify quote automatically reached PaperService.process_live_quote
        self.assertEqual(len(paper_service.received_quotes), 1)
        received_sid, received_ev = paper_service.received_quotes[0]
        self.assertEqual(received_sid, session_id)
        self.assertEqual(received_ev.event_id, "PIPE-TICK-01")
        self.assertEqual(received_ev.quote.last_price, Decimal("24600.5"))

        # Detach pipe
        manager.detach_paper_service_pipe("user_trader", "CONN-UP-01", session_id)
        feed.ingest_tick({
            "timestamp": (now + timedelta(seconds=1)).isoformat(),
            "bid": 24602.0,
            "ask": 24603.0,
            "last_price": 24602.5,
            "event_id": "PIPE-TICK-02",
        }, ident)
        # Should not receive tick 2 after detachment
        self.assertEqual(len(paper_service.received_quotes), 1)


if __name__ == "__main__":
    unittest.main()
