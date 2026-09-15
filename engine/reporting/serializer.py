"""Strict public-safe JSON projection for the closed Slice 13 v1 schema."""

from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Mapping

from engine.reproducibility.codec import CanonicalCodec, CanonicalEncodingError
from engine.reporting.model import (
    CategoryAPayload, CategoryBPayload, CategoryCPayload, RandomizedAnalysisCollectionEvidence, RandomizedAnalysisEvidence,
    REPORT_SCHEMA_VERSION, REPORT_SCHEMA_VERSION_V2, REPORT_SCHEMA_VERSION_V3, InvalidFinalizationPayload, ResultKind, StructuredBacktestResult, SuccessPayload,
)


class ReportSerializationError(ValueError):
    """Raised when an export cannot meet the closed public schema."""


_DEFENSE_IN_DEPTH_FORBIDDEN_KEYS = frozenset({
    "path", "filepath", "file_path", "username", "hostname", "host", "credential",
    "credentials", "api_key", "apikey", "token", "password", "secret", "exception",
    "error", "message", "traceback", "stack", "stacktrace", "environment", "env",
    "operational_context",
})
_PUBLIC_EVIDENCE_FIELDS = frozenset({
    # Closed report envelope and variant fields.
    "attempt_id", "payload", "policy_identity", "pre_manifest_evidence",
    "randomized_analysis", "report_generated_at", "result_kind", "schema_version",
    "entries", "analysis_kind", "scope_identity", "evidence_schema_version", "evidence_result_fingerprint",
    # Common identity, provenance, and status fields from Slice 1–12 evidence.
    "account_id", "accounting_sequence", "action", "amount", "annualization_sessions",
    "assessment_id", "average_entry_price", "basis", "block_length", "code_member",
    "code_type", "component_id", "component_results", "configuration_fingerprint",
    "contract_multiplier", "cost_policy_fingerprint", "cost_evidence_fingerprint", "costs", "currency", "data_fingerprint",
    "dependency_policy_identity", "derived_seed", "effective_from", "effective_to",
    "engine_version", "entry_legs", "entry_quantity", "environment_conformance", "evidence",
    "evidence_id", "execution_bar_timestamp", "execution_evidence", "execution_price",
    "execution_quantity", "execution_timestamp", "exit_legs", "exit_quantity", "expiry",
    "failure_schema", "fill_price", "filled_quantity", "gross_equity", "gross_realized_pnl",
    "holding_duration", "identity", "implementation", "input_amount", "instrument",
    "instrument_identity", "interface_version", "kind", "market", "market_data_identity",
    "market_profile_fingerprint", "mark_price", "mark_timestamp", "metric_policy_fingerprint",
    "metrics", "monetary_quantum", "net_basis", "net_equity", "net_realized_pnl",
    "opening_event_key", "opened_at", "option_type", "order", "originating_timestamp",
    "outcome", "parameter_fingerprint", "policy", "portfolio_equity_evidence", "position_key",
    "position_side", "pre_slippage_price", "price", "provenance", "quantity", "rate",
    "realized_pnl", "realized_pnl_delta", "reproducibility", "result_evidence", "role",
    "root_seed", "rounding_mode", "run_id", "schedule_fingerprint", "schedule_id",
    "schedule_references", "schedule_version", "seed_derivation_policy_identity",
    "seed_policy_fingerprint", "segment", "slippage_amount", "slippage_model_id", "source_data_fingerprint",
    "source_evidence", "source_run_id", "stage", "starting_capital", "status", "strategy_id",
    "strategy_identity", "strategy_version", "strike", "symbol", "timeframe", "timestamp",
    "total_cost", "trade_evidence_fingerprint", "trade_id", "trades", "underlying",
    "unrealized_pnl", "unrounded_amount", "validation", "validation_identity",
    "validation_policy_fingerprint", "valuation_timeframe", "value", "version", "window_id",
    "expectancy", "observed", "lower_bound", "upper_bound", "confidence_level", "sample_count",
    "missing_component", "operational_class", "failure_result_fingerprint", "manifest_fingerprint",
    "result_fingerprint", "parameter_identity", "configuration_identity", "runtime_identity",
    "timezone_calendar_identity", "dependencies", "randomness_policy_identity",
    "regime_evidence", "regime_evidence_fingerprint", "regime_status", "regime", "regime_reconciliation",
    "TRENDING", "SIDEWAYS", "VOLATILE", "UNCLASSIFIED_WARMUP",
    "promotion_status", "promotable", "promotion_gates", "promotion_evidence_fingerprint", "validation_collection_fingerprint",
    "gate_kind", "reason", "invalid_reasons", "result_status",
})
_WINDOWS_ABSOLUTE = re.compile(r"^[A-Za-z]:[\\/]")
_SAFE_ATTEMPT = re.compile(r"^[A-Za-z0-9_-]+$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{9}Z$")


