"""Research-only options cost envelope from effective-dated terms."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from engine.data.instruments import InstrumentTerms
from .contracts import finite


class OptionsError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OptionModel:
    version: str
    daily_theta: Decimal
    iv_shift: Decimal
    gamma_impact: Decimal
    spread: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or "@" not in self.version:
            raise OptionsError("versioned option model required")
        for field in ("daily_theta", "iv_shift", "gamma_impact", "spread"):
            finite(getattr(self, field), field)


@dataclass(frozen=True, slots=True)
class OptionFill:
    quantity: Decimal
    premium: Decimal
    total_cost: Decimal
    promotion_eligible: bool = False


def price_option_fill(terms: InstrumentTerms, as_of: date, observed_premium: Decimal,
                      lots: int, model: OptionModel) -> OptionFill:
    if not isinstance(terms, InstrumentTerms) or terms.segment != "options" or not isinstance(as_of, date) or not isinstance(model, OptionModel):
        raise OptionsError("effective-dated option terms and model required")
    if as_of < terms.effective_from or (terms.effective_to is not None and as_of > terms.effective_to) or as_of > terms.expiry:
        raise OptionsError("terms expired or not effective")
    if isinstance(lots, bool) or not isinstance(lots, int) or lots <= 0:
        raise OptionsError("lots must be positive integer")
    finite(observed_premium, "observed_premium", positive=True)
    quantity = terms.lot_size * lots
    # All costs are explicitly supplied research assumptions; observed premium
    # is required so a model cannot manufacture an option chain quote.
    premium = observed_premium + model.spread / 2 + model.iv_shift + model.gamma_impact + model.daily_theta
    tick = terms.tick_size
    premium = (premium / tick).to_integral_value(rounding="ROUND_CEILING") * tick
    return OptionFill(quantity, premium, quantity * premium)
