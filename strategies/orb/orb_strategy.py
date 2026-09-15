"""Opening Range Breakout strategy contract skeleton."""

from engine.strategy.base import StrategySignalGenerator


class ORBStrategy(StrategySignalGenerator):
    """StrategySignalGenerator skeleton for the Opening Range Breakout strategy."""

    interface_version = "1.0"
    required_timeframes = ["5m"]
    state_schema = {}

    def generate_signal(self, data, state):
        """Generate an ORB signal from supplied data and runtime state."""
        pass