def _validate_text(value: str) -> str:
    if not isinstance(value, str):
        raise ReportSerializationError("public JSON text must be a string")
    if "\ufeff" in value or any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ReportSerializationError("public JSON rejects BOM and unpaired surrogate text")
    if _WINDOWS_ABSOLUTE.match(value) or value.startswith("/") or value.startswith("\\\\"):
        raise ReportSerializationError("public JSON cannot contain an absolute filesystem path")
    return value


def _decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise ReportSerializationError("non-finite Decimal is not public authoritative evidence")
    if value.is_zero():
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _key_allowed(key: str) -> str:
    key = _validate_text(key)
    if key.casefold() in _DEFENSE_IN_DEPTH_FORBIDDEN_KEYS or key not in _PUBLIC_EVIDENCE_FIELDS:
        raise ReportSerializationError(f"public JSON field is not allowlisted: {key}")
    return key


def _value(value: object) -> object:
    if value is None:
        raise ReportSerializationError("null is not allowed without an explicit upstream null contract")
    if isinstance(value, str):
        return _validate_text(value)
    if isinstance(value, bool) or isinstance(value, int):
        return value
    if isinstance(value, float):
        raise ReportSerializationError("float values are forbidden in canonical reporting JSON")
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, Enum):
        return _validate_text(value.name)
    if CanonicalCodec._is_pandas_timestamp(value) or isinstance(value, datetime):
        try:
            return CanonicalCodec.timestamp_text(value)
        except CanonicalEncodingError as error:
            raise ReportSerializationError(str(error)) from error
    if isinstance(value, Mapping):
        return {key: _value(item) for key, item in sorted(((_key_allowed(key), item) for key, item in value.items()), key=lambda item: item[0])}
    if isinstance(value, (tuple, list)):
        return [_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        raise ReportSerializationError("unordered collections are forbidden")
    raise ReportSerializationError(f"unsupported public reporting value: {type(value).__name__}")


class ReportSerializer:
    """Projects typed reporting values into the closed v1 public JSON schema."""

    @classmethod
    def document(cls, result: StructuredBacktestResult) -> dict[str, object]:
        if not isinstance(result, StructuredBacktestResult):
            raise TypeError("result must be StructuredBacktestResult")
        return {
            "schema_version": result.schema_version,
            "result_kind": result.result_kind.value,
            "report_generated_at": _value(result.report_generated_at),
            "provenance": cls._provenance(result),
            "payload": cls._payload(result.payload),
        }

    @classmethod
    def serialize(cls, result: StructuredBacktestResult) -> bytes:
        document = cls.document(result)
        try:
            return json.dumps(document, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError, UnicodeError) as error:
            raise ReportSerializationError("unable to encode strict UTF-8 report JSON") from error

    @classmethod
    def _provenance(cls, result: StructuredBacktestResult) -> dict[str, object]:
        value: dict[str, object] = {}
        if result.provenance.attempt_id is not None:
            if not _SAFE_ATTEMPT.fullmatch(result.provenance.attempt_id):
                raise ReportSerializationError("attempt_id is not public-safe")
            value["attempt_id"] = _value(result.provenance.attempt_id)
        if result.provenance.environment_conformance is not None:
            value["environment_conformance"] = _value(result.provenance.environment_conformance)
        return value

    @classmethod
    def _randomized(cls, value: RandomizedAnalysisEvidence | RandomizedAnalysisCollectionEvidence) -> dict[str, object]:
        if isinstance(value, RandomizedAnalysisCollectionEvidence):
            return {
                "schema_version": value.schema_version,
                "identity": value.identity,
                "entries": _value(value.entries),
            }
        body: dict[str, object] = {
            "kind": _value(value.kind),
            "root_seed": _value(str(value.root_seed)),
            "seed_derivation_policy_identity": _value(value.seed_derivation_policy_identity),
            "identity": _value(value.identity),
            "result_evidence": _value(value.result_evidence),
        }
        if value.derived_seed is not None:
            body["derived_seed"] = _value(str(value.derived_seed))
        return body

    @classmethod
    def _payload(cls, payload: object) -> dict[str, object]:
        if isinstance(payload, SuccessPayload):
            body: dict[str, object] = {
                "manifest_fingerprint": payload.manifest_fingerprint,
                "result_fingerprint": payload.result_fingerprint,
                "strategy_identity": _value(payload.strategy_identity),
                "parameter_identity": payload.parameter_identity,
                "market_data_identity": payload.market_data_identity,
                "configuration_identity": payload.configuration_identity,
                "validation_identity": payload.validation_identity,
                "trades": _value(payload.trades),
                "execution_evidence": _value(payload.execution_evidence),
                "portfolio_equity_evidence": _value(payload.portfolio_equity_evidence),
                "costs": _value(payload.costs),
                "metrics": _value(payload.metrics),
                "validation": _value(payload.validation),
                "reproducibility": _value(payload.reproducibility),
            }
            if payload.randomized_analysis is not None:
                body["randomized_analysis"] = cls._randomized(payload.randomized_analysis)
            if payload.regime_evidence_fingerprint is not None:
                body["regime_evidence"] = _value(payload.regime_evidence)
                body["regime_evidence_fingerprint"] = payload.regime_evidence_fingerprint
            if payload.promotion_status is not None:
                body.update({
                    "promotion_status": payload.promotion_status,
                    "promotable": payload.promotable,
                    "promotion_gates": _value(payload.promotion_gates),
                    "promotion_evidence_fingerprint": payload.promotion_evidence_fingerprint,
                    "validation_collection_fingerprint": payload.validation_collection_fingerprint,
                })
            return body
        if isinstance(payload, InvalidFinalizationPayload):
            return {
                "manifest_fingerprint": payload.manifest_fingerprint,
                "result_fingerprint": payload.result_fingerprint,
                "result_status": "INVALID",
                "promotion_status": payload.promotion_status,
                "promotable": payload.promotable,
                "invalid_reasons": _value(payload.invalid_reasons),
                "promotion_evidence_fingerprint": payload.promotion_evidence_fingerprint,
                "validation_collection_fingerprint": payload.validation_collection_fingerprint,
                "promotion_gates": _value(payload.promotion_gates),
            }
        if isinstance(payload, CategoryAPayload):
            reproducibility = dict(_value(payload.reproducibility))
            if payload.randomized_analysis is not None:
                reproducibility["randomized_analysis"] = cls._randomized(payload.randomized_analysis)
            body = {
                "manifest_fingerprint": payload.manifest_fingerprint,
                "failure_result_fingerprint": payload.failure_result_fingerprint,
                "failure_schema": _value(payload.failure_schema),
                "code_type": _value(payload.code_type),
                "code_member": _value(payload.code_member),
                "stage": _value(payload.stage),
                "policy_identity": payload.policy_identity,
                "evidence": _value(payload.evidence),
                "reproducibility": reproducibility,
            }
            return body
        if isinstance(payload, CategoryBPayload):
            return {"pre_manifest_evidence": _value(payload.pre_manifest_evidence)}
        if isinstance(payload, CategoryCPayload):
            body = {"operational_class": _value(payload.operational_class)}
            if payload.manifest_fingerprint is not None:
                body["manifest_fingerprint"] = payload.manifest_fingerprint
            return body
        raise TypeError("unsupported reporting payload")

    @classmethod
    def validate_bytes(cls, raw: bytes) -> dict[str, object]:
        if raw.startswith(b"\xef\xbb\xbf"):
            raise ReportSerializationError("UTF-8 BOM is forbidden")
        try:
            text = raw.decode("utf-8")
            document = json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ReportSerializationError("non-standard JSON number")))
        except (UnicodeDecodeError, json.JSONDecodeError, ReportSerializationError) as error:
            raise ReportSerializationError("report is not strict UTF-8 JSON") from error
        if not isinstance(document, dict) or tuple(document) != ("schema_version", "result_kind", "report_generated_at", "provenance", "payload"):
            raise ReportSerializationError("report top-level schema is closed and ordered")
        if document["schema_version"] not in {REPORT_SCHEMA_VERSION, REPORT_SCHEMA_VERSION_V2, REPORT_SCHEMA_VERSION_V3} or document["result_kind"] not in {kind.value for kind in ResultKind}:
            raise ReportSerializationError("unknown report schema or result kind")
        if not isinstance(document["provenance"], dict) or not isinstance(document["payload"], dict):
            raise ReportSerializationError("report provenance and payload must be objects")
        if not isinstance(document["report_generated_at"], str) or not _TIMESTAMP.fullmatch(document["report_generated_at"]):
            raise ReportSerializationError("report_generated_at must be a D4 UTC nanosecond timestamp")
        cls._validate_variant_schema(document["schema_version"], document["result_kind"], document["provenance"], document["payload"])
        cls._validate_tree(document)
        return document

    @staticmethod
    def _validate_variant_schema(schema_version: str, kind: str, provenance: dict[str, object], payload: dict[str, object]) -> None:
        if set(provenance) - {"attempt_id", "environment_conformance"}:
            raise ReportSerializationError("report provenance contains unknown fields")
        expected = {
            ResultKind.SUCCESS.value: {
                "manifest_fingerprint", "result_fingerprint", "strategy_identity", "parameter_identity",
                "market_data_identity", "configuration_identity", "validation_identity", "trades",
                "execution_evidence", "portfolio_equity_evidence", "costs", "metrics", "validation",
                "reproducibility", "randomized_analysis",
                "promotion_status", "promotable", "promotion_gates", "promotion_evidence_fingerprint", "validation_collection_fingerprint",
            },
            ResultKind.INVALID_FINALIZED.value: {"manifest_fingerprint", "result_fingerprint", "result_status", "promotion_status", "promotable", "invalid_reasons", "promotion_evidence_fingerprint", "validation_collection_fingerprint", "promotion_gates"},
            ResultKind.CATEGORY_A.value: {
                "manifest_fingerprint", "failure_result_fingerprint", "failure_schema", "code_type",
                "code_member", "stage", "policy_identity", "evidence", "reproducibility",
            },
            ResultKind.CATEGORY_B.value: {"pre_manifest_evidence"},
            ResultKind.CATEGORY_C.value: {"operational_class", "manifest_fingerprint"},
        }[kind]
        if schema_version != REPORT_SCHEMA_VERSION_V3 and kind == ResultKind.SUCCESS.value:
            expected = expected - {"promotion_status", "promotable", "promotion_gates", "promotion_evidence_fingerprint", "validation_collection_fingerprint"}
        required = expected - {"randomized_analysis", "manifest_fingerprint" if kind == ResultKind.CATEGORY_C.value else ""}
        if schema_version == REPORT_SCHEMA_VERSION_V2 and kind == ResultKind.SUCCESS.value:
            expected = expected | {"regime_evidence", "regime_evidence_fingerprint"}
            required = required | {"regime_evidence", "regime_evidence_fingerprint"}
        if schema_version == REPORT_SCHEMA_VERSION_V3:
            if kind == ResultKind.SUCCESS.value:
                required = required | {"promotion_status", "promotable", "promotion_gates", "promotion_evidence_fingerprint", "validation_collection_fingerprint"}
            elif kind == ResultKind.INVALID_FINALIZED.value:
                required = expected
        if set(payload) - expected or not required <= set(payload):
            raise ReportSerializationError("report payload violates its closed result variant schema")

    @classmethod
    def _validate_tree(cls, value: object) -> None:
        if isinstance(value, str):
            _validate_text(value)
        elif isinstance(value, list):
            for item in value:
                cls._validate_tree(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                _key_allowed(key)
                cls._validate_tree(item)
        elif value is None or isinstance(value, float):
            raise ReportSerializationError("report contains forbidden null or float")
