"""Multi-broker strategy deployment executor and signal router.

Complies with Phase 9 requirements:
- Allows a single strategy S1 to be deployed simultaneously across multiple connections/brokers.
- Each deployment maintains:
  - Distinct deployment_id
  - Dedicated broker adapter instance
  - Independent orderbook and position tracking
  - Deployment-aware signal deduplication (signal produces at most 1 order per deployment)
  - Isolated failure boundaries: failure on Broker A never blocks Broker B.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from engine.broker_adapters.contracts import (
    BrokerAdapter,
    BrokerSubmissionResult,
    broker_order_identity,
)
from engine.orders import (
    ConcreteCloseInstruction,
    ConcreteOpenInstruction,
    OrderRequest,
    OrderType,
    TimeInForce,
)
from engine.orchestration.signal_intake import SignalIntent, signal_intent_identity
from engine.portfolio.model import InstrumentIdentity, InstrumentSpecification

logger = logging.getLogger(__name__)


@dataclass
class DeploymentContext:
    """Isolated runtime execution context for one strategy deployment."""

    deployment_id: str
    strategy_id: str
    strategy_version: str
    connection_id: str
    provider: str
    broker_adapter: BrokerAdapter
    execution_mode: str = "LIVE"
    max_position_size: Decimal = Decimal("500")
    processed_signal_keys: set[str] = field(default_factory=set)
    orders: dict[str, Any] = field(default_factory=dict)
    positions: dict[str, Decimal] = field(default_factory=dict)
    active: bool = True


class MultiBrokerDeploymentExecutor:
    """Orchestrates multi-broker strategy deployments and signal routing."""

    def __init__(self) -> None:
        self._deployments: dict[str, DeploymentContext] = {}

    def register_deployment(
        self,
        *,
        deployment_id: str,
        strategy_id: str,
        strategy_version: str,
        connection_id: str,
        provider: str,
        broker_adapter: BrokerAdapter,
        execution_mode: str = "LIVE",
        max_position_size: Decimal = Decimal("500"),
    ) -> DeploymentContext:
        """Register an active deployment with dedicated broker adapter."""
        ctx = DeploymentContext(
            deployment_id=deployment_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            connection_id=connection_id,
            provider=provider.upper(),
            broker_adapter=broker_adapter,
            execution_mode=execution_mode.upper(),
            max_position_size=max_position_size,
        )
        self._deployments[deployment_id] = ctx
        logger.info(
            "Registered deployment '%s' for strategy '%s' on %s (conn: %s)",
            deployment_id, strategy_id, provider, connection_id
        )
        return ctx

    def unregister_deployment(self, deployment_id: str) -> bool:
        """Remove a deployment from execution routing."""
        if deployment_id in self._deployments:
            self._deployments[deployment_id].active = False
            del self._deployments[deployment_id]
            return True
        return False

    def get_deployment(self, deployment_id: str) -> DeploymentContext | None:
        return self._deployments.get(deployment_id)

    def list_deployments_for_strategy(self, strategy_id: str) -> list[DeploymentContext]:
        """Find all active deployments for a specific strategy."""
        return [
            dep for dep in self._deployments.values()
            if dep.strategy_id == strategy_id and dep.active
        ]

    def route_signal(
        self,
        signal: SignalIntent,
        *,
        instrument_identity: InstrumentIdentity,
        specification: InstrumentSpecification,
        quantity: Decimal = Decimal("50"),
        price: Decimal | None = None,
    ) -> dict[str, BrokerSubmissionResult]:
        """Route a strategy signal to all active deployments for that strategy.

        Guarantees:
        1. Deployment-aware deduplication: each deployment executes at most once per signal.
        2. Isolation: a failure, rejection, or rate limit on deployment A never blocks deployment B.
        3. Returns a dictionary mapping deployment_id -> BrokerSubmissionResult.
        """
        target_deployments = self.list_deployments_for_strategy(signal.strategy_id)
        results: dict[str, BrokerSubmissionResult] = {}

        signal_key = signal_intent_identity(signal)

        for ctx in target_deployments:
            dep_id = ctx.deployment_id
            # 1. Deployment-aware deduplication
            if signal_key in ctx.processed_signal_keys:
                results[dep_id] = BrokerSubmissionResult(
                    accepted=False,
                    order_id=None,
                    broker_order_identity=None,
                    duplicate=True,
                    reason=f"duplicate_signal_on_deployment_{dep_id}",
                )
                continue

            ctx.processed_signal_keys.add(signal_key)

            # 2. Risk check per deployment account limit
            current_qty = ctx.positions.get(instrument_identity.instrument, Decimal("0"))
            if current_qty + quantity > ctx.max_position_size:
                results[dep_id] = BrokerSubmissionResult(
                    accepted=False,
                    order_id=None,
                    broker_order_identity=None,
                    reason=f"deployment_risk_limit_exceeded: max {ctx.max_position_size}",
                )
                continue

            # 3. Create executable order instruction
            order_req = OrderRequest(
                source_intent=signal,
                order_type=OrderType.LIMIT if price else OrderType.MARKET,
                quantity=quantity,
                time_in_force=TimeInForce.DAY,
                limit_price=price,
            )
            executable = ConcreteOpenInstruction(
                source_entry_order=order_req,
                opening_action=getattr(signal, "action", "BUY"),
                execution_symbol=instrument_identity.instrument,
            )

            # 4. Submit to this deployment's dedicated broker adapter
            try:
                sub_res = ctx.broker_adapter.submit(
                    executable,
                    instrument_identity=instrument_identity,
                    specification=specification,
                    submission_market_timestamp=signal.originating_timestamp,
                )
                results[dep_id] = sub_res
                if sub_res.accepted and sub_res.order_id:
                    ctx.orders[sub_res.order_id] = {
                        "order": executable,
                        "submission_result": sub_res,
                        "timestamp": signal.originating_timestamp,
                    }
                    ctx.positions[instrument_identity.instrument] = current_qty + quantity
            except Exception as exc:
                # Isolated failure boundary: capture failure for this deployment without crashing other deployments
                logger.error("Deployment '%s' broker submission error: %s", dep_id, exc)
                results[dep_id] = BrokerSubmissionResult(
                    accepted=False,
                    order_id=None,
                    broker_order_identity=None,
                    reason=f"broker_adapter_exception: {exc}",
                )

        return results
