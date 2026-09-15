from abc import ABC, abstractmethod


class DataFeed(ABC):
    """Abstract market-data feed."""

    @abstractmethod
    def fetch(self, instrument: str, timeframe: str) -> "DataFrame":
        """Fetch data for one instrument and timeframe."""

