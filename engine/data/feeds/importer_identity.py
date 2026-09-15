"""Canonical identity contracts for the historical-data importer."""

from dataclasses import asdict, dataclass

from engine.data.feeds.path_safety import PathSafetyError, require_safe_component


INDIAN_MARKETS = {"india", "indian", "nse", "bse", "mcx"}
ALLOWED_SEGMENTS = {"index", "spot", "futures", "options", "commodity", "crypto"}
ALLOWED_OPTION_TYPES = {"CE", "PE"}


class IdentityResolutionError(ValueError):
    """Raised when importer identity metadata is missing or contradictory."""


def resolve_source_timezone(market: str, source_timezone: str | None) -> str:
    """Resolve the approved Indian-market timezone or require a supplied global timezone."""
    if market.casefold() in INDIAN_MARKETS:
        if source_timezone and source_timezone != "Asia/Kolkata":
            raise IdentityResolutionError(
                "Indian market metadata must use source_timezone='Asia/Kolkata'."
            )
        return "Asia/Kolkata"
    if not source_timezone:
        raise IdentityResolutionError(
            "Non-Indian/global market data requires an explicit source_timezone."
        )
    return source_timezone


@dataclass(frozen=True)
class CanonicalIdentity:
    """Validated common and contract-specific identity used for importer routing."""

    market: str
    instrument: str
    segment: str
    timeframe: str
    source_timezone: str
    underlying: str | None = None
    expiry: str | None = None
    strike: str | None = None
    option_type: str | None = None

    def __post_init__(self) -> None:
        if not all((self.market, self.instrument, self.segment, self.timeframe, self.source_timezone)):
            raise IdentityResolutionError("Identity requires market, instrument, segment, timeframe, and source_timezone.")
        if self.segment not in ALLOWED_SEGMENTS:
            raise IdentityResolutionError(f"Unsupported segment: {self.segment!r}.")
        # These fields participate directly in the frozen canonical storage
        # layout.  Reject malformed identity evidence; never sanitize it into
        # another authoritative identity.
        try:
            for field_name in ("market", "instrument", "segment", "timeframe"):
                require_safe_component(getattr(self, field_name), field_name)
            for field_name in ("underlying", "expiry", "strike", "option_type"):
                value = getattr(self, field_name)
                if value is not None:
                    require_safe_component(value, field_name)
        except PathSafetyError as error:
            raise IdentityResolutionError(str(error)) from error
        if self.segment == "futures" and not self.expiry:
            raise IdentityResolutionError("Futures identity requires expiry.")
        if self.segment == "options":
            if not all((self.underlying, self.expiry, self.strike, self.option_type)):
                raise IdentityResolutionError(
                    "Options identity requires underlying, expiry, strike, and option_type."
                )
            if self.option_type not in ALLOWED_OPTION_TYPES:
                raise IdentityResolutionError("Options option_type must be 'CE' or 'PE'.")

    def as_dict(self) -> dict[str, str | None]:
        """Return a manifest-safe representation of the detected identity."""
        return asdict(self)
