"""Exact numeric conversion for authoritative economic values."""

from decimal import Decimal, InvalidOperation


def as_decimal(value: Decimal | int | float | str, field_name: str) -> Decimal:
    """Normalize a finite economic input without Decimal-to-float narrowing."""
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise TypeError(f"{field_name} must be numeric") from error
    if not result.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return result
