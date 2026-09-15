"""Strict Phase-5 paper-runtime configuration resolution.

This module is deliberately limited to configuration parsing, validation, and
construction of existing domain components.  It does not own execution,
accounting, RiskGate, or protective lifecycle behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import yaml

from engine.costs import CostSchedule
from engine.execution.paper_fill import FixedBasisPointsSlippage, PaperFillPolicy
from engine.data.feeds.live_feed import SubscriptionOwnerKey
from engine.protective.plan import ProtectivePlanPolicy
from engine.paper.protective_policy_registry import (
    ProtectivePolicyRegistrationKey,
    ProtectivePolicyRegistry,
    ProtectivePolicyRegistryError,
)
from engine.reproducibility import CanonicalCodec
from engine.risk.risk_manager import RiskPolicy


class PaperConfigurationError(ValueError):
    """Raised when paper configuration is absent, malformed, or unsafe."""


class _StrictYamlLoader(yaml.SafeLoader):
    """Safe YAML loader that also rejects duplicate mapping keys."""


def _construct_unique_mapping(loader: _StrictYamlLoader, node, deep: bool = False):
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise PaperConfigurationError(f"duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictYamlLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


RISK_POLICY_VERSION = "risk-policy/v3"
RESEARCH_ZERO_COST_PROFILE = "RESEARCH_ZERO_COST"
RESEARCH_ZERO_SLIPPAGE_PROFILE = "RESEARCH_ZERO_SLIPPAGE"

_LOCKED_RISK_VALUES = {
    "per_trade_risk_pct": Decimal("0.005"),
    "max_daily_loss_pct": Decimal("0.02"),
    "max_daily_trades": 10,
    "max_open_positions": 3,
    "max_portfolio_risk_pct": Decimal("0.03"),
    "capital_allocation_method": "FIXED",
    "min_risk_reward": Decimal("1.5"),
}


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise PaperConfigurationError(f"{field} must be a mapping")
    if not all(isinstance(key, str) for key in value):
        raise PaperConfigurationError(f"{field} keys must be strings")
    return value


def _required(mapping: Mapping[str, object], field: str, context: str) -> object:
    if field not in mapping:
        raise PaperConfigurationError(f"{context}.{field} is required")
    return mapping[field]


def _only(mapping: Mapping[str, object], allowed: set[str], context: str) -> None:
    unknown = set(mapping) - allowed
    if unknown:
        raise PaperConfigurationError(f"{context} contains unsupported fields: {sorted(unknown)!r}")


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PaperConfigurationError(f"{field} must be a non-empty string")
    return value.strip()


def _decimal(value: object, field: str, *, positive: bool = False, non_negative: bool = False) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise PaperConfigurationError(f"{field} must be an exact string or integer, never float")
    if not isinstance(value, (str, int, Decimal)):
        raise PaperConfigurationError(f"{field} must be an exact string or integer")
    try:
        result = Decimal(value) if isinstance(value, int) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise PaperConfigurationError(f"{field} must be a valid Decimal") from exc
    if not result.is_finite():
        raise PaperConfigurationError(f"{field} must be finite")
    if positive and result <= 0:
        raise PaperConfigurationError(f"{field} must be positive")
    if non_negative and result < 0:
        raise PaperConfigurationError(f"{field} must be non-negative")
    return result


def _integer(value: object, field: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PaperConfigurationError(f"{field} must be an integer")
    if positive and value <= 0:
        raise PaperConfigurationError(f"{field} must be positive")
    return value


def _yaml(path: Path) -> Mapping[str, object]:
    if not path.is_file():
        raise PaperConfigurationError(f"configuration file not found: {path}")
    try:
        loaded = yaml.load(path.read_text(encoding="utf-8"), Loader=_StrictYamlLoader)
    except (OSError, yaml.YAMLError, PaperConfigurationError) as exc:
        if isinstance(exc, PaperConfigurationError):
            raise
        raise PaperConfigurationError(f"invalid YAML configuration: {path}") from exc
    return _mapping(loaded, str(path))


def _resolve_path(base: Path, raw: object, field: str) -> Path:
    text = _text(raw, field)
    value = Path(text)
    return value.resolve() if value.is_absolute() else (base / value).resolve()


@dataclass(frozen=True)
class PaperAccountConfiguration:
    account_id: str
    starting_capital: Decimal
    currency: str
    monetary_quantum: Decimal


@dataclass(frozen=True)
class PaperStrategyBindingConfiguration:
    owner: SubscriptionOwnerKey
    activation: str
    instrument: str
    timeframe: str
    source_path: Path
    protective_policy: ProtectivePlanPolicy | None
    protective_policy_key: ProtectivePolicyRegistrationKey | None = None
    protective_policy_parameters: tuple[tuple[str, object], ...] | None = None
    upstream_promotion_evidence_fingerprint: str | None = None
    upstream_promotion_evidence_path: Path | None = None
    upstream_promotion_evidence_promotable: bool = True


@dataclass(frozen=True)
class ResolvedPaperConfiguration:
    source_path: Path
    database_path: Path
    account: PaperAccountConfiguration
    risk_policy: RiskPolicy
    cost_schedules: tuple[CostSchedule, ...]
    paper_fill_policy: PaperFillPolicy
    strategy_bindings: Mapping[SubscriptionOwnerKey, PaperStrategyBindingConfiguration]
    protective_plan_policies: Mapping[SubscriptionOwnerKey, ProtectivePlanPolicy]
    cost_profile_identity: str
    execution_policy_identity: str
    promotion_eligible: bool
    promotion_ineligibility_reasons: tuple[str, ...]
    promotion_tracking_activated: datetime | None = None
    calendar_snapshot: Any | None = None
    calendar_snapshot_path: Path | None = None
    promotion_report_destination_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.promotion_tracking_activated is not None:
            if self.promotion_tracking_activated.tzinfo is None or self.promotion_tracking_activated.utcoffset() is None:
                raise PaperConfigurationError("promotion_tracking_activated must be timezone-aware")

    @property
    def risk_policy_identity(self) -> str:
        return self.risk_policy.fingerprint

    @property
    def configuration_identity(self) -> str:
        calendar_fp = self.calendar_snapshot.calendar_fingerprint if self.calendar_snapshot is not None else None
        return CanonicalCodec.fingerprint(
            "sentinelx-resolved-paper-configuration/v1",
            (
                ("risk_policy", self.risk_policy_identity),
                ("cost_profile", self.cost_profile_identity),
                ("execution_policy", self.execution_policy_identity),
                ("strategies", tuple(
                    (
                        owner.strategy_id,
                        owner.strategy_version,
                        binding.activation,
                        binding.instrument,
                        binding.timeframe,
                        None if binding.protective_policy is None else (
                            binding.protective_policy_key.policy_id,
                            binding.protective_policy_key.policy_version,
                            binding.protective_policy_parameters,
                            binding.protective_policy.policy_identity,
                        ),
                        binding.upstream_promotion_evidence_fingerprint,
                    )
                    for owner, binding in sorted(
                        self.strategy_bindings.items(),
                        key=lambda pair: (pair[0].strategy_id, pair[0].strategy_version),
                    )
                )),
                ("promotion_eligible", self.promotion_eligible),
                ("promotion_ineligibility_reasons", self.promotion_ineligibility_reasons),
                ("promotion_tracking_activated", self.promotion_tracking_activated.isoformat() if self.promotion_tracking_activated is not None else None),
                ("calendar_fingerprint", calendar_fp),
            ),
        )


def _load_risk_policy(path: Path) -> RiskPolicy:
    raw = _yaml(path)
    _only(
        raw,
        {
            "schema_version", "version", "per_trade_risk_pct", "max_daily_loss_pct",
            "max_daily_trades", "max_open_positions", "max_portfolio_risk_pct",
            "capital_allocation_method", "min_risk_reward",
        },
        "risk configuration",
    )
    if _text(_required(raw, "schema_version", "risk configuration"), "risk configuration.schema_version") != "risk-config/v1":
        raise PaperConfigurationError("unsupported risk configuration schema_version")
    if _text(_required(raw, "version", "risk configuration"), "risk configuration.version") != RISK_POLICY_VERSION:
        raise PaperConfigurationError("paper runtime supports only risk-policy/v3")
    values = {
        "per_trade_risk_pct": _decimal(_required(raw, "per_trade_risk_pct", "risk configuration"), "per_trade_risk_pct", positive=True),
        "max_daily_loss_pct": _decimal(_required(raw, "max_daily_loss_pct", "risk configuration"), "max_daily_loss_pct", positive=True),
        "max_daily_trades": _integer(_required(raw, "max_daily_trades", "risk configuration"), "max_daily_trades", positive=True),
        "max_open_positions": _integer(_required(raw, "max_open_positions", "risk configuration"), "max_open_positions", positive=True),
        "max_portfolio_risk_pct": _decimal(_required(raw, "max_portfolio_risk_pct", "risk configuration"), "max_portfolio_risk_pct", positive=True),
        "capital_allocation_method": _text(_required(raw, "capital_allocation_method", "risk configuration"), "capital_allocation_method"),
        "min_risk_reward": _decimal(_required(raw, "min_risk_reward", "risk configuration"), "min_risk_reward", positive=True),
    }
    for name, expected in _LOCKED_RISK_VALUES.items():
        if values[name] != expected:
            raise PaperConfigurationError(f"{name} must equal owner-locked value {expected}")
    return RiskPolicy(
        version=RISK_POLICY_VERSION,
        per_trade_risk_pct=values["per_trade_risk_pct"],
        max_daily_loss_pct=values["max_daily_loss_pct"],
        max_daily_trades=values["max_daily_trades"],
        max_open_positions=values["max_open_positions"],
        max_portfolio_risk_pct=values["max_portfolio_risk_pct"],
        capital_allocation=values["capital_allocation_method"],
        min_risk_reward=values["min_risk_reward"],
    )


def _load_execution_policy(path: Path) -> tuple[PaperFillPolicy, str]:
    raw = _yaml(path)
    _only(raw, {"schema_version", "paper_fill"}, "execution configuration")
    if _text(_required(raw, "schema_version", "execution configuration"), "execution configuration.schema_version") != "execution-config/v1":
        raise PaperConfigurationError("unsupported execution configuration schema_version")
    fill = _mapping(_required(raw, "paper_fill", "execution configuration"), "paper_fill")
    _only(fill, {"profile", "version", "slippage_model", "max_execution_tolerance_bps", "max_slippage_bps"}, "paper_fill")
    profile = _text(_required(fill, "profile", "paper_fill"), "paper_fill.profile")
    version = _text(_required(fill, "version", "paper_fill"), "paper_fill.version")
    if profile != RESEARCH_ZERO_SLIPPAGE_PROFILE:
        raise PaperConfigurationError("no owner-approved canonical paper slippage profile is configured")
    model = _mapping(_required(fill, "slippage_model", "paper_fill"), "paper_fill.slippage_model")
    _only(model, {"type", "bps"}, "paper_fill.slippage_model")
    if _text(_required(model, "type", "paper_fill.slippage_model"), "paper_fill.slippage_model.type") != "fixed_bps":
        raise PaperConfigurationError("unsupported paper slippage model")
    bps = _decimal(_required(model, "bps", "paper_fill.slippage_model"), "paper_fill.slippage_model.bps", non_negative=True)
    if bps != Decimal("0"):
        raise PaperConfigurationError("only the owner-approved RESEARCH_ZERO_SLIPPAGE profile is currently available")
    tolerance = _decimal(_required(fill, "max_execution_tolerance_bps", "paper_fill"), "paper_fill.max_execution_tolerance_bps", positive=True)
    maximum = _decimal(_required(fill, "max_slippage_bps", "paper_fill"), "paper_fill.max_slippage_bps", positive=True)
    policy = PaperFillPolicy(
        slippage_model=FixedBasisPointsSlippage(bps),
        max_execution_tolerance_bps=tolerance,
        max_slippage_bps=maximum,
    )
    identity = CanonicalCodec.fingerprint(
        "sentinelx-paper-execution-profile/v1",
        (
            ("profile", profile), ("version", version), ("model_id", policy.slippage_model.model_id),
            ("max_execution_tolerance_bps", tolerance), ("max_slippage_bps", maximum),
        ),
    )
    return policy, identity


def _research_zero_cost_profile(raw: Mapping[str, object]) -> tuple[tuple[CostSchedule, ...], str]:
    _only(raw, {"profile", "version", "currency"}, "cost_profile")
    profile = _text(_required(raw, "profile", "cost_profile"), "cost_profile.profile")
    version = _text(_required(raw, "version", "cost_profile"), "cost_profile.version")
    currency = _text(_required(raw, "currency", "cost_profile"), "cost_profile.currency")
    if profile != RESEARCH_ZERO_COST_PROFILE:
        raise PaperConfigurationError("no owner-approved canonical paper cost profile is configured")
    if currency != "INR":
        raise PaperConfigurationError("RESEARCH_ZERO_COST/v1 requires cost_profile.currency INR")
    schedule = CostSchedule(
        schedule_id=profile,
        version=version,
        currency=currency,
        effective_from=datetime(1970, 1, 1, tzinfo=timezone.utc),
        effective_to=None,
        component_rules=(),
    )
    identity = CanonicalCodec.fingerprint(
        "sentinelx-paper-cost-profile/v1",
        (("profile", profile), ("version", version), ("currency", currency), ("schedule", schedule.fingerprint)),
    )
    return (schedule,), identity


def _verify_upstream_promotion_artifact(
    artifact_path: Path,
    expected_fingerprint: str | None,
    owner: SubscriptionOwnerKey,
) -> bool:
    """Load and verify upstream UpstreamPromotionEvidenceBundle (ADR §122 OD-W).

    Returns True if evidence is promotable, False if unpromotable.
    Raises PaperConfigurationError on fingerprint mismatch, corruption, or strategy owner mismatch.
    """
    if not artifact_path.is_file():
        raise PaperConfigurationError(f"upstream promotion evidence artifact not found: {artifact_path}")
    import json
    try:
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PaperConfigurationError(f"invalid JSON in upstream promotion evidence artifact: {artifact_path}") from exc

    from engine.paper.promotion_tracking import UpstreamPromotionEvidenceBundle, UPSTREAM_PROMOTION_BUNDLE_SCHEMA_VERSION

    schema = data.get("schema_version")
    if schema != UPSTREAM_PROMOTION_BUNDLE_SCHEMA_VERSION:
        raise PaperConfigurationError(
            f"unsupported upstream promotion evidence schema {schema!r} in {artifact_path}; "
            f"expected {UPSTREAM_PROMOTION_BUNDLE_SCHEMA_VERSION!r}"
        )

    try:
        bundle = UpstreamPromotionEvidenceBundle.from_dict(data)
    except Exception as exc:
        raise PaperConfigurationError(f"malformed upstream promotion bundle in {artifact_path}: {exc}") from exc

    if bundle.strategy_id != owner.strategy_id or bundle.strategy_version != owner.strategy_version:
        raise PaperConfigurationError(
            f"upstream promotion evidence strategy owner mismatch for {owner}: "
            f"bundle belongs to strategy_id={bundle.strategy_id!r}, strategy_version={bundle.strategy_version!r}"
        )

    if expected_fingerprint is not None and bundle.bundle_fingerprint != expected_fingerprint:
        raise PaperConfigurationError(
            f"upstream promotion evidence bundle fingerprint mismatch for {owner}: "
            f"expected {expected_fingerprint!r}, computed {bundle.bundle_fingerprint!r}"
        )

    if bundle.promotion_decision.result_fingerprint != bundle.promotion_decision_fingerprint:
        raise PaperConfigurationError(
            f"bundle promotion_decision_fingerprint mismatch: "
            f"expected {bundle.promotion_decision.result_fingerprint!r}, got {bundle.promotion_decision_fingerprint!r}"
        )

    if bundle.promotion_decision.manifest_fingerprint != bundle.manifest_fingerprint:
        raise PaperConfigurationError(
            f"bundle manifest_fingerprint mismatch: "
            f"expected {bundle.promotion_decision.manifest_fingerprint!r}, got {bundle.manifest_fingerprint!r}"
        )

    return bundle.promotion_decision.promotable


def _canonical_policy_parameters(value: object) -> tuple[tuple[str, object], ...]:
    parameters = _mapping(value, "protective_policy.parameters")

    def freeze(item: object, field: str) -> object:
        if item is None or isinstance(item, (bool, int, str)):
            return item
        if isinstance(item, float):
            raise PaperConfigurationError(f"{field} must not use YAML float values")
        if isinstance(item, Mapping):
            if not all(isinstance(key, str) and key.strip() for key in item):
                raise PaperConfigurationError(f"{field} mapping keys must be non-empty strings")
            return tuple((key, freeze(item[key], f"{field}.{key}")) for key in sorted(item))
        if isinstance(item, list):
            return tuple(freeze(child, f"{field}[{index}]") for index, child in enumerate(item))
        raise PaperConfigurationError(f"{field} contains unsupported parameter value type")

    return tuple((key, freeze(parameters[key], f"protective_policy.parameters.{key}") ) for key in sorted(parameters))


def _parameters_mapping(parameters: tuple[tuple[str, object], ...]) -> Mapping[str, object]:
    def thaw(value: object) -> object:
        if isinstance(value, tuple):
            if all(isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str) for item in value):
                return MappingProxyType({key: thaw(item) for key, item in value})
            return tuple(thaw(item) for item in value)
        return value

    return MappingProxyType({key: thaw(value) for key, value in parameters})


def _strategy_binding(
    path: Path,
    registry: ProtectivePolicyRegistry | None = None,
) -> PaperStrategyBindingConfiguration:
    registry = ProtectivePolicyRegistry() if registry is None else registry
    if not isinstance(registry, ProtectivePolicyRegistry):
        raise TypeError("registry must be a ProtectivePolicyRegistry")
    raw = _yaml(path)
    _only(
        raw,
        {
            "schema_version", "strategy_id", "strategy_version", "activation", "instrument",
            "timeframe", "protective_policy", "upstream_promotion_evidence_fingerprint",
            "upstream_promotion_evidence_path",
        },
        "strategy configuration",
    )
    if _text(_required(raw, "schema_version", "strategy configuration"), "strategy configuration.schema_version") != "paper-strategy-config/v1":
        raise PaperConfigurationError("unsupported strategy configuration schema_version")
    owner = SubscriptionOwnerKey(
        _text(_required(raw, "strategy_id", "strategy configuration"), "strategy_id"),
        _text(_required(raw, "strategy_version", "strategy configuration"), "strategy_version"),
    )
    activation = _text(_required(raw, "activation", "strategy configuration"), "activation")
    if activation not in {"actionable", "observation_only"}:
        raise PaperConfigurationError("activation must be actionable or observation_only")
    instrument = _text(_required(raw, "instrument", "strategy configuration"), "instrument")
    timeframe = _text(_required(raw, "timeframe", "strategy configuration"), "timeframe")
    
    upstream_fingerprint = raw.get("upstream_promotion_evidence_fingerprint")
    if upstream_fingerprint is not None:
        upstream_fingerprint = _text(upstream_fingerprint, "upstream_promotion_evidence_fingerprint")
    
    upstream_path_raw = raw.get("upstream_promotion_evidence_path")
    upstream_path: Path | None = None
    if upstream_path_raw is not None:
        upstream_path = _resolve_path(path.parent, upstream_path_raw, "upstream_promotion_evidence_path")

    declaration = raw.get("protective_policy")
    if activation == "observation_only" and declaration is not None:
        raise PaperConfigurationError("observation_only strategy must not declare an actionable protective_policy")
    policy_key: ProtectivePolicyRegistrationKey | None = None
    policy_parameters: tuple[tuple[str, object], ...] | None = None
    if activation == "actionable":
        if declaration is None:
            raise PaperConfigurationError(
                f"actionable strategy {owner.strategy_id}/{owner.strategy_version} requires an explicitly approved strategy-owned protective policy"
            )
        policy_raw = _mapping(declaration, "protective_policy")
        if "type" in policy_raw:
            declared_type = _text(policy_raw["type"], "protective_policy.type")
            if declared_type not in {"fixed_percent", "trailing_percent"}:
                raise PaperConfigurationError(f"unsupported protective_policy.type: {declared_type!r}")
            raise PaperConfigurationError(
                f"unsupported protective_policy.type: {declared_type!r}; generic protective-policy forms are not supported for production; "
                "an owner-approved strategy-specific protective policy is required"
            )
        _only(policy_raw, {"policy_id", "policy_version", "parameters"}, "protective_policy")
        policy_key = ProtectivePolicyRegistrationKey(
            owner.strategy_id,
            owner.strategy_version,
            _text(_required(policy_raw, "policy_id", "protective_policy"), "protective_policy.policy_id"),
            _text(_required(policy_raw, "policy_version", "protective_policy"), "protective_policy.policy_version"),
        )
        policy_parameters = _canonical_policy_parameters(_required(policy_raw, "parameters", "protective_policy"))
        try:
            protective_policy = registry.resolve(policy_key, _parameters_mapping(policy_parameters))
        except (ProtectivePolicyRegistryError, TypeError) as error:
            raise PaperConfigurationError(str(error)) from error
    else:
        protective_policy = None
    return PaperStrategyBindingConfiguration(
        owner=owner,
        activation=activation,
        instrument=instrument,
        timeframe=timeframe,
        source_path=path,
        protective_policy=protective_policy,
        protective_policy_key=policy_key,
        protective_policy_parameters=policy_parameters,
        upstream_promotion_evidence_fingerprint=upstream_fingerprint,
        upstream_promotion_evidence_path=upstream_path,
    )


def load_paper_configuration(
    path: Path | str,
    *,
    protective_policy_registry: ProtectivePolicyRegistry | None = None,
) -> ResolvedPaperConfiguration:
    """Load one strict paper runtime configuration before component startup."""
    import json
    source_path = Path(path).resolve()
    registry = ProtectivePolicyRegistry() if protective_policy_registry is None else protective_policy_registry
    if not isinstance(registry, ProtectivePolicyRegistry):
        raise TypeError("protective_policy_registry must be a ProtectivePolicyRegistry")
    raw = _yaml(source_path)
    _only(
        raw,
        {
            "schema_version", "environment", "account", "persistence", "canonical_bindings",
            "cost_profile", "promotion_tracking_activated", "calendar_closure_snapshot",
            "calendar_snapshot_path", "promotion_report_destination_dir",
        },
        "paper configuration",
    )
    if _text(_required(raw, "schema_version", "paper configuration"), "paper configuration.schema_version") != "paper-config/v1":
        raise PaperConfigurationError("unsupported paper configuration schema_version")
    if _text(_required(raw, "environment", "paper configuration"), "paper configuration.environment") != "paper":
        raise PaperConfigurationError("paper configuration environment must be paper")

    # Activation timestamp
    tracking_activated: datetime | None = None
    if "promotion_tracking_activated" in raw and raw["promotion_tracking_activated"] is not None:
        val = raw["promotion_tracking_activated"]
        if isinstance(val, datetime):
            tracking_activated = val
        elif isinstance(val, str) and val.strip():
            try:
                tracking_activated = datetime.fromisoformat(val.strip())
            except ValueError as exc:
                raise PaperConfigurationError("invalid promotion_tracking_activated timestamp") from exc
        else:
            raise PaperConfigurationError("promotion_tracking_activated must be an ISO-8601 timestamp or null")
        if tracking_activated.tzinfo is None or tracking_activated.utcoffset() is None:
            raise PaperConfigurationError("promotion_tracking_activated must be timezone-aware")

    # Calendar Snapshot (ADR §122 OD-X)
    calendar_snapshot: Any | None = None
    calendar_snapshot_path: Path | None = None
    if "calendar_snapshot_path" in raw and raw["calendar_snapshot_path"] is not None:
        calendar_snapshot_path = _resolve_path(source_path.parent, raw["calendar_snapshot_path"], "calendar_snapshot_path")
        if not calendar_snapshot_path.is_file():
            raise PaperConfigurationError(f"calendar snapshot artifact not found: {calendar_snapshot_path}")
        try:
            snap_data = json.loads(calendar_snapshot_path.read_text(encoding="utf-8"))
            from engine.market.profile import CalendarClosureSnapshot
            calendar_snapshot = CalendarClosureSnapshot.from_dict(snap_data)
        except Exception as exc:
            raise PaperConfigurationError(f"invalid calendar snapshot at {calendar_snapshot_path}: {exc}") from exc
    elif "calendar_closure_snapshot" in raw and raw["calendar_closure_snapshot"] is not None:
        try:
            from engine.market.profile import CalendarClosureSnapshot
            calendar_snapshot = CalendarClosureSnapshot.from_dict(raw["calendar_closure_snapshot"])
        except Exception as exc:
            raise PaperConfigurationError(f"invalid inline calendar snapshot: {exc}") from exc

    promotion_report_dest: Path | None = None
    if "promotion_report_destination_dir" in raw and raw["promotion_report_destination_dir"] is not None:
        val = _text(raw["promotion_report_destination_dir"], "promotion_report_destination_dir")
        promotion_report_dest = _resolve_path(source_path.parent, val, "promotion_report_destination_dir")

    account_raw = _mapping(_required(raw, "account", "paper configuration"), "account")
    _only(account_raw, {"account_id", "starting_capital", "currency", "monetary_quantum"}, "account")
    account = PaperAccountConfiguration(
        account_id=_text(_required(account_raw, "account_id", "account"), "account.account_id"),
        starting_capital=_decimal(_required(account_raw, "starting_capital", "account"), "account.starting_capital", positive=True),
        currency=_text(_required(account_raw, "currency", "account"), "account.currency"),
        monetary_quantum=_decimal(_required(account_raw, "monetary_quantum", "account"), "account.monetary_quantum", positive=True),
    )
    persistence = _mapping(_required(raw, "persistence", "paper configuration"), "persistence")
    _only(persistence, {"type", "path"}, "persistence")
    if _text(_required(persistence, "type", "persistence"), "persistence.type") != "sqlite":
        raise PaperConfigurationError("paper persistence type must be sqlite")
    database_path = _resolve_path(source_path.parent, _required(persistence, "path", "persistence"), "persistence.path")
    bindings = _mapping(_required(raw, "canonical_bindings", "paper configuration"), "canonical_bindings")
    _only(bindings, {"risk_config_path", "execution_config_path", "strategy_config_paths"}, "canonical_bindings")
    risk_policy = _load_risk_policy(_resolve_path(source_path.parent, _required(bindings, "risk_config_path", "canonical_bindings"), "canonical_bindings.risk_config_path"))
    fill_policy, execution_identity = _load_execution_policy(_resolve_path(source_path.parent, _required(bindings, "execution_config_path", "canonical_bindings"), "canonical_bindings.execution_config_path"))
    paths = _required(bindings, "strategy_config_paths", "canonical_bindings")
    if not isinstance(paths, list) or not paths:
        raise PaperConfigurationError("canonical_bindings.strategy_config_paths must be a non-empty list")
    strategy_configs: dict[SubscriptionOwnerKey, PaperStrategyBindingConfiguration] = {}
    policies: dict[SubscriptionOwnerKey, ProtectivePlanPolicy] = {}
    for index, item in enumerate(paths):
        strategy = _strategy_binding(
            _resolve_path(source_path.parent, item, f"canonical_bindings.strategy_config_paths[{index}]"), registry
        )
        if strategy.owner in strategy_configs:
            raise PaperConfigurationError(f"duplicate strategy configuration for {strategy.owner!r}")

        promotable = True
        if strategy.upstream_promotion_evidence_path is not None:
            promotable = _verify_upstream_promotion_artifact(
                strategy.upstream_promotion_evidence_path,
                strategy.upstream_promotion_evidence_fingerprint,
                strategy.owner,
            )

        strategy_configs[strategy.owner] = replace(strategy, upstream_promotion_evidence_promotable=promotable)
        if strategy.protective_policy is not None:
            policies[strategy.owner] = strategy.protective_policy

    schedules, cost_identity = _research_zero_cost_profile(_mapping(_required(raw, "cost_profile", "paper configuration"), "cost_profile"))
    if account.currency != schedules[0].currency:
        raise PaperConfigurationError(
            "account.currency must match cost_profile.currency before paper runtime startup"
        )
    reasons = ("RESEARCH_ZERO_COST", "RESEARCH_ZERO_SLIPPAGE")
    return ResolvedPaperConfiguration(
        source_path=source_path,
        database_path=database_path,
        account=account,
        risk_policy=risk_policy,
        cost_schedules=schedules,
        paper_fill_policy=fill_policy,
        strategy_bindings=MappingProxyType(dict(strategy_configs)),
        protective_plan_policies=MappingProxyType(dict(policies)),
        cost_profile_identity=cost_identity,
        execution_policy_identity=execution_identity,
        promotion_eligible=False,
        promotion_ineligibility_reasons=reasons,
        promotion_tracking_activated=tracking_activated,
        calendar_snapshot=calendar_snapshot,
        calendar_snapshot_path=calendar_snapshot_path,
        promotion_report_destination_dir=promotion_report_dest,
    )
