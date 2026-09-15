"""Read-only adapters from existing SentinelX data contracts to dashboard DTOs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Protocol
import pandas as pd

from .domain import TrustState, TrustedValue


@dataclass(frozen=True)
class ChartRequest:
    instrument: str
    timeframe: str
    mode: str
    start_date: str | None = None
    end_date: str | None = None
    limit: int = 1000


class MarketChartAuthority(Protocol):
    """Composition adapter over existing HistoricalDataFeed/live-feed authorities."""
    def chart(self, request: ChartRequest) -> dict[str, object]: ...
    def available_timeframes(self, instrument: str, mode: str) -> tuple[str, ...]: ...


class UnavailableMarketChartAuthority:
    """Fail closed until composition wires a verified existing authority."""
    def chart(self, request: ChartRequest) -> dict[str, object]:
        unknown = TrustedValue(value=None, trust=TrustState.UNKNOWN, as_of_utc=None)
        res = {
            "mode": request.mode,
            "instrument": request.instrument,
            "timeframe": request.timeframe,
            "candles": unknown.public_dict(),
            "markers": unknown.public_dict(),
            "overlays": unknown.public_dict(),
        }
        res["candles"]["state"] = "DATA_PROVIDER_NOT_CONFIGURED"
        return res

    def available_timeframes(self, instrument: str, mode: str) -> tuple[str, ...]:
        return ()


class HistoricalFeedChartAuthority:
    """Read-only projection of the existing HistoricalDataFeed / HistoricalDataService contract.

    It intentionally derives no signals, trades, volume, or protective levels.
    """
    def __init__(
        self,
        feed: object,
        *,
        source_identity: str,
        marker_reader: Callable[[ChartRequest], TrustedValue] | None = None,
        overlay_reader: Callable[[ChartRequest], TrustedValue] | None = None,
    ) -> None:
        self._feed = feed
        self._source_identity = source_identity
        self._marker_reader, self._overlay_reader = marker_reader, overlay_reader

    def chart(self, request: ChartRequest) -> dict[str, object]:
        if request.mode == "LIVE":
            return UnavailableMarketChartAuthority().chart(request)

        try:
            if hasattr(self._feed, "request_data") and request.start_date and request.end_date:
                s_d = date.fromisoformat(request.start_date)
                e_d = date.fromisoformat(request.end_date)
                frame, _ = self._feed.request_data(
                    instrument=request.instrument,
                    timeframe=request.timeframe,
                    start_date=s_d,
                    end_date=e_d,
                    auto_provision=False,
                )
            else:
                frame = self._feed.fetch(request.instrument, request.timeframe)
        except Exception as exc:
            provider = getattr(self._feed, "provider", None)
            is_unconfigured = (
                "DATA_PROVIDER_NOT_CONFIGURED" in str(exc)
                or (provider is not None and not getattr(provider, "is_configured", True))
            )
            err_state = "DATA_PROVIDER_NOT_CONFIGURED" if is_unconfigured else "NO_DATA"
            unknown = TrustedValue(None, TrustState.UNKNOWN, None).public_dict()
            unknown["state"] = err_state
            unknown["error"] = str(exc)
            return {
                "mode": request.mode,
                "instrument": request.instrument,
                "timeframe": request.timeframe,
                "candles": unknown,
                "markers": unknown,
                "overlays": unknown,
            }

        required = {"open", "high", "low", "close"}
        if frame is None or frame.empty or not required.issubset(frame.columns):
            res = UnavailableMarketChartAuthority().chart(request)
            res["candles"]["state"] = "NO_DATA"
            return res

        # Robust timestamp extraction supporting both column and DatetimeIndex.
        # Series form is required downstream (.iloc/.tail/.dt access).
        if "timestamp" in frame.columns:
            ts_series = pd.to_datetime(frame["timestamp"], utc=True)
            if not isinstance(ts_series, pd.Series):
                ts_series = pd.Series(ts_series, index=frame.index)
        elif isinstance(frame.index, pd.DatetimeIndex):
            if frame.index.tz is None:
                # Timezone-naive evidence cannot anchor trust: fail closed.
                res = UnavailableMarketChartAuthority().chart(request)
                res["candles"]["state"] = "DATA_INVALID"
                return res
            ts_series = pd.Series(pd.to_datetime(frame.index, utc=True), index=frame.index)
        else:
            try:
                parsed = pd.to_datetime(frame.index, utc=True)
            except Exception:
                res = UnavailableMarketChartAuthority().chart(request)
                res["candles"]["state"] = "DATA_INVALID"
                return res
            ts_series = (parsed if isinstance(parsed, pd.Series)
                         else pd.Series(parsed, index=frame.index))

        # Apply date filters if not already sliced
        if request.start_date or request.end_date:
            dates = ts_series.dt.date
            mask = pd.Series(True, index=frame.index)
            if request.start_date:
                mask &= (dates >= date.fromisoformat(request.start_date))
            if request.end_date:
                mask &= (dates <= date.fromisoformat(request.end_date))
            frame = frame.loc[mask]
            ts_series = ts_series.loc[mask]

        if frame.empty:
            no_data = TrustedValue(None, TrustState.UNKNOWN, None).public_dict()
            no_data["state"] = "NO_DATA"
            return {
                "mode": request.mode,
                "instrument": request.instrument,
                "timeframe": request.timeframe,
                "candles": no_data,
                "markers": no_data,
                "overlays": no_data,
            }

        # Bounded windowing if rows exceed limit
        limit = getattr(request, "limit", 1000) or 1000
        if len(frame) > limit:
            frame = frame.tail(limit)
            ts_series = ts_series.tail(limit)

        as_of = ts_series.iloc[-1].to_pydatetime()
        candles = []
        for (_, row), ts_val in zip(frame.iterrows(), ts_series):
            ts_dt = ts_val.to_pydatetime()
            candle = {
                "time": ts_dt.isoformat(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }
            if "volume" in frame.columns and pd.notna(row["volume"]):
                candle["volume"] = float(row["volume"])
            candles.append(candle)

        trusted = TrustedValue(candles, TrustState.FRESH, as_of, self._source_identity).public_dict()
        trusted["state"] = "AVAILABLE"
        unknown = TrustedValue(None, TrustState.UNKNOWN, None)

        def evidence(reader: Callable[[ChartRequest], TrustedValue] | None) -> dict[str, object | None]:
            if reader is None:
                return unknown.public_dict()
            try:
                val = reader(request)
            except Exception:
                return unknown.public_dict()
            return val.public_dict() if isinstance(val, TrustedValue) else unknown.public_dict()

        return {
            "mode": request.mode,
            "instrument": request.instrument,
            "timeframe": request.timeframe,
            "candles": trusted,
            "markers": evidence(self._marker_reader),
            "overlays": evidence(self._overlay_reader),
        }

    def available_timeframes(self, instrument: str, mode: str) -> tuple[str, ...]:
        if mode == "LIVE":
            return ()
        available = getattr(self._feed, "available_timeframes", None)
        try:
            values = tuple(available(instrument)) if callable(available) else ()
        except Exception:
            return ()
        return values if all(isinstance(value, str) and value.strip() for value in values) else ()


class LiveQuoteReadAuthority:
    """Passive projection of the existing LiveMarketDataFeed listener contract.

    The dashboard neither subscribes nor reconnects the feed; runtime
    composition forwards already-authoritative events here.
    """
    def __init__(self, *, stale_after: timedelta) -> None:
        if stale_after <= timedelta(0):
            raise ValueError("stale_after must be positive")
        self._stale_after = stale_after
        self._latest: object | None = None

    def accept_event(self, event: object) -> None:
        quote = getattr(event, "quote", None)
        timestamp = getattr(quote, "exchange_timestamp", None)
        if quote is None or not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
            self._latest = None
            return
        self._latest = event

    def latest(self, *, now_utc: datetime) -> TrustedValue:
        if now_utc.tzinfo is None:
            raise ValueError("now_utc must be timezone-aware")
        event = self._latest
        quote = getattr(event, "quote", None)
        timestamp = getattr(quote, "exchange_timestamp", None)
        if event is None or quote is None or not isinstance(timestamp, datetime) or timestamp.tzinfo is None:
            return TrustedValue(None, TrustState.UNKNOWN, None)
        trust = TrustState.FRESH if now_utc - timestamp <= self._stale_after else TrustState.STALE
        value = {"last_price": str(getattr(quote, "last_price", "")), "instrument": str(getattr(quote, "instrument_identity", ""))}
        return TrustedValue(value, trust, timestamp, getattr(quote, "source", None), getattr(event, "event_id", None))


class CoreReadAuthority:
    """Read-only API-facing facade over injected core authorities.

    It cannot calculate risk, run backtests, mutate persistence, or emit audit
    events. Each supplied reader must return existing authoritative evidence.
    """
    def __init__(self, readers: dict[str, Protocol] | None = None) -> None:
        self._readers = readers or {}

    def read(self, name: str, *args: object, **kwargs: object) -> TrustedValue:
        reader = self._readers.get(name)
        if reader is None or not callable(reader):
            return TrustedValue(None, TrustState.UNKNOWN, None)
        try:
            value = reader(*args, **kwargs)
        except Exception:
            return TrustedValue(None, TrustState.UNKNOWN, None)
        if not isinstance(value, TrustedValue):
            return TrustedValue(None, TrustState.UNKNOWN, None)
        return value


import json
import sqlite3
from pathlib import Path
from typing import Any

from engine.audit.model import AuditEvent, derive_audit_severity, derive_audit_status
from engine.audit.sinks import FORBIDDEN_RECORD_KEYS, _SECRET_VALUE_PATTERNS, _REDACTED_PLACEHOLDER


def _redact_value(val: Any) -> Any:
    if isinstance(val, str):
        for pat in _SECRET_VALUE_PATTERNS:
            if pat.search(val):
                return _REDACTED_PLACEHOLDER
        return val
    if isinstance(val, dict):
        return {
            k: (_REDACTED_PLACEHOLDER if k.lower() in FORBIDDEN_RECORD_KEYS else _redact_value(v))
            for k, v in val.items()
        }
    if isinstance(val, list):
        return [_redact_value(v) for v in val]
    return val


class D16AuditReadAdapter:
    """Read-only projection of the D16 audit events table.

    Applies redaction to payload_json and projects AuditEvent instances
    into serialized dictionary records conforming to the frontend OwnerAuditRow contract.
    """
    def __init__(self, persistence_store: object | None = None, *, db_path: Path | str | None = None) -> None:
        self._persistence_store = persistence_store
        self._db_path = Path(db_path) if db_path else None

    def read_audit_events(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        event_family: str | None = None,
        severity: str | None = None,
        as_of_utc: datetime | None = None,
    ) -> dict[str, Any]:
        now = as_of_utc or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        events: list[dict[str, Any]] = []
        total_count = 0

        # 1. Try via persistence store query_audit_events
        if self._persistence_store is not None and hasattr(self._persistence_store, "query_audit_events"):
            try:
                raw_events = self._persistence_store.query_audit_events(
                    event_family=event_family,
                    limit=limit,
                    offset=offset,
                )
                total_count = len(raw_events)
                for ev in raw_events:
                    mapped = self._map_event(ev)
                    if severity is None or mapped.get("severity") == severity:
                        events.append(mapped)
                return {
                    "source": "BACKEND",
                    "trust": "FRESH",
                    "as_of_utc": now.isoformat(),
                    "total_count": total_count,
                    "events": events,
                }
            except Exception:
                pass

        # 2. Try direct read from SQLite db_path if store not injected
        if self._db_path is not None and self._db_path.exists():
            try:
                conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_events';")
                if not cursor.fetchone():
                    conn.close()
                    return {
                        "source": "BACKEND",
                        "trust": "UNKNOWN",
                        "as_of_utc": now.isoformat(),
                        "total_count": 0,
                        "events": [],
                    }

                query = "SELECT * FROM audit_events"
                clauses = []
                params = []
                if event_family:
                    clauses.append("event_family = ?")
                    params.append(event_family)
                if clauses:
                    query += " WHERE " + " AND ".join(clauses)
                query += " ORDER BY audit_sequence DESC, recorded_at_utc DESC"
                if limit:
                    query += f" LIMIT {int(limit)}"
                if offset:
                    query += f" OFFSET {int(offset)}"

                cursor.execute(query, params)
                rows = cursor.fetchall()
                for row in rows:
                    ev_dict = dict(row)
                    mapped = self._map_row(ev_dict)
                    if severity is None or mapped.get("severity") == severity:
                        events.append(mapped)
                conn.close()
                return {
                    "source": "BACKEND",
                    "trust": "FRESH",
                    "as_of_utc": now.isoformat(),
                    "total_count": len(events),
                    "events": events,
                }
            except Exception:
                pass

        return {
            "source": "BACKEND",
            "trust": "UNKNOWN",
            "as_of_utc": now.isoformat(),
            "total_count": 0,
            "events": [],
        }

    def _map_event(self, ev: AuditEvent) -> dict[str, Any]:
        payload = {}
        try:
            payload = json.loads(ev.payload_json) if ev.payload_json else {}
        except Exception:
            payload = {}
        redacted_payload = _redact_value(payload)
        details_str = json.dumps(redacted_payload) if redacted_payload else f"{ev.event_family}: {ev.event_type}"

        sev = ev.severity or derive_audit_severity(ev.event_type)
        stat = ev.status or derive_audit_status(ev.event_type)

        rec_time = ev.recorded_at_utc
        time_str = rec_time.isoformat() if isinstance(rec_time, datetime) else str(rec_time)

        return {
            "id": f"aud-{ev.event_id[:8]}",
            "eventId": ev.event_id,
            "timestamp": time_str,
            "actor": ev.source_identity or "ENGINE",
            "actorType": "ENGINE" if "ENGINE" in (ev.source_identity or "").upper() else "SYSTEM",
            "eventFamily": ev.event_family,
            "eventType": ev.event_type,
            "severity": sev,
            "status": stat,
            "entity": f"{ev.aggregate_type}: {ev.aggregate_identity}" if ev.aggregate_type else (ev.instrument_key or "SYSTEM"),
            "strategyId": ev.strategy_id,
            "orderId": ev.broker_order_identity or ev.entry_intent_identity,
            "sessionId": ev.run_id,
            "details": details_str,
            "evidenceRef": ev.canonical_configuration_fingerprint or (f"audit-seq-{ev.audit_sequence}" if ev.audit_sequence else ev.event_id),
            "reason": redacted_payload.get("reason") or redacted_payload.get("error"),
        }

    def _map_row(self, row: dict[str, Any]) -> dict[str, Any]:
        payload_str = row.get("payload_json") or "{}"
        try:
            payload = json.loads(payload_str)
        except Exception:
            payload = {}
        redacted_payload = _redact_value(payload)
        details_str = json.dumps(redacted_payload) if redacted_payload else f"{row.get('event_family')}: {row.get('event_type')}"

        ev_type = row.get("event_type", "UNKNOWN")
        sev = row.get("severity") or derive_audit_severity(ev_type)
        stat = row.get("status") or derive_audit_status(ev_type)

        return {
            "id": f"aud-{(row.get('event_id') or '00000000')[:8]}",
            "eventId": row.get("event_id") or "UNKNOWN",
            "timestamp": row.get("recorded_at_utc") or "",
            "actor": row.get("source_identity") or "ENGINE",
            "actorType": "ENGINE",
            "eventFamily": row.get("event_family") or "SYSTEM",
            "eventType": ev_type,
            "severity": sev,
            "status": stat,
            "entity": f"{row.get('aggregate_type', '')}: {row.get('aggregate_identity', '')}".strip(": ") or "SYSTEM",
            "strategyId": row.get("strategy_id"),
            "orderId": row.get("broker_order_identity") or row.get("entry_intent_identity"),
            "sessionId": row.get("run_id"),
            "details": details_str,
            "evidenceRef": row.get("canonical_configuration_fingerprint") or (f"audit-seq-{row.get('audit_sequence')}" if row.get("audit_sequence") else row.get("event_id", "")),
            "reason": redacted_payload.get("reason") or redacted_payload.get("error"),
        }


class PersistenceHealthReadAdapter:
    """Read-only verified facts about the SQLite persistence store."""
    def __init__(self, persistence_store: object | None = None, *, db_path: Path | str | None = None) -> None:
        self._persistence_store = persistence_store
        self._db_path = Path(db_path) if db_path else None

    def read_persistence_health(self, *, as_of_utc: datetime | None = None) -> dict[str, Any]:
        now = as_of_utc or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        target_path = self._db_path
        if target_path is None and self._persistence_store is not None:
            target_path = getattr(self._persistence_store, "_db_path", None)
            if target_path:
                target_path = Path(target_path)

        if target_path is None:
            return {
                "source": "BACKEND",
                "trust": "UNKNOWN",
                "as_of_utc": now.isoformat(),
                "adapter_reachable": True,
                "database_connected": False,
                "schema_version": None,
                "journal_mode": "UNKNOWN",
                "audit_store_operational": False,
                "audit_event_count": 0,
                "subsystems": {
                    "backend_api": "OPERATIONAL",
                    "persistence": "UNAVAILABLE",
                    "audit_journal": "UNAVAILABLE",
                    "engine_orchestrator": "NOT_CONNECTED",
                    "broker_adapters": "DEFERRED",
                    "market_data_feeds": "NOT_CONNECTED",
                    "risk_runtime": "DEFERRED",
                    "service_entitlement": "DEFERRED",
                },
            }

        try:
            if not target_path.exists():
                return {
                    "source": "BACKEND",
                    "trust": "UNKNOWN",
                    "as_of_utc": now.isoformat(),
                    "adapter_reachable": True,
                    "database_connected": False,
                    "schema_version": None,
                    "journal_mode": "UNKNOWN",
                    "audit_store_operational": False,
                    "audit_event_count": 0,
                    "subsystems": {
                        "backend_api": "OPERATIONAL",
                        "persistence": "NOT_FOUND",
                        "audit_journal": "NOT_FOUND",
                        "engine_orchestrator": "NOT_CONNECTED",
                        "broker_adapters": "DEFERRED",
                        "market_data_feeds": "NOT_CONNECTED",
                        "risk_runtime": "DEFERRED",
                        "service_entitlement": "DEFERRED",
                    },
                }

            conn = sqlite3.connect(f"file:{target_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            cursor.execute("PRAGMA schema_version;")
            schema_ver = cursor.fetchone()[0]

            cursor.execute("PRAGMA journal_mode;")
            journal_mode = cursor.fetchone()[0].lower()

            cursor.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='audit_events';")
            has_audit = bool(cursor.fetchone()[0])

            audit_count = 0
            if has_audit:
                cursor.execute("SELECT count(*) FROM audit_events;")
                audit_count = cursor.fetchone()[0]

            conn.close()

            return {
                "source": "BACKEND",
                "trust": "FRESH",
                "as_of_utc": now.isoformat(),
                "adapter_reachable": True,
                "database_connected": True,
                "schema_version": schema_ver,
                "journal_mode": journal_mode,
                "audit_store_operational": has_audit,
                "audit_event_count": audit_count,
                "subsystems": {
                    "backend_api": "OPERATIONAL",
                    "persistence": "OPERATIONAL",
                    "audit_journal": "OPERATIONAL" if has_audit else "DEGRADED",
                    "engine_orchestrator": "NOT_CONNECTED",
                    "broker_adapters": "DEFERRED",
                    "market_data_feeds": "NOT_CONNECTED",
                    "risk_runtime": "DEFERRED",
                    "service_entitlement": "DEFERRED",
                },
            }
        except Exception:
            return {
                "source": "BACKEND",
                "trust": "UNKNOWN",
                "as_of_utc": now.isoformat(),
                "adapter_reachable": True,
                "database_connected": False,
                "schema_version": None,
                "journal_mode": "UNKNOWN",
                "audit_store_operational": False,
                "audit_event_count": 0,
                "subsystems": {
                    "backend_api": "OPERATIONAL",
                    "persistence": "ERROR",
                    "audit_journal": "ERROR",
                    "engine_orchestrator": "NOT_CONNECTED",
                    "broker_adapters": "DEFERRED",
                    "market_data_feeds": "NOT_CONNECTED",
                    "risk_runtime": "DEFERRED",
                    "service_entitlement": "DEFERRED",
                },
            }


class AccessRegistryReadAdapter:
    """Read-only projection for Owner Access Registry and Service Entitlements."""

    def __init__(self, *, security_store: object | None = None) -> None:
        self._security_store = security_store

    def _mask_email(self, email: str | None) -> str | None:
        if not email:
            return None
        if "@" not in email:
            return email
        user, domain = email.split("@", 1)
        if len(user) <= 2:
            return f"{user[0]}*@{domain}"
        return f"{user[:2]}{'•' * min(len(user) - 2, 5)}@{domain}"

    def _mask_phone(self, phone: str | None) -> str | None:
        if not phone:
            return None
        clean = phone.strip()
        if len(clean) < 8:
            return clean
        prefix = clean[:6]
        suffix = clean[-3:]
        return f"{prefix} •••• {suffix}"

    def _get_service_label(self, term_type: str, custom_val: int | None, custom_unit: str | None) -> str:
        if term_type == "LIFETIME":
            return "Lifetime"
        if term_type == "1_MONTH":
            return "1 Month"
        if term_type == "3_MONTHS":
            return "3 Months"
        if term_type == "6_MONTHS":
            return "6 Months"
        if term_type == "12_MONTHS":
            return "12 Months"
        if term_type in {"CUSTOM_DAYS", "CUSTOM"} and (custom_unit == "DAYS" or term_type == "CUSTOM_DAYS"):
            val = custom_val or 30
            return f"{val} {'Day' if val == 1 else 'Days'}"
        if term_type in {"CUSTOM_MONTHS", "CUSTOM"} and (custom_unit == "MONTHS" or term_type == "CUSTOM_MONTHS"):
            val = custom_val or 1
            return f"{val} {'Month' if val == 1 else 'Months'}"
        return "3 Months"

    def read_access_records(self, *, now_utc: datetime | None = None) -> dict[str, object]:
        now = now_utc or datetime.now(timezone.utc)
        if self._security_store is None:
            return {
                "source": "BACKEND",
                "trust": "UNKNOWN",
                "as_of_utc": now.isoformat(),
                "total_count": 0,
                "records": [],
                "error": "SECURITY_STORE_UNAVAILABLE",
            }

        try:
            if hasattr(self._security_store, "list_users"):
                rows = self._security_store.list_users()
            elif hasattr(self._security_store, "_conn"):
                rows = self._security_store._conn.execute("SELECT * FROM users ORDER BY created_at_utc ASC").fetchall()
            else:
                rows = ()

            records = []
            for row in rows:
                keys = row.keys()
                role_val = row["role"]
                lifecycle_val = row["lifecycle"]
                uid = row["user_id"]
                sx_id = row["sx_id"] if "sx_id" in keys and row["sx_id"] else f"SX-U-{uid[:4].upper()}-{uid[-4].upper()}"
                acct_status = row["account_status"] if "account_status" in keys and row["account_status"] else ("ACTIVE" if lifecycle_val == "ACTIVE" else "SUSPENDED")
                act_status = row["activation_status"] if "activation_status" in keys and row["activation_status"] else "REDEEMED"
                srv_status = row["service_status"] if "service_status" in keys and row["service_status"] else ("ACTIVE" if role_val == "OWNER" else "ACTIVE")
                srv_started = row["service_started_at"] if "service_started_at" in keys and row["service_started_at"] else (row["created_at_utc"] if role_val == "OWNER" else None)
                srv_expires = row["service_expires_at"] if "service_expires_at" in keys and row["service_expires_at"] else None
                srv_type = row["service_term_type"] if "service_term_type" in keys and row["service_term_type"] else "LIFETIME"
                custom_val = row["custom_term_value"] if "custom_term_value" in keys else None
                custom_unit = row["custom_term_unit"] if "custom_term_unit" in keys else None
                display_name = row["display_name"]
                email = row["bound_email"] if "bound_email" in keys and row["bound_email"] else None
                phone = row["bound_phone"] if "bound_phone" in keys and row["bound_phone"] else None
                notes = row["notes"] if "notes" in keys and row["notes"] is not None else None
                plan = row["plan"] if "plan" in keys and row["plan"] is not None else None
                created_by = row["created_by"] if "created_by" in keys and row["created_by"] is not None else None

                label = self._get_service_label(srv_type, custom_val, custom_unit)

                effective_srv = srv_status
                if role_val == "OWNER":
                    effective_srv = "ACTIVE"
                elif act_status in {"DRAFT", "INVITED"} or not srv_started:
                    effective_srv = "NOT_STARTED"
                elif srv_expires is not None:
                    try:
                        exp_dt = datetime.fromisoformat(srv_expires)
                        if exp_dt.tzinfo is None:
                            exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                        effective_srv = "EXPIRED" if now >= exp_dt else "ACTIVE"
                    except Exception:
                        effective_srv = srv_status

                # Load issuances for activation history
                activation_history = []
                active_issuance_exp = None
                if hasattr(self._security_store, "get_user_issuances"):
                    try:
                        iss_rows = self._security_store.get_user_issuances(uid)
                        for iss in iss_rows:
                            iss_keys = iss.keys()
                            iss_status = iss["status"]
                            iss_exp = iss["expires_at_utc"]
                            if iss_status == "INVITED":
                                active_issuance_exp = iss_exp
                            activation_history.append({
                                "id": iss["issuance_id"],
                                "code": None,  # NEVER expose code or hash in read projection
                                "issuedAt": iss["issued_at_utc"],
                                "expiresAt": iss_exp,
                                "status": iss_status,
                                "redeemedAt": iss["redeemed_at_utc"] if "redeemed_at_utc" in iss_keys else None,
                                "revokedAt": iss["revoked_at_utc"] if "revoked_at_utc" in iss_keys else None,
                                "actor": iss["actor"] if "actor" in iss_keys and iss["actor"] else (created_by or "SYSTEM"),
                                "notes": iss["notes"] if "notes" in iss_keys and iss["notes"] is not None else "",
                            })
                    except Exception:
                        pass

                records.append({
                    "id": f"acc-{uid[:8]}",
                    "sxId": sx_id,
                    "accessId": sx_id,
                    "activationCode": None,  # Plaintext activation code never returned in read projection
                    "activationStatus": act_status,
                    "accountStatus": acct_status,
                    "status": acct_status,
                    "displayName": display_name,
                    "email": email,
                    "phone": phone,
                    "emailMasked": self._mask_email(email),
                    "phoneMasked": self._mask_phone(phone),
                    "createdAt": row["created_at_utc"],
                    "expiresAt": active_issuance_exp,
                    "redeemedAt": srv_started if act_status == "REDEEMED" else None,
                    "serviceTermType": srv_type,
                    "serviceTermCustom": {"value": custom_val, "unit": custom_unit or "DAYS"} if custom_val else None,
                    "serviceTermLabel": label,
                    "serviceStatus": effective_srv,
                    "serviceStartedAt": srv_started,
                    "serviceExpiresAt": srv_expires,
                    "notes": notes,
                    "role": role_val,
                    "plan": plan,
                    "createdBy": created_by,
                    "history": [{"time": row["created_at_utc"], "action": "INITIAL_CREATION", "actor": created_by or "SYSTEM"}],
                    "activationHistory": activation_history,
                })

            return {
                "source": "BACKEND",
                "trust": "FRESH",
                "as_of_utc": now.isoformat(),
                "total_count": len(records),
                "records": records,
            }
        except Exception as exc:
            return {
                "source": "BACKEND",
                "trust": "UNKNOWN",
                "as_of_utc": now.isoformat(),
                "total_count": 0,
                "records": [],
                "error": str(exc),
            }


class OwnerStrategiesReadAdapter:
    """Read-only projection of owner strategies governance state."""
    def __init__(self, *, security_store: object | None = None) -> None:
        self._security_store = security_store

    def read_strategies(self, *, now_utc: datetime | None = None) -> dict[str, object]:
        now = now_utc or datetime.now(timezone.utc)
        if self._security_store is None:
            return {
                "source": "BACKEND",
                "trust": "UNKNOWN",
                "as_of_utc": now.isoformat(),
                "total_count": 0,
                "strategies": [],
                "error": "SECURITY_STORE_UNAVAILABLE",
            }
        try:
            strategies = self._security_store.list_owner_strategies()
            return {
                "source": "BACKEND",
                "trust": "FRESH",
                "as_of_utc": now.isoformat(),
                "total_count": len(strategies),
                "strategies": strategies,
            }
        except Exception as exc:
            return {
                "source": "BACKEND",
                "trust": "UNKNOWN",
                "as_of_utc": now.isoformat(),
                "total_count": 0,
                "strategies": [],
                "error": str(exc),
            }

    def get_strategy(self, strategy_id: str) -> dict[str, object] | None:
        if self._security_store is None:
            return None
        try:
            return self._security_store.get_owner_strategy(strategy_id)
        except Exception:
            return None


class OwnerConnectionsReadAdapter:
    """Read-only projection of owner broker / data connection authority."""
    def __init__(self, *, security_store: object | None = None) -> None:
        self._security_store = security_store

    def read_connections(self, *, now_utc: datetime | None = None) -> dict[str, object]:
        now = now_utc or datetime.now(timezone.utc)
        if self._security_store is None:
            return {
                "source": "BACKEND",
                "trust": "UNKNOWN",
                "as_of_utc": now.isoformat(),
                "total_count": 0,
                "connections": [],
                "error": "SECURITY_STORE_UNAVAILABLE",
            }
        try:
            connections = self._security_store.list_owner_connections()
            return {
                "source": "BACKEND",
                "trust": "FRESH",
                "as_of_utc": now.isoformat(),
                "total_count": len(connections),
                "connections": connections,
            }
        except Exception as exc:
            return {
                "source": "BACKEND",
                "trust": "UNKNOWN",
                "as_of_utc": now.isoformat(),
                "total_count": 0,
                "connections": [],
                "error": str(exc),
            }

    def get_connection(self, connection_id: str) -> dict[str, object] | None:
        if self._security_store is None:
            return None
        try:
            return self._security_store.get_owner_connection(connection_id)
        except Exception:
            return None


class OwnerDatasetsReadAdapter:
    """Read-only projection of owner dataset authority and gap verification."""
    def __init__(self, *, security_store: object | None = None) -> None:
        self._security_store = security_store

    def read_datasets(self, *, now_utc: datetime | None = None) -> dict[str, object]:
        now = now_utc or datetime.now(timezone.utc)
        if self._security_store is None:
            return {
                "source": "BACKEND",
                "trust": "UNKNOWN",
                "as_of_utc": now.isoformat(),
                "total_count": 0,
                "datasets": [],
                "error": "SECURITY_STORE_UNAVAILABLE",
            }
        try:
            datasets = self._security_store.list_owner_datasets()
            return {
                "source": "BACKEND",
                "trust": "FRESH",
                "as_of_utc": now.isoformat(),
                "total_count": len(datasets),
                "datasets": datasets,
            }
        except Exception as exc:
            return {
                "source": "BACKEND",
                "trust": "UNKNOWN",
                "as_of_utc": now.isoformat(),
                "total_count": 0,
                "datasets": [],
                "error": str(exc),
            }

    def get_dataset(self, dataset_id: str) -> dict[str, object] | None:
        if self._security_store is None:
            return None
        try:
            return self._security_store.get_owner_dataset(dataset_id)
        except Exception:
            return None


class SentinelXReadAdapters:
    """Concrete, read-only projections of existing SentinelX authorities.

    Callers inject existing objects/functions; this class deliberately cannot
    construct or replace any engine authority.
    """
    def __init__(self, *, persistence_store: object | None = None, audit_store: object | None = None,
                 security_store: object | None = None,
                 backtest_reader: Callable[[], object] | None = None,
                 strategy_reader: Callable[[], object] | None = None,
                 risk_reader: Callable[[], object] | None = None,
                 protective_reader: Callable[[], object] | None = None) -> None:
        self._persistence_store, self._audit_store, self._security_store = persistence_store, audit_store, security_store
        self._readers = {"backtest": backtest_reader, "strategy": strategy_reader, "risk": risk_reader, "protective": protective_reader}
        self.audit_adapter = D16AuditReadAdapter(persistence_store=audit_store or persistence_store)
        self.health_adapter = PersistenceHealthReadAdapter(persistence_store=persistence_store)
        self.access_adapter = AccessRegistryReadAdapter(security_store=security_store)
        self.strategies_adapter = OwnerStrategiesReadAdapter(security_store=security_store)
        self.connections_adapter = OwnerConnectionsReadAdapter(security_store=security_store)
        self.datasets_adapter = OwnerDatasetsReadAdapter(security_store=security_store)

    @staticmethod
    def _project(value: object, *, source: str, as_of_utc: datetime) -> TrustedValue:
        if as_of_utc.tzinfo is None:
            return TrustedValue(None, TrustState.UNKNOWN, None)
        return TrustedValue(value, TrustState.FRESH, as_of_utc, source)

    def persistence(self, *, as_of_utc: datetime) -> TrustedValue:
        loader = getattr(self._persistence_store, "load_state", None)
        try:
            return self._project(loader(), source="SQLitePaperStateStore.load_state", as_of_utc=as_of_utc) if callable(loader) else TrustedValue(None, TrustState.UNKNOWN, None)
        except Exception:
            return TrustedValue(None, TrustState.UNKNOWN, None)

    def audit(self, *, as_of_utc: datetime) -> TrustedValue:
        query = getattr(self._audit_store, "query_audit_events", None)
        try:
            return self._project(tuple(query()), source="SQLitePaperStateStore.query_audit_events", as_of_utc=as_of_utc) if callable(query) else TrustedValue(None, TrustState.UNKNOWN, None)
        except Exception:
            return TrustedValue(None, TrustState.UNKNOWN, None)

    def read_existing(self, name: str, *, as_of_utc: datetime) -> TrustedValue:
        reader = self._readers.get(name)
        try:
            return self._project(reader(), source=f"SentinelX.{name}", as_of_utc=as_of_utc) if callable(reader) else TrustedValue(None, TrustState.UNKNOWN, None)
        except Exception:
            return TrustedValue(None, TrustState.UNKNOWN, None)
