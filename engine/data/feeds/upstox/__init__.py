"""Upstox Market Data Feed V3 package.

Provides operational live market data feed adapter, authorization client,
Protobuf decoder, instrument catalog loader, normalizer, and serialized dispatcher.
"""

from engine.data.feeds.upstox.auth import (
    UpstoxAuthError,
    UpstoxV3AuthorizationClient,
)
from engine.data.feeds.upstox.catalog_loader import (
    UpstoxCatalogLoaderError,
    UpstoxInstrumentCatalogLoader,
)
from engine.data.feeds.upstox.decoder import (
    UpstoxDecodeError,
    UpstoxV3Decoder,
)
from engine.data.feeds.upstox.dispatcher import (
    BarHandler,
    CorruptPayloadHandler,
    MarketTimeHandler,
    OverflowHandler,
    QuoteHandler,
    UpstoxFrameEnvelope,
    UpstoxSerializedDispatcher,
)
from engine.data.feeds.upstox.feed import (
    BarListener,
    MarketTimeListener,
    StateListener,
    UpstoxLiveMarketDataFeed,
    UpstoxStartupPhase,
)
from engine.data.feeds.upstox.normalizer import (
    NormalizedBatch,
    UpstoxNormalizerError,
    UpstoxV3Normalizer,
)

__all__ = [
    # Auth
    "UpstoxAuthError",
    "UpstoxV3AuthorizationClient",
    # Decoder
    "UpstoxDecodeError",
    "UpstoxV3Decoder",
    # Catalog Loader
    "UpstoxCatalogLoaderError",
    "UpstoxInstrumentCatalogLoader",
    # Normalizer
    "NormalizedBatch",
    "UpstoxNormalizerError",
    "UpstoxV3Normalizer",
    # Dispatcher
    "BarHandler",
    "CorruptPayloadHandler",
    "MarketTimeHandler",
    "OverflowHandler",
    "QuoteHandler",
    "UpstoxFrameEnvelope",
    "UpstoxSerializedDispatcher",
    # Feed Adapter
    "BarListener",
    "MarketTimeListener",
    "StateListener",
    "UpstoxLiveMarketDataFeed",
    "UpstoxStartupPhase",
]
