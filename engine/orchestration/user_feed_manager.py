"""AlgoFortis V1 — Per-User Multi-Broker Live Feed Manager (ADR §131 / Phase 5 & Phase 6).

Enforces:
- Strict per-user isolation: User A and User B feeds never share sockets, quote caches, or state
- Multi-broker concurrency: A user can run independent live feeds across Upstox, Kite, Dhan, Angel One
- Isolation of failure: Disconnecting one broker feed never affects unrelated feeds or other users
- Live Paper Auto-Pipe: Direct, in-process routing of live quotes to PaperService.process_live_quote
- Administrative audit visibility: Owner can list active feeds without intercepting or mutating quotes
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from engine.broker_adapters.contracts import BrokerCapability, UnsupportedCapabilityError
from engine.data.feeds.broker_live_feeds import (
    BaseLiveMarketDataFeed,
    create_live_market_feed,
)
from engine.data.feeds.live_feed import (
    FeedConnectionState,
    LiveMarketDataFeed,
    LiveQuoteEvent,
    QuoteListener,
)
from engine.portfolio.model import InstrumentIdentity

logger = logging.getLogger(__name__)


class UserLiveFeedManager:
    """Manages independent, isolated live market data feeds per user connection."""

    def __init__(self) -> None:
        self._feeds: dict[tuple[str, str], BaseLiveMarketDataFeed] = {}
        self._paper_pipes: dict[tuple[str, str], list[tuple[str, Any, QuoteListener]]] = {}
        self._lock = threading.RLock()

    def get_or_create_feed(
        self,
        user_id: str,
        connection_id: str,
        provider: str,
        **kwargs: Any,
    ) -> BaseLiveMarketDataFeed:
        """Resolve existing or instantiate a fresh isolated live feed for (user_id, connection_id)."""
        if not user_id or not str(user_id).strip():
            raise ValueError("user_id must be a non-empty string")
        if not connection_id or not str(connection_id).strip():
            raise ValueError("connection_id must be a non-empty string")

        key = (str(user_id), str(connection_id))
        with self._lock:
            if key in self._feeds:
                return self._feeds[key]

            feed = create_live_market_feed(provider, **kwargs)
            self._feeds[key] = feed
            logger.info("Created isolated live feed for user %s, connection %s (%s)", user_id, connection_id, provider)
            return feed

    def get_feed(self, user_id: str, connection_id: str) -> BaseLiveMarketDataFeed | None:
        """Get existing feed for user connection, or None if absent."""
        key = (str(user_id), str(connection_id))
        with self._lock:
            return self._feeds.get(key)

    def disconnect_feed(self, user_id: str, connection_id: str, reason: str = "manual_disconnect") -> bool:
        """Disconnect and deregister a single broker feed for a specific user connection."""
        key = (str(user_id), str(connection_id))
        with self._lock:
            feed = self._feeds.pop(key, None)
            if feed is None:
                return False

            feed.disconnect(reason=reason)

            # Cleanup attached paper pipes
            pipes = self._paper_pipes.pop(key, [])
            for _, _, listener in pipes:
                feed.remove_quote_listener(listener)

            logger.info("Disconnected isolated feed for user %s, connection %s", user_id, connection_id)
            return True

    def disconnect_user_feeds(self, user_id: str, reason: str = "user_logout") -> int:
        """Disconnect all feeds belonging to a specific user (does not touch other users)."""
        uid = str(user_id)
        with self._lock:
            matching_keys = [k for k in self._feeds.keys() if k[0] == uid]
            for key in matching_keys:
                self.disconnect_feed(key[0], key[1], reason=reason)
            return len(matching_keys)

    def subscribe_instrument(
        self,
        user_id: str,
        connection_id: str,
        identity: InstrumentIdentity,
    ) -> None:
        """Subscribe instrument on a specific user connection feed."""
        key = (str(user_id), str(connection_id))
        with self._lock:
            feed = self._feeds.get(key)
            if feed is None:
                raise KeyError(f"No active feed found for user {user_id}, connection {connection_id}")
            feed.subscribe(identity)

    def unsubscribe_instrument(
        self,
        user_id: str,
        connection_id: str,
        identity: InstrumentIdentity,
    ) -> None:
        """Unsubscribe instrument on a specific user connection feed."""
        key = (str(user_id), str(connection_id))
        with self._lock:
            feed = self._feeds.get(key)
            if feed is None:
                return
            feed.unsubscribe(identity)

    def attach_paper_service_pipe(
        self,
        user_id: str,
        connection_id: str,
        session_id: str,
        paper_service: Any,
    ) -> None:
        """Phase 6: Automatically pipe incoming live quotes directly into PaperService.process_live_quote."""
        key = (str(user_id), str(connection_id))
        with self._lock:
            feed = self._feeds.get(key)
            if feed is None:
                raise KeyError(f"No active feed for user {user_id}, connection {connection_id} to pipe to paper")

            def _live_paper_quote_listener(event: LiveQuoteEvent) -> None:
                try:
                    paper_service.process_live_quote(session_id, event)
                except Exception as exc:
                    logger.error(
                        "Error piping live quote %s to paper session %s: %s",
                        event.event_id,
                        session_id,
                        exc,
                        exc_info=True,
                    )

            feed.add_quote_listener(_live_paper_quote_listener)
            self._paper_pipes.setdefault(key, []).append((session_id, paper_service, _live_paper_quote_listener))
            logger.info(
                "Piped live feed (user=%s, conn=%s) directly to paper session %s",
                user_id,
                connection_id,
                session_id,
            )

    def detach_paper_service_pipe(
        self,
        user_id: str,
        connection_id: str,
        session_id: str,
    ) -> bool:
        """Remove live paper auto-pipe for a session."""
        key = (str(user_id), str(connection_id))
        with self._lock:
            feed = self._feeds.get(key)
            pipes = self._paper_pipes.get(key, [])
            remaining = []
            found = False
            for sid, ps, listener in pipes:
                if sid == session_id:
                    if feed:
                        feed.remove_quote_listener(listener)
                    found = True
                else:
                    remaining.append((sid, ps, listener))
            self._paper_pipes[key] = remaining
            return found

    def list_active_feeds(self, user_id: str | None = None) -> list[dict[str, Any]]:
        """List active feeds. user_id=None provides administrative/read visibility for Owner."""
        with self._lock:
            results = []
            for (uid, cid), feed in self._feeds.items():
                if user_id is not None and uid != str(user_id):
                    continue
                results.append({
                    "userId": uid,
                    "connectionId": cid,
                    "provider": feed.provider_name,
                    "connectionState": feed.connection_state.value,
                    "isConnected": feed.is_connected,
                    "isStale": feed.is_stale(),
                    "subscribedInstrumentsCount": len(feed.active_subscriptions()),
                    "lastPacketTime": feed.last_packet_time.isoformat() if feed.last_packet_time else None,
                })
            return results
