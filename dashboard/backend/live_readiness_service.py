"""Live read authority, shadow execution dry-run validation, and validation receipts.

Execution remains strictly READ_ONLY / SHADOW. There is no executable live order path.
Real broker mutation call count remains ZERO.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Literal
from uuid import UUID

from engine.data.feeds.live_feed import LiveQuoteEvent, deterministic_live_quote_event_id
from engine.data.feeds.quote_cache import LatestQuoteCache, QuoteCacheStatus
from engine.data.feeds.upstox.catalog_loader import UpstoxInstrumentCatalogLoader
from engine.execution.quote import QuoteSnapshot
from engine.orders.model import SignalIntent, OrderRequest, OrderType, TimeInForce
from engine.portfolio.model import PositionKey
from engine.reproducibility.codec import CanonicalCodec
from engine.risk.risk_manager import RiskGate, RiskOutcome, PositionDirection
from engine.safety.safety import SafetyManager, KillSwitchState
from .live_broker_read import UpstoxReadConnection, BrokerReadError, READ_CAPABILITIES, EXECUTION_CAPABILITIES

UTC = timezone.utc
CONNECTION_STATES = ("UNCONFIGURED", "CONFIGURED", "AUTHENTICATING", "CONNECTED", "DEGRADED", "DISCONNECTED", "ERROR", "REVOKED")


class LiveAuthorityUnavailable(RuntimeError):
    pass


class LiveExecutionDisabled(PermissionError):
    pass


def execution_boundary(mode: str = "LIVE") -> dict:
    # Deliberately no enable flag, setter, SDK capability override or stored
    # arming value. Enabling execution requires a separately reviewed code change.
    return {"execution_mode": mode, "arming_state": "READ_ONLY", "mutation_allowed": False,
            "reason": "EXECUTION_DISABLED" if mode == "LIVE" else "SHADOW_READ_ONLY"}


def require_live_mutation() -> None:
    raise LiveExecutionDisabled("EXECUTION_DISABLED")


def classify_reconciliation_order(order: dict) -> str:
    """Classify order source for reconciliation. Shadow records never drift broker orderbook."""
    mode = order.get("execution_mode", "")
    status = str(order.get("status", ""))
    if mode == "SHADOW" or status.startswith("SHADOW_"):
        return "ALGOFORTIS_SHADOW"
    if mode == "PAPER" or ("session_id" in order and not mode):
        return "PAPER"
    return "BROKER_REAL"


def build_would_be_broker_payload(
    *,
    user_id: str,
    canonical: SignalIntent,
    entry: Any,
    observed: dict | None,
    account: dict | None,
    quantity: Decimal,
    order_type: str = "MARKET",
    risk_result: Any = None,
    candidate_plan: Any = None,
    idempotency_key: str,
    now: datetime,
) -> dict[str, Any]:
    """Exact would-be broker request projection.

    Captures all 22+ canonical fields required for live execution if authorized,
    while guaranteeing that secrets, credentials, and bearer tokens are strictly excluded.
    """
    spec = getattr(entry, "specification", None)
    ident = getattr(entry, "identity", None)
    lot_size = int(spec.minimum_quantity) if spec and hasattr(spec, "minimum_quantity") else 1

    raw_segment = str(getattr(ident, "segment", "FO")).upper() if ident else "FO"
    segment = "FO" if raw_segment in ("OPTIONS", "FUTURES", "FO", "NSE_FO") else raw_segment

    return {
        "broker": account.get("broker", "UPSTOX") if account else "UPSTOX",
        "account_id": account.get("user_id") if account else None,
        "instrument_token": str(ident.instrument) if ident and hasattr(ident, "instrument") else str(canonical.symbol),
        "broker_instrument_token": str(canonical.symbol),
        "canonical_instrument": getattr(ident, "instrument", str(canonical.symbol)) if ident else str(canonical.symbol),
        "exchange": str(getattr(ident, "market", "NSE")).upper() if ident else "NSE",
        "segment": segment,
        "expiry": str(ident.expiry) if ident and getattr(ident, "expiry", None) else None,
        "strike": str(ident.strike) if ident and getattr(ident, "strike", None) else None,
        "option_type": getattr(ident, "option_type", None) if ident else None,
        "side": canonical.action,
        "quantity": int(quantity),
        "lot_size": lot_size,
        "order_type": order_type,
        "product_type": "D",
        "validity": "DAY",
        "limit_price": None if order_type == "MARKET" else (str(observed.get("ask")) if observed else None),
        "trigger_price": None,
        "disclosed_quantity": 0,
        "strategy_id": canonical.strategy_id,
        "execution_mode": "SHADOW",
        "client_order_intent_id": canonical.identity,
        "idempotency_key": idempotency_key,
        "request_timestamp": now.isoformat(),
        "market_data_timestamp": observed.get("exchange_timestamp") if observed else None,
        "risk_decision_id": getattr(risk_result, "decision_id", f"RISK-{canonical.identity[:12]}"),
    }


@dataclass(frozen=True)
class LiveRiskContext:
    """Trusted engine adapter inputs, never accepted from HTTP/client payloads.

    required_capital must come from existing reservation/margin authority;
    this projection does not introduce premium, margin, allocation or P&L math.
    """
    account_id: str
    as_of: datetime
    gate: RiskGate
    arguments: dict = field(repr=False)
    required_capital: Decimal | None = None


def compare_live_reads(actual: dict, expected: dict | None, now: datetime, max_age: timedelta) -> dict:
    """Read-only field comparison, not accounting or broker-state repair.

    The engine's existing comparators are explicitly paper/offline scoped.
    Missing independently maintained LIVE expectations cannot be IN_SYNC.
    """
    result = {"state": "UNKNOWN", "checked_at": now.isoformat(), "differences": []}
    if actual.get("connection_state") != "CONNECTED":
        return result | {"state": "UNAVAILABLE"}
    if not expected or expected.get("execution_mode") != "LIVE" or expected.get("authority") != "CANONICAL_LIVE_ACCOUNT":
        return result
    if expected.get("user_id") != actual.get("user_id") or not expected.get("reference_id"):
        return result
    try:
        age = now - datetime.fromisoformat(expected["as_of"])
        if age < timedelta(0) or age > max_age:
            return result
        for key in ("account", "funds", "positions", "orders", "connection_state"):
            if key not in expected or actual.get(key) is None:
                return result
            left, right = actual[key], expected[key]
            if isinstance(left, list) and isinstance(right, list):
                # Filter out shadow and paper orders so they never create broker drift
                left = [r for r in left if classify_reconciliation_order(r) == "BROKER_REAL"]
                right = [r for r in right if classify_reconciliation_order(r) == "BROKER_REAL"]
                left = sorted(json.dumps(row, sort_keys=True) for row in left)
                right = sorted(json.dumps(row, sort_keys=True) for row in right)
            if left != right:
                result["differences"].append(key)
        result["state"] = "DRIFT" if result["differences"] else "IN_SYNC"
        return result
    except (KeyError, ValueError, TypeError):
        return result


class LiveReadinessService:
    def __init__(self, *, store, audit, safe_mode, connections: dict[str, UpstoxReadConnection] | None = None,
                 catalog=None, mapper=None, catalog_date: date | None = None,
                 risk_provider: Callable | None = None, reference_provider: Callable | None = None,
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC),
                 freshness: timedelta = timedelta(seconds=10)):
        self.store, self.audit, self.safe_mode = store, audit, safe_mode
        self.connections = connections or {}
        self.catalog, self.mapper, self.catalog_date = catalog, mapper, catalog_date
        self.risk_provider, self.reference_provider = risk_provider, reference_provider
        self.clock, self.freshness = clock, freshness
        self._states: dict[str, dict] = {}
        self._quotes: dict[str, LatestQuoteCache] = {}
        self._lock = RLock()

    @classmethod
    def from_environment(cls, *, store, audit, safe_mode):
        # Infrastructure only: instrument catalog / mapper for read-only market
        # data resolution. This factory NEVER binds a process-global credential
        # to any user (NF-R203-04). Per-user operational authority is resolved
        # explicitly via resolve_operational_connection from the canonical
        # user_connections record.
        catalog = mapper = catalog_date = None
        master_path = os.environ.get("ALGOFORTIS_UPSTOX_INSTRUMENT_MASTER", "")
        business_date = os.environ.get("ALGOFORTIS_UPSTOX_CATALOG_DATE", "")
        if master_path and business_date:
            try:
                catalog_date = date.fromisoformat(business_date)
                records = json.loads(Path(master_path).read_text(encoding="utf-8"))
                catalog, mapper = UpstoxInstrumentCatalogLoader.load_catalog_and_mapper(records, snapshot_business_date=catalog_date)
            except Exception:
                catalog = mapper = catalog_date = None
        return cls(store=store, audit=audit, safe_mode=safe_mode, connections={},
                   catalog=catalog, mapper=mapper, catalog_date=catalog_date)

    def resolve_operational_connection(
        self,
        user_id: str,
        *,
        security_store=None,
        credential_provider: Callable[[str], str] | None = None,
    ) -> UpstoxReadConnection:
        """Resolve the authenticated user's canonical operational adapter.

        Production path: authenticated user -> canonical user_connections
        record (same-user, SQL-scoped) -> opaque credential_ref -> provider
        read-only adapter. The process-global UPSTOX_ACCESS_TOKEN is NEVER
        consulted here; a missing/unusable record or unresolvable reference
        fails closed with LiveAuthorityUnavailable.

        credential_provider(ref) resolves an opaque credential_ref to a bearer
        secret server-side. When no provider is wired (development without a
        vault), resolution fails closed. Tests inject adapters explicitly via
        the connections= constructor seam instead of calling this method.
        """
        store = security_store if security_store is not None else self.store
        resolve = getattr(store, "get_operational_connection", None)
        if resolve is None:
            raise LiveAuthorityUnavailable("CONNECTION_AUTHORITY_UNAVAILABLE")
        try:
            record = resolve(user_id)
        except Exception as exc:
            raise LiveAuthorityUnavailable(f"OPERATIONAL_CONNECTION_UNAVAILABLE: {exc}") from None
        if not record:
            raise LiveAuthorityUnavailable("OPERATIONAL_CONNECTION_UNAVAILABLE: no usable canonical connection")
        if str(record.get("provider", "UPSTOX")).upper() != "UPSTOX":
            raise LiveAuthorityUnavailable("OPERATIONAL_CONNECTION_UNAVAILABLE: unsupported provider")
        credential_ref = str(record.get("credentialRef") or "")
        account_ref = str(record.get("accountRef") or "")
        if not credential_ref or not account_ref:
            raise LiveAuthorityUnavailable("OPERATIONAL_CONNECTION_UNAVAILABLE: incomplete connection authority")
        if credential_provider is None:
            raise LiveAuthorityUnavailable("CREDENTIAL_AUTHORITY_UNAVAILABLE: no credential provider wired")

        def _scoped_provider(ref=credential_ref):
            token = credential_provider(ref)
            if not isinstance(token, str) or not token.strip():
                raise BrokerReadError("EXTERNAL_CONNECTION_REQUIRED")
            return token

        return UpstoxReadConnection(str(user_id), account_ref, _scoped_provider)

    def bind_operational_connection(
        self,
        user_id: str,
        *,
        security_store=None,
        credential_provider: Callable[[str], str] | None = None,
    ) -> bool:
        """Best-effort bind of the user's canonical adapter. Returns False and
        installs nothing when no canonical authority exists, so callers keep
        honest UNCONFIGURED truth instead of raising on plain readiness reads."""
        try:
            conn = self.resolve_operational_connection(
                user_id, security_store=security_store, credential_provider=credential_provider)
        except LiveAuthorityUnavailable:
            return False
        with self._lock:
            self.connections[str(user_id)] = conn
        return True

    def _audit(self, user_id: str, action: str, payload: dict, rejected=False) -> str:
        if self.audit is None:
            raise LiveAuthorityUnavailable("CORE_AUDIT_UNAVAILABLE")
        try:
            return self.audit.record(actor_id=UUID(user_id), action=action, payload=payload, rejected=rejected)
        except Exception:
            raise LiveAuthorityUnavailable("CORE_AUDIT_UNAVAILABLE") from None

    def _entries(self) -> dict:
        if self.catalog is None or self.mapper is None or self.catalog_date != self.clock().astimezone(timezone(timedelta(hours=5, minutes=30))).date():
            return {}
        try:
            result = {}
            for underlying in ("NIFTY", "BANKNIFTY"):
                for entry in self.catalog.list_entries(underlying=underlying, as_of=self.catalog_date):
                    if entry.identity.expiry is None or entry.identity.expiry < self.catalog_date:
                        continue
                    ref = self.mapper.to_provider_ref(entry.identity)
                    if ref.provider != "upstox" or ref.token in result:
                        return {}
                    result[ref.token] = entry
            return result
        except Exception:
            return {}

    def _policy(self, mode: str = "LIVE") -> dict:
        manager = SafetyManager(initial_kill_state=KillSwitchState(active=self.store.live_global_hold(), reason="LIVE_GLOBAL_HOLD", source="OWNER_GOVERNANCE"))
        return execution_boundary(mode) | {"global_hold": manager.is_kill_switch_active, "safe_mode": self.safe_mode.enabled}

    def _empty(self, user_id: str) -> dict:
        conn = self.connections.get(user_id)
        configured = conn is not None and conn.user_id == user_id and conn.configured()
        previous = next((r["data"] for r in self.store.live_observations(user_id) if r["key"] == "connection"), {})
        return {"user_id": user_id, "provider": "UPSTOX", "connection_state": "CONFIGURED" if configured else "UNCONFIGURED",
                "account": None, "funds": None, "positions": None, "holdings": None, "orders": None,
                "market_data": [], "market_data_state": "DISCONNECTED", "last_success": previous.get("last_success"),
                "last_failure": previous.get("last_failure"), "checked_at": None, "audit_id": None,
                "error": None if configured else "EXTERNAL_CONNECTION_REQUIRED",
                "reconciliation": {"state": "UNAVAILABLE", "checked_at": None, "differences": []}}

    def readiness(self, user_id: str) -> dict:
        with self._lock:
            result = json.loads(json.dumps(self._states.get(user_id) or self._empty(user_id)))
            conn = self.connections.get(user_id)
            if conn is None or not conn.configured():
                result = self._empty(user_id)
            now = self.clock()
            if result["checked_at"] and result["connection_state"] == "CONNECTED":
                if now - datetime.fromisoformat(result["checked_at"]) > self.freshness:
                    result["connection_state"] = "DEGRADED"
                    result["reconciliation"]["state"] = "UNKNOWN"
            for quote in result["market_data"]:
                age = now - datetime.fromisoformat(quote["exchange_timestamp"])
                received_age = now - datetime.fromisoformat(quote["received_timestamp"])
                if age < timedelta(0) or age > self.freshness or received_age < timedelta(0) or received_age > self.freshness:
                    quote["state"] = "STALE"
            if result["market_data"]:
                result["market_data_state"] = "FRESH" if all(q["state"] == "FRESH" for q in result["market_data"]) else "STALE"
            result["execution_policy"] = self._policy()
            result["capabilities"] = [{"name": c, "connector_support": conn is not None,
                "observed_available": result["connection_state"] == "CONNECTED" and (c != "MARKET_DATA_READ" or result["market_data_state"] == "FRESH"),
                "effective": "READ_ONLY" if conn is not None else "UNAVAILABLE"} for c in READ_CAPABILITIES]
            result["capabilities"] += [{"name": c, "connector_support": False, "observed_available": False, "effective": "EXECUTION_DISABLED"} for c in EXECUTION_CAPABILITIES]
            for capability in result["capabilities"]:
                if capability["name"] in READ_CAPABILITIES and not capability["observed_available"]:
                    capability["effective"] = "UNAVAILABLE"
            result["instruments"] = [{"token": token, "symbol": e.identity.instrument, "underlying": e.identity.underlying,
                "expiry": str(e.identity.expiry), "strike": str(e.identity.strike), "option_type": e.identity.option_type,
                "exchange": e.identity.market, "segment": e.identity.segment, "lot_size": str(e.specification.minimum_quantity)}
                for token, e in self._entries().items()]
            result["strategies"] = [{"id": s["strategyId"], "name": s["name"], "version": s["version"],
                "admin_status": s["adminStatus"], "live": s["governance"]["live"]} for s in self.store.list_owner_strategies()]
            result["intents"] = [r["data"] for r in self.store.live_observations(user_id) if r["key"].startswith("intent:")]
            result["shadow_orders"] = [r["data"] for r in self.store.live_observations(user_id) if r["key"].startswith("shadow:")]
            result["account_equity"] = None
            result["aggregate_exposure"] = None
            result["risk_state"] = "REQUIRES_CANONICAL_LIVE_CONTEXT" if self.risk_provider is None else "VALIDATE_INTENT"
            return result

    def shadow_orders(self, user_id: str | None = None, *, limit: int | None = None) -> list[dict]:
        with self._lock:
            observations = self.store.live_observations(user_id)
            orders = [r["data"] for r in observations if r["key"].startswith("shadow:") or (r["key"].startswith("intent:") and r["data"].get("execution_mode") == "SHADOW")]
            if limit is not None:
                try:
                    return list(orders[: max(0, int(limit))])
                except (TypeError, ValueError):
                    pass
            return orders

    def refresh(self, user_id: str) -> dict:
        with self._lock:
            # Audit the attempt before calling the external read transport.
            self._states.pop(user_id, None)
            self._audit(user_id, "LIVE_BROKER_READ_REQUESTED", {})
            state = self._empty(user_id)
            conn = self.connections.get(user_id)
            if state["connection_state"] == "CONFIGURED":
                state["connection_state"] = "AUTHENTICATING"
                try:
                    conn = conn.read_cycle()
                    state["account"] = conn.read("profile")
                    if state["account"].get("is_active") is not True:
                        raise BrokerReadError("BROKER_ACCOUNT_INACTIVE")
                    for resource in ("funds", "positions", "holdings", "orders"):
                        state[resource] = conn.read(resource)
                    state["connection_state"] = "CONNECTED"
                    entries = self._entries()
                    if entries:
                        quote_rows = conn.read("quotes", instrument_tokens=tuple(entries)[:500])
                        cache = self._quotes.setdefault(user_id, LatestQuoteCache())
                        for raw in quote_rows:
                            entry = entries[raw["instrument_token"]]
                            ts = datetime.fromtimestamp(float(Decimal(str(raw["last_trade_time"])) / 1000), UTC)
                            quote = QuoteSnapshot(instrument_identity=entry.identity, exchange_timestamp=ts,
                                bid_price=raw["bid"], ask_price=raw["ask"], last_price=raw["last_price"], source="UPSTOX_REST")
                            event = LiveQuoteEvent(event_id=deterministic_live_quote_event_id(quote), quote=quote)
                            cached = cache.on_quote_event(event)
                            valid = cached.status in (QuoteCacheStatus.ACCEPTED, QuoteCacheStatus.DUPLICATE_IGNORED)
                            state["market_data"].append({"token": raw["instrument_token"], "symbol": entry.identity.instrument,
                                "source": quote.source, "exchange_timestamp": ts.isoformat(), "received_timestamp": self.clock().isoformat(),
                                "ltp": str(quote.last_price), "bid": str(quote.bid_price) if quote.bid_price is not None else None,
                                "ask": str(quote.ask_price) if quote.ask_price is not None else None,
                                "state": "FRESH" if valid else "REJECTED", "ordering": cached.status.value})
                    if conn.read("profile") != state["account"]:
                        raise BrokerReadError("BROKER_ACCOUNT_MISMATCH")
                    state["last_success"] = self.clock().isoformat()
                except BrokerReadError as exc:
                    state = self._empty(user_id) | {"connection_state": "REVOKED" if exc.code == "BROKER_AUTH_FAILED" else "ERROR",
                        "error": exc.code, "last_failure": self.clock().isoformat()}
                except Exception:
                    state = self._empty(user_id) | {"connection_state": "ERROR", "error": "BROKER_RESPONSE_INVALID", "last_failure": self.clock().isoformat()}
            state["checked_at"] = self.clock().isoformat()
            expected = None
            if self.reference_provider is not None:
                try:
                    expected = self.reference_provider(user_id)
                except Exception:
                    pass
            state["reconciliation"] = compare_live_reads(state, expected, self.clock(), self.freshness)
            state["audit_id"] = self._audit(user_id, "LIVE_BROKER_READ_RESULT", {
                "connection_state": state["connection_state"], "reconciliation": state["reconciliation"]["state"], "error": state["error"]},
                rejected=state["connection_state"] != "CONNECTED")
            self.store.save_live_observation(user_id, "connection", state)
            self._states[user_id] = state
            return self.readiness(user_id)

    def validate(self, user_id: str, request: dict) -> dict:
        with self._lock:
            mode = request.get("execution_mode", "LIVE")
            strategy = self.store.get_owner_strategy(request["strategy_id"])
            orig_ts = request["originating_timestamp"]
            if isinstance(orig_ts, str):
                orig_ts = datetime.fromisoformat(orig_ts)
            canonical = SignalIntent(action=request["side"], confidence=1.0, symbol=request["instrument_token"],
                timeframe=request["timeframe"], originating_timestamp=orig_ts,
                strategy_id=request["strategy_id"], strategy_version=strategy["version"] if strategy else "UNAVAILABLE", metadata={})
            intent_id = CanonicalCodec.fingerprint("algofortis-live-validation-intent/v1" if mode == "LIVE" else "algofortis-shadow-validation-intent/v1", (
                ("user", user_id), ("mode", mode), ("signal", canonical.identity), ("quantity", request["quantity"])))
            idempotency_key = request.get("idempotency_key") or intent_id
            state = self.readiness(user_id)
            reasons = []
            def block(code, detail=None):
                reasons.append({"code": code, "detail": detail or code})

            # Idempotency conflict check
            existing_for_key = next((r["data"] for r in self.store.live_observations(user_id)
                                    if r["data"].get("idempotency_key") == idempotency_key), None)
            if existing_for_key is not None:
                prev = existing_for_key
                if (prev.get("strategy_id") != canonical.strategy_id or
                    prev.get("instrument_token") != request["instrument_token"] or
                    prev.get("side") != canonical.action or
                    Decimal(str(prev.get("quantity", "0"))) != Decimal(str(request["quantity"]))):
                    block("IDEMPOTENCY_CONFLICT", f"Payload mismatch for idempotency key {idempotency_key}")

            if self.safe_mode.enabled: block("SAFE_MODE")
            if self.store.live_global_hold(): block("OWNER_HOLD")
            if strategy is None or strategy["adminStatus"] != "ACTIVE": block("STRATEGY_SUSPENDED")
            elif strategy["governance"]["live"]["ownerAllowance"] != "ALLOWED": block("OWNER_HOLD", "Strategy live allowance")
            elif strategy["governance"]["live"]["effectiveEligibility"] != "ELIGIBLE": block("STRATEGY_NOT_LIVE_ELIGIBLE")
            if state["connection_state"] != "CONNECTED": block("BROKER_DISCONNECTED")
            if not state["account"] or state["account"].get("is_active") is not True: block("ACCOUNT_INELIGIBLE")
            entry = self._entries().get(request["instrument_token"])
            if entry is None: block("INSTRUMENT_UNRESOLVED")
            else:
                qty = Decimal(str(request["quantity"]))
                if qty < entry.specification.minimum_quantity or qty % entry.specification.quantity_step:
                    block("INVALID_LOT_QUANTITY")
                # Option resolution check: verify canonical attributes
                ident = entry.identity
                if getattr(ident, "underlying", None) not in ("NIFTY", "BANKNIFTY") or getattr(ident, "expiry", None) is None or getattr(ident, "strike", None) is None or getattr(ident, "option_type", None) not in ("CE", "PE"):
                    block("INSTRUMENT_UNRESOLVED", "Invalid contract specifications")
            observed = next((q for q in state["market_data"] if q["token"] == request["instrument_token"]), None)
            if observed is None: block("MARKET_DATA_DISCONNECTED")
            elif observed["state"] != "FRESH": block("MARKET_DATA_STALE")
            elif observed["bid"] is None or observed["ask"] is None or Decimal(observed["bid"]) <= 0 or Decimal(observed["ask"]) < Decimal(observed["bid"]):
                block("MARKET_DATA_INVALID")
            if state["reconciliation"]["state"] != "IN_SYNC": block("RECONCILIATION_REQUIRED", state["reconciliation"]["state"])
            risk_result = None
            order = None
            context = None
            if self.risk_provider is not None and entry is not None and observed is not None:
                try:
                    context = self.risk_provider(user_id, canonical, entry, observed)
                    if not isinstance(context, LiveRiskContext) or not isinstance(context.gate, RiskGate) or state["account"] is None or context.account_id != state["account"]["user_id"]:
                        raise ValueError("account context mismatch")
                    if not timedelta(0) <= self.clock() - context.as_of <= self.freshness:
                        raise ValueError("stale context")
                    expected_key = PositionKey(canonical.strategy_id, canonical.strategy_version, entry.identity)
                    if context.arguments.get("intended_position_key") != expected_key or context.arguments.get("specification") != entry.specification:
                        raise ValueError("unbound risk context")
                    plan = context.arguments.get("candidate_plan")
                    snapshot = context.arguments.get("snapshot")
                    if snapshot is None or snapshot.account_id != context.account_id or snapshot.as_of_timestamp is None or not timedelta(0) <= self.clock() - snapshot.as_of_timestamp <= self.freshness:
                        raise ValueError("unbound account snapshot")
                    if request["side"] != "BUY" or context.arguments.get("direction") is not PositionDirection.LONG:
                        raise ValueError("unsupported direction")
                    if observed["state"] != "FRESH" or observed["ask"] is None or context.arguments.get("entry_price") != Decimal(observed["ask"]):
                        raise ValueError("unbound quote")
                    if plan is None or plan.intended_position_key != expected_key or plan.originating_timestamp != canonical.originating_timestamp or plan.timeframe != canonical.timeframe:
                        raise ValueError("unbound protective plan")
                    if context.required_capital is not None and (not context.required_capital.is_finite() or context.required_capital < 0):
                        raise ValueError("invalid required capital")
                    gate_args = {k: v for k, v in context.arguments.items() if k != "exposure_limit_exceeded"}
                    risk_result = context.gate.evaluate_pre_order(**gate_args)
                    if risk_result.outcome is not RiskOutcome.APPROVED:
                        block("RISK_REJECTED", risk_result.reason)
                    elif Decimal(str(request["quantity"])) != risk_result.quantity:
                        block("RISK_QUANTITY_MISMATCH")
                    else:
                        order = OrderRequest.from_intent(canonical, OrderType.MARKET, risk_result.quantity, TimeInForce.DAY)
                    funds = state["funds"] or {}
                    if context.required_capital is None or funds.get("available_margin") is None:
                        block("FUNDS_REQUIREMENT_UNAVAILABLE")
                    elif context.required_capital > Decimal(str(funds["available_margin"])):
                        block("INSUFFICIENT_FUNDS")
                    if context.arguments.get("exposure_limit_exceeded"):
                        block("EXPOSURE_LIMIT", "Portfolio exposure limit exceeded")
                except Exception as ex:
                    block("RISK_AUTHORITY_UNAVAILABLE", str(ex))
            else:
                block("RISK_AUTHORITY_UNAVAILABLE")
            if request["side"] != "BUY": block("CLOSE_INTENT_AUTHORITY_UNAVAILABLE")

            conn = self.connections.get(user_id)
            if mode == "SHADOW":
                conn_order_capability = getattr(conn, "supports_order_placement", True) if conn else False
                if not conn_order_capability:
                    block("BROKER_CAPABILITY_MISSING", "Broker capability contract does not support order placement")

                if not reasons:
                    status = "SHADOW_READY"
                    would_be = build_would_be_broker_payload(
                        user_id=user_id,
                        canonical=canonical,
                        entry=entry,
                        observed=observed,
                        account=state.get("account"),
                        quantity=Decimal(str(request["quantity"])),
                        order_type="MARKET",
                        risk_result=risk_result,
                        candidate_plan=context.arguments.get("candidate_plan") if context else None,
                        idempotency_key=idempotency_key,
                        now=self.clock(),
                    )
                else:
                    status = "SHADOW_REJECTED" if any(r["code"] in ("RISK_REJECTED", "STRATEGY_NOT_LIVE_ELIGIBLE") for r in reasons) else "SHADOW_BLOCKED"
                    would_be = None

                result = {
                    "intent_id": intent_id,
                    "idempotency_key": idempotency_key,
                    "canonical_signal_id": canonical.identity,
                    "user_id": user_id,
                    "execution_mode": "SHADOW",
                    "strategy_id": canonical.strategy_id,
                    "instrument_token": request["instrument_token"],
                    "canonical_instrument": entry.identity.instrument if entry else None,
                    "side": canonical.action,
                    "quantity": str(request["quantity"]),
                    "status": status,
                    "checked_at": self.clock().isoformat(),
                    "arming_state": "READ_ONLY",
                    "reasons": reasons,
                    "risk_status": risk_result.outcome.value if risk_result else "UNAVAILABLE",
                    "broker_mutation_sent": False,
                    "would_be_payload": would_be,
                    "canonical_order": {"order_type": order.order_type.value, "quantity": str(order.quantity), "time_in_force": order.time_in_force.value} if order else None,
                }
                result["audit_id"] = self._audit(user_id, "SHADOW_INTENT_VALIDATED", {
                    "intent_id": intent_id, "idempotency_key": idempotency_key, "status": status,
                    "reasons": [r["code"] for r in reasons], "broker_mutation_sent": False},
                    rejected=status != "SHADOW_READY")
                self.store.save_live_observation(user_id, "intent:" + intent_id, result)
                self.store.save_live_observation(user_id, "shadow:" + intent_id, result)
                return result
            else:
                block("BROKER_CAPABILITY_MISSING", "Live mutation connector is intentionally absent")
                block("EXECUTION_DISABLED")
                result = {"intent_id": intent_id, "canonical_signal_id": canonical.identity, "user_id": user_id,
                    "execution_mode": "LIVE", "strategy_id": canonical.strategy_id, "instrument_token": request["instrument_token"],
                    "side": canonical.action, "quantity": str(request["quantity"]), "status": "BLOCKED",
                    "checked_at": self.clock().isoformat(), "arming_state": "READ_ONLY", "reasons": reasons,
                    "risk_status": risk_result.outcome.value if risk_result else "UNAVAILABLE", "broker_mutation_sent": False,
                    "canonical_order": {"order_type": order.order_type.value, "quantity": str(order.quantity), "time_in_force": order.time_in_force.value} if order else None}
                result["audit_id"] = self._audit(user_id, "LIVE_INTENT_VALIDATED", {
                    "intent_id": intent_id, "status": "BLOCKED", "reasons": [r["code"] for r in reasons]}, rejected=True)
                self.store.save_live_observation(user_id, "intent:" + intent_id, result)
                return result

    def set_hold(self, actor_id: str, enabled: bool) -> dict:
        with self._lock:
            self._audit(actor_id, "LIVE_GLOBAL_HOLD_REQUESTED", {"enabled": enabled})
            self.store.set_live_global_hold(enabled)
            try:
                self._audit(actor_id, "LIVE_GLOBAL_HOLD_APPLIED", {"enabled": enabled})
            except LiveAuthorityUnavailable:
                self.store.set_live_global_hold(True)
                raise
            return self._policy()

    def deny_mutation(self, actor_id: str):
        # An unavailable audit must still leave the final backend gate closed.
        self._audit(actor_id, "LIVE_EXECUTION_DISABLED", execution_boundary(), rejected=True)
        require_live_mutation()

    def oversight(self) -> dict:
        user_ids = set(self.connections) | {row["user_id"] for row in self.store.live_observations()}
        return {"execution_policy": self._policy(), "users": [self.readiness(uid) for uid in sorted(user_ids)]}
