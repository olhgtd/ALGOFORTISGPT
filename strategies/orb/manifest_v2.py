"""AlgoFortis V2 Strategy SDK manifest for the ORB reference strategy.

The manifest deliberately contains no stop, target, trailing, R:R or sizing
economics.  Those remain an explicit versioned protective-policy dependency.
"""

from engine.strategy.contracts_v2 import (
    ParameterKind,
    ParameterSpec,
    StrategyManifestV2,
)


ORB_MANIFEST_V2 = StrategyManifestV2(
    strategy_id="orb",
    strategy_version="2.0.0",
    parameter_schema={
        # The Phase-4 reference signal is intentionally fixed to supplied bar
        # close vs supplied opening-range boundaries.  Keeping that field
        # explicit in the manifest makes the contract fingerprinted without
        # inventing any economic threshold.
        "signal_price_field": ParameterSpec(
            kind=ParameterKind.CHOICE,
            required=False,
            default="close",
            choices=("close",),
        ),
    },
    required_data_kinds=("bars",),
    required_timeframes=("5m",),
    supported_instruments=("index", "index_option"),
    dependency_lock={
        "data_contract": "phase3/v1",
        "strategy_sdk": "2.0",
    },
    protective_policy_required=True,
)


__all__ = ["ORB_MANIFEST_V2"]
