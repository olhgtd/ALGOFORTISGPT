"""Deterministic option contract selector — pure selection core.

Converts a semantic entry intent plus authoritative option catalog
evidence into a concrete ResolvedOptionEntry.

NO order creation.
NO risk sizing.
NO broker execution.

Frozen semantics:
  SignalIntent BUY  -> select CE
  SignalIntent SELL -> select PE
  SignalIntent HOLD -> no selection (returns rejection)
  SignalIntent EXIT -> selector bypass (returns rejection)

The original SignalIntent is NEVER mutated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from engine.core.numeric import as_decimal
from engine.options.catalog import InstrumentCatalog, OptionCatalogEntry
from engine.options.policy import ExpiryPolicy, OptionSelectionPolicy, StrikeMode, StrikePolicy
from engine.portfolio.model import InstrumentIdentity, InstrumentSpecification
from engine.orchestration.signal_intake import SignalIntent


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OptionSelectionEvidence:
    """Immutable evidence of how a selection was made."""

    selected_identity: InstrumentIdentity
    selected_specification: InstrumentSpecification
    option_type_selected: Literal["CE", "PE"]
    selected_strike: Decimal
    selected_expiry: date
    underlying_price_at_selection: Decimal
    atm_strike: Decimal | None
    policy_strategy_id: str
    policy_strategy_version: str
    expiry_mode: str
    min_dte_days: int
    strike_mode: str
    offset_steps: int
    catalog_entry_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.selected_identity, InstrumentIdentity):
            raise TypeError("selected_identity must be an InstrumentIdentity")
        if not isinstance(self.selected_specification, InstrumentSpecification):
            raise TypeError("selected_specification must be an InstrumentSpecification")
        if self.option_type_selected not in ("CE", "PE"):
            raise ValueError("option_type_selected must be CE or PE")
        if self.selected_specification.identity != self.selected_identity:
            raise ValueError("specification identity must match selected identity")
        for name in ("selected_strike", "underlying_price_at_selection"):
            val = as_decimal(getattr(self, name), name)
            if val <= 0:
                raise ValueError(f"{name} must be positive")
        if self.atm_strike is not None:
            atm = as_decimal(self.atm_strike, "atm_strike")
            if atm <= 0:
                raise ValueError("atm_strike must be positive")
        if not isinstance(self.selected_expiry, date):
            raise TypeError("selected_expiry must be a date")
        if not isinstance(self.catalog_entry_count, int):
            raise TypeError("catalog_entry_count must be an int")
        if self.catalog_entry_count < 0:
            raise ValueError("catalog_entry_count must be >= 0")


@dataclass(frozen=True)
class OptionSelectionRejection:
    """Structured rejection reason when selection fails."""

    reason: str
    strategy_id: str
    strategy_version: str
    action: str
    underlying: str | None = None


@dataclass(frozen=True)
class ResolvedOptionEntry:
    """The output of successful option selection.

    Contains provenance (original source_intent), selected contract identity,
    specification, and selection evidence.

    Does NOT contain:
      - executable order side
      - order_type
      - limit price
      - stop price
      - execution quantity
      - broker token

    Those belong to later execution slices.
    """

    source_intent: SignalIntent
    selected_identity: InstrumentIdentity
    selected_specification: InstrumentSpecification
    selection_evidence: OptionSelectionEvidence

    def __post_init__(self) -> None:
        if not isinstance(self.source_intent, SignalIntent):
            raise TypeError("source_intent must be a SignalIntent")
        if not isinstance(self.selected_identity, InstrumentIdentity):
            raise TypeError("selected_identity must be an InstrumentIdentity")
        if not isinstance(self.selected_specification, InstrumentSpecification):
            raise TypeError("selected_specification must be an InstrumentSpecification")
        if not isinstance(self.selection_evidence, OptionSelectionEvidence):
            raise TypeError("selection_evidence must be an OptionSelectionEvidence")
        if self.selected_specification.identity != self.selected_identity:
            raise ValueError("specification identity must match selected identity")
        if self.selection_evidence.selected_identity != self.selected_identity:
            raise ValueError("evidence identity must match selected identity")
        if self.selection_evidence.selected_specification != self.selected_specification:
            raise ValueError("evidence specification must match selected specification")


# ---------------------------------------------------------------------------
# Selector
# ---------------------------------------------------------------------------


class OptionSelector:
    """Deterministic option contract selector.

    Pure selection only.  No orders, no risk, no broker.
    """

    def __init__(self, catalog: InstrumentCatalog) -> None:
        if not isinstance(catalog, InstrumentCatalog):
            raise TypeError("catalog must be an InstrumentCatalog")
        self._catalog = catalog

    @property
    def catalog(self) -> InstrumentCatalog:
        return self._catalog

    def select(
        self,
        *,
        intent: SignalIntent,
        policy: OptionSelectionPolicy,
        underlying_price: Decimal | int | float | str,
        selection_timestamp: datetime,
    ) -> ResolvedOptionEntry | OptionSelectionRejection:
        """Select one concrete option contract from the catalog.

        Returns ResolvedOptionEntry on success or OptionSelectionRejection
        on failure.  Never returns None.
        """
        # --- Validate inputs ---
        if not isinstance(intent, SignalIntent):
            return OptionSelectionRejection(
                reason="invalid_intent", strategy_id="", strategy_version="", action="UNKNOWN",
            )
        if not isinstance(policy, OptionSelectionPolicy):
            return OptionSelectionRejection(
                reason="missing_option_policy",
                strategy_id=intent.strategy_id if isinstance(intent, SignalIntent) else "",
                strategy_version=intent.strategy_version if isinstance(intent, SignalIntent) else "",
                action=intent.action if isinstance(intent, SignalIntent) else "UNKNOWN",
            )
        try:
            price = as_decimal(underlying_price, "underlying_price")
        except (TypeError, ValueError):
            return OptionSelectionRejection(
                reason="invalid_underlying_price",
                strategy_id=policy.strategy_id,
                strategy_version=policy.strategy_version,
                action=intent.action,
            )
        if price <= 0:
            return OptionSelectionRejection(
                reason="non_positive_underlying_price",
                strategy_id=policy.strategy_id,
                strategy_version=policy.strategy_version,
                action=intent.action,
            )
        if not isinstance(selection_timestamp, datetime):
            return OptionSelectionRejection(
                reason="invalid_selection_timestamp",
                strategy_id=policy.strategy_id,
                strategy_version=policy.strategy_version,
                action=intent.action,
            )
        if selection_timestamp.tzinfo is None or selection_timestamp.utcoffset() is None:
            return OptionSelectionRejection(
                reason="selection_timestamp_not_timezone_aware",
                strategy_id=policy.strategy_id,
                strategy_version=policy.strategy_version,
                action=intent.action,
            )

        # --- Action routing ---
        if intent.action == "HOLD":
            return OptionSelectionRejection(
                reason="hold_bypass", strategy_id=policy.strategy_id,
                strategy_version=policy.strategy_version, action="HOLD",
            )
        if intent.action == "EXIT":
            return OptionSelectionRejection(
                reason="exit_bypass", strategy_id=policy.strategy_id,
                strategy_version=policy.strategy_version, action="EXIT",
            )

        # Determine target option type from semantic intent
        if intent.action == "BUY":
            target_option_type = "CE"
        elif intent.action == "SELL":
            target_option_type = "PE"
        else:
            return OptionSelectionRejection(
                reason=f"unsupported_intent_action_{intent.action}",
                strategy_id=policy.strategy_id, strategy_version=policy.strategy_version,
                action=intent.action,
            )

        # --- Query catalog ---
        selection_date = selection_timestamp.date()
        all_entries = self._catalog.list_entries(
            underlying=intent.symbol.upper(), as_of=selection_date,
        )

        if not all_entries:
            return OptionSelectionRejection(
                reason="no_matching_underlying",
                strategy_id=policy.strategy_id, strategy_version=policy.strategy_version,
                action=intent.action, underlying=intent.symbol,
            )

        # Filter by target option type
        type_entries = tuple(
            e for e in all_entries if e.identity.option_type == target_option_type
        )
        if not type_entries:
            return OptionSelectionRejection(
                reason=f"no_matching_{target_option_type}",
                strategy_id=policy.strategy_id, strategy_version=policy.strategy_version,
                action=intent.action, underlying=intent.symbol,
            )

        # --- Expiry selection (NEAREST_LISTED) ---
        expiry_result = self._select_nearest_listed_expiry(
            type_entries, policy.expiry, selection_date,
            policy.strategy_id, policy.strategy_version, intent.action, intent.symbol,
        )
        if isinstance(expiry_result, OptionSelectionRejection):
            return expiry_result

        expiry_entries, selected_expiry, dte = expiry_result

        # --- Strike selection ---
        strike_result = self._select_strike(
            expiry_entries, policy.strike, price, target_option_type,
        )
        if strike_result is None:
            return OptionSelectionRejection(
                reason="no_eligible_strikes",
                strategy_id=policy.strategy_id, strategy_version=policy.strategy_version,
                action=intent.action, underlying=intent.symbol,
            )

        selected_entry, atm_strike = strike_result

        # --- Build evidence ---
        evidence = OptionSelectionEvidence(
            selected_identity=selected_entry.identity,
            selected_specification=selected_entry.specification,
            option_type_selected=target_option_type,
            selected_strike=selected_entry.identity.strike,
            selected_expiry=selected_expiry,
            underlying_price_at_selection=price,
            atm_strike=atm_strike,
            policy_strategy_id=policy.strategy_id,
            policy_strategy_version=policy.strategy_version,
            expiry_mode=policy.expiry.mode,
            min_dte_days=policy.expiry.min_dte_days,
            strike_mode=policy.strike.mode.value,
            offset_steps=policy.strike.offset_steps,
            catalog_entry_count=len(all_entries),
        )

        return ResolvedOptionEntry(
            source_intent=intent,
            selected_identity=selected_entry.identity,
            selected_specification=selected_entry.specification,
            selection_evidence=evidence,
        )

    # ------------------------------------------------------------------
    # Internal methods
    # ------------------------------------------------------------------

    @staticmethod
    def _select_nearest_listed_expiry(
        entries: tuple[OptionCatalogEntry, ...],
        expiry_policy: ExpiryPolicy,
        selection_date: date,
        strategy_id: str,
        strategy_version: str,
        action: str,
        underlying: str,
    ) -> tuple[tuple[OptionCatalogEntry, ...], date, int] | OptionSelectionRejection:
        """Filter entries to those with the nearest eligible listed expiry.

        Returns (entries_for_expiry, selected_expiry, dte) or a rejection.
        """
        # Collect unique expiries from entries
        unique_expiries: dict[date, list[OptionCatalogEntry]] = {}
        for entry in entries:
            exp = entry.identity.expiry
            if exp not in unique_expiries:
                unique_expiries[exp] = []
            unique_expiries[exp].append(entry)

        if not unique_expiries:
            return OptionSelectionRejection(
                reason="no_eligible_expiry",
                strategy_id=strategy_id, strategy_version=strategy_version,
                action=action, underlying=underlying,
            )

        # Filter by DTE and expiry-day policy
        eligible: list[tuple[date, int]] = []  # (expiry, dte)
        for exp in sorted(unique_expiries.keys()):
            dte = (exp - selection_date).days
            if dte < expiry_policy.min_dte_days:
                continue  # Too soon
            # Check expiry-day policy
            if not expiry_policy.allow_expiry_day and dte == 0:
                continue  # Same-day expiry not allowed
            # Expired contracts must not participate
            if dte < 0:
                continue
            eligible.append((exp, dte))

        if not eligible:
            return OptionSelectionRejection(
                reason="no_eligible_expiry_meets_dte_or_day_policy",
                strategy_id=strategy_id, strategy_version=strategy_version,
                action=action, underlying=underlying,
            )

        # NEAREST_LISTED: pick minimum DTE (nearest)
        nearest_exp, nearest_dte = min(eligible, key=lambda x: x[1])

        # Check for duplicate exact expiry (ambiguity guard)
        if nearest_dte == 0:
            # Same-day is allowed; no ambiguity since same date
            pass

        return tuple(unique_expiries[nearest_exp]), nearest_exp, nearest_dte

    @staticmethod
    def _select_strike(
        entries: tuple[OptionCatalogEntry, ...],
        strike_policy: StrikePolicy,
        underlying_price: Decimal,
        target_option_type: str,
    ) -> tuple[OptionCatalogEntry, Decimal | None] | None:
        """Select the correct strike from eligible entries.

        Returns (selected_entry, atm_strike) or None (caller wraps in rejection).
        Strike ladder comes only from actual catalog strikes.
        """
        # Collect unique sorted strikes for this expiry+type
        strikes_sorted: list[tuple[Decimal, OptionCatalogEntry]] = []
        seen_strikes: set[Decimal] = set()
        for entry in entries:
            s = entry.identity.strike
            if s not in seen_strikes:
                seen_strikes.add(s)
                strikes_sorted.append((s, entry))

        if not strikes_sorted:
            return None  # Caller wraps in rejection

        # Sort by strike value (deterministic — no dict order dependence)
        strikes_sorted.sort(key=lambda x: x[0])

        # Find ATM: minimum absolute difference from authoritative underlying price
        atm_strike: Decimal | None = None
        atm_diff: Decimal | None = None
        for strike_val, _ in strikes_sorted:
            diff = abs(strike_val - underlying_price)
            if atm_diff is None or diff < atm_diff:
                atm_diff = diff
                atm_strike = strike_val
            elif diff == atm_diff:
                # Equal-distance ATM tie: choose lower numeric strike
                if strike_val < atm_strike:  # type: ignore[operator]
                    atm_strike = strike_val

        if atm_strike is None:
            return None  # Caller wraps in rejection

        # Find ATM index in sorted list
        atm_index: int | None = None
        for i, (s, _) in enumerate(strikes_sorted):
            if s == atm_strike:
                atm_index = i
                break

        if atm_index is None:
            return None  # Caller wraps in rejection

        # Compute target index based on mode + direction
        if strike_policy.mode is StrikeMode.ATM:
            target_index = atm_index
        elif strike_policy.mode is StrikeMode.ITM:
            if target_option_type == "CE":
                # CE ITM: move downward from ATM (lower strikes = more ITM for calls)
                target_index = atm_index - strike_policy.offset_steps
            else:
                # PE ITM: move upward from ATM (higher strikes = more ITM for puts)
                target_index = atm_index + strike_policy.offset_steps
        elif strike_policy.mode is StrikeMode.OTM:
            if target_option_type == "CE":
                # CE OTM: move upward from ATM (higher strikes = OTM for calls)
                target_index = atm_index + strike_policy.offset_steps
            else:
                # PE OTM: move downward from ATM (lower strikes = OTM for puts)
                target_index = atm_index - strike_policy.offset_steps
        else:
            return None  # Caller wraps in rejection

        # Check bounds — use a sentinel string the caller can detect
        if target_index < 0 or target_index >= len(strikes_sorted):
            return None  # Caller wraps in OptionSelectionRejection

        selected_strike, selected_entry = strikes_sorted[target_index]
        return selected_entry, atm_strike
