def get_data(
    strategy_config: "StrategyConfig", feed: "DataFeed"
) -> "Dict[str, DataFrame]":
    """Single strategy-facing data-access wrapper for all required timeframes."""
    return {
        timeframe: feed.fetch(strategy_config.instrument, timeframe)
        for timeframe in strategy_config.required_timeframes
    }
