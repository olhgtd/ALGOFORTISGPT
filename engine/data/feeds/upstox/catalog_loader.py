"""Upstox Instrument Catalog Loader.

Constructs authoritative InstrumentCatalog and ProviderInstrumentMapper instances
from Upstox instrument master records (BOD snapshot).

Guarantees:
- Upstox instrument_key is the SOLE provider transport token (exchange_token is never stable identity).
- contract_multiplier is strictly mapped from provider 'qty_multiplier' (present, finite, > 0).
- effective_from strictly equals the authoritative snapshot_business_date.
- Entire candidate snapshot is validated upfront; any conflict or invalid record fails the entire snapshot.
- Atomic replacement of LiveInstrumentCatalog instances preserving previous valid state on failure.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence

from engine.data.feeds.provider_mapping import (
    InMemoryProviderInstrumentMapper,
    ProviderInstrumentRef,
)
from engine.options.catalog import InstrumentCatalog, OptionCatalogEntry
from engine.options.live_catalog import LiveInstrumentCatalog
from engine.portfolio.model import InstrumentIdentity, InstrumentSpecification

__all__ = [
    "UpstoxCatalogLoaderError",
    "UpstoxInstrumentCatalogLoader",
]


class UpstoxCatalogLoaderError(ValueError):
    """Raised when Upstox instrument catalog candidate records fail validation."""


def _parse_date(value: Any, field_name: str) -> date:
    """Parse date from date, datetime, ISO string, or timestamp."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise UpstoxCatalogLoaderError(f"Empty date string for field {field_name!r}")
        try:
            return date.fromisoformat(cleaned)
        except ValueError:
            # Try formatting with time component if present
            try:
                return datetime.fromisoformat(cleaned).date()
            except ValueError:
                raise UpstoxCatalogLoaderError(
                    f"Invalid ISO date string {value!r} for field {field_name!r}"
                ) from None
    if isinstance(value, (int, float)):
        # Treat as epoch timestamp (milliseconds or seconds)
        ts = value / 1000.0 if value > 1e11 else float(value)
        try:
            return datetime.fromtimestamp(ts, tz=None).date()
        except Exception:
            raise UpstoxCatalogLoaderError(
                f"Invalid numeric timestamp {value!r} for field {field_name!r}"
            ) from None

    raise UpstoxCatalogLoaderError(
        f"Unsupported date format {type(value).__name__} for field {field_name!r}"
    )


def _parse_positive_decimal(value: Any, field_name: str) -> Decimal:
    """Parse a strictly positive, finite Decimal."""
    if value is None:
        raise UpstoxCatalogLoaderError(f"Missing required numeric field {field_name!r}")
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise UpstoxCatalogLoaderError(
            f"Invalid numeric value {value!r} for field {field_name!r}"
        ) from None

    if not dec.is_finite() or dec <= 0:
        raise UpstoxCatalogLoaderError(
            f"Field {field_name!r} must be finite and positive; got {value!r}"
        )
    return dec


class UpstoxInstrumentCatalogLoader:
    """Loads and validates Upstox instrument master records into canonical catalog and mapper."""

    @staticmethod
    def load_catalog_and_mapper(
        provider_records: Sequence[Mapping[str, Any]],
        snapshot_business_date: date,
    ) -> tuple[LiveInstrumentCatalog, InMemoryProviderInstrumentMapper]:
        """Validate candidate Upstox records and return a new LiveInstrumentCatalog and Mapper.

        Args:
            provider_records: Sequence of Upstox instrument dicts.
            snapshot_business_date: Authoritative business date of the BOD snapshot.

        Returns:
            Tuple of (LiveInstrumentCatalog, InMemoryProviderInstrumentMapper).

        Raises:
            UpstoxCatalogLoaderError: If provider_records is empty or contains invalid/conflicting data.
        """
        if not isinstance(snapshot_business_date, date):
            raise UpstoxCatalogLoaderError("snapshot_business_date must be a datetime.date instance")
        if not provider_records:
            raise UpstoxCatalogLoaderError("provider_records must be a non-empty sequence")

        catalog_entries: list[OptionCatalogEntry] = []
        mappings: list[tuple[ProviderInstrumentRef, InstrumentIdentity]] = []
        seen_identities: set[InstrumentIdentity] = set()
        seen_tokens: set[str] = set()

        for idx, record in enumerate(provider_records):
            if not isinstance(record, (dict, Mapping)):
                raise UpstoxCatalogLoaderError(
                    f"Record at index {idx} must be a dict-like mapping, got {type(record).__name__}"
                )

            # 1. Authority Token: instrument_key
            instrument_key = record.get("instrument_key")
            if not isinstance(instrument_key, str) or not instrument_key.strip():
                raise UpstoxCatalogLoaderError(
                    f"Record at index {idx} missing valid 'instrument_key'"
                )
            clean_instrument_key = instrument_key.strip()
            if clean_instrument_key in seen_tokens:
                raise UpstoxCatalogLoaderError(
                    f"Duplicate ProviderInstrumentRef token in candidate snapshot: {clean_instrument_key}"
                )
            seen_tokens.add(clean_instrument_key)

            # 2. Exchange & Trading Symbol
            exchange = record.get("exchange") or "NSE"
            if not isinstance(exchange, str) or not exchange.strip():
                raise UpstoxCatalogLoaderError(f"Record {clean_instrument_key} missing valid 'exchange'")
            clean_exchange = exchange.strip().upper()

            tradingsymbol = record.get("tradingsymbol") or record.get("trading_symbol") or record.get("symbol")
            if not isinstance(tradingsymbol, str) or not tradingsymbol.strip():
                raise UpstoxCatalogLoaderError(
                    f"Record {clean_instrument_key} missing valid 'tradingsymbol'"
                )
            clean_symbol = tradingsymbol.strip().upper()

            # Construct transport ref (canonical provider token authority)
            ref = ProviderInstrumentRef(
                provider="upstox",
                token=clean_instrument_key,
                exchange=clean_exchange,
            )

            # 3. Determine Segment / Type
            segment_raw = str(
                record.get("segment") or record.get("instrument_type") or ""
            ).strip().upper()

            # Check if this is an option contract
            is_option = segment_raw in {"OPTIONS", "OPT", "OPTIDX", "OPTSTK"} or (
                record.get("strike_price") is not None
                and record.get("instrument_type") in {"CE", "PE"}
            )

            if is_option:
                underlying = (
                    record.get("underlying_symbol")
                    or record.get("asset_symbol")
                    or record.get("underlying_key")
                    or record.get("name")
                )
                if not isinstance(underlying, str) or not underlying.strip():
                    raise UpstoxCatalogLoaderError(
                        f"Option record {clean_instrument_key} missing valid underlying symbol"
                    )
                clean_underlying = underlying.strip().upper()

                raw_expiry = record.get("expiry")
                if raw_expiry is None:
                    raise UpstoxCatalogLoaderError(
                        f"Option record {clean_instrument_key} missing valid 'expiry'"
                    )
                expiry_date = _parse_date(raw_expiry, f"{clean_instrument_key}.expiry")

                raw_strike = record.get("strike_price") if record.get("strike_price") is not None else record.get("strike")
                strike_dec = _parse_positive_decimal(raw_strike, f"{clean_instrument_key}.strike_price")

                raw_opt_type = str(record.get("instrument_type") or "").strip().upper()
                if raw_opt_type not in {"CE", "PE"}:
                    raise UpstoxCatalogLoaderError(
                        f"Option record {clean_instrument_key} invalid instrument_type {raw_opt_type!r}; expected CE or PE"
                    )

                ident = InstrumentIdentity(
                    market=clean_exchange.lower(),
                    instrument=clean_symbol,
                    segment="options",
                    underlying=clean_underlying,
                    expiry=expiry_date,
                    strike=strike_dec,
                    option_type=raw_opt_type,
                )

                # Upstox contract multiplier from qty_multiplier
                raw_qty_mult = record.get("qty_multiplier")
                contract_mult = _parse_positive_decimal(raw_qty_mult, f"{clean_instrument_key}.qty_multiplier")

                # lot_size -> quantity_step
                raw_lot_size = record.get("lot_size")
                quantity_step = _parse_positive_decimal(raw_lot_size, f"{clean_instrument_key}.lot_size")

                # minimum_lot -> minimum_quantity (defaults to lot_size if minimum_lot not distinct)
                raw_min_lot = record.get("minimum_lot") or raw_lot_size
                minimum_quantity = _parse_positive_decimal(raw_min_lot, f"{clean_instrument_key}.minimum_lot")

                # tick_size -> price_increment
                raw_tick_size = record.get("tick_size")
                price_increment = _parse_positive_decimal(raw_tick_size, f"{clean_instrument_key}.tick_size")

                currency = str(record.get("currency") or "INR").strip().upper()

                spec = InstrumentSpecification(
                    identity=ident,
                    effective_from=snapshot_business_date,
                    contract_multiplier=contract_mult,
                    minimum_quantity=minimum_quantity,
                    quantity_step=quantity_step,
                    currency=currency,
                    price_increment=price_increment,
                )

                entry = OptionCatalogEntry(identity=ident, specification=spec)
                catalog_entries.append(entry)

            else:
                # Underlying index or equity
                segment = "equity"
                ident = InstrumentIdentity(
                    market=clean_exchange.lower(),
                    instrument=clean_symbol,
                    segment=segment,
                )

            # Check uniqueness
            if ident in seen_identities:
                raise UpstoxCatalogLoaderError(
                    f"Duplicate InstrumentIdentity in candidate snapshot: {ident}"
                )

            seen_identities.add(ident)
            mappings.append((ref, ident))

        # Atomic construction
        mapper = InMemoryProviderInstrumentMapper(mappings)
        catalog = LiveInstrumentCatalog(catalog_entries)
        return catalog, mapper

    @classmethod
    def update_live_catalog_and_mapper(
        cls,
        live_catalog: LiveInstrumentCatalog,
        current_mapper: InMemoryProviderInstrumentMapper | None,
        provider_records: Sequence[Mapping[str, Any]],
        snapshot_business_date: date,
    ) -> InMemoryProviderInstrumentMapper:
        """Atomically validate candidate records and update an existing LiveInstrumentCatalog.

        If validation fails, live_catalog remains completely unchanged.

        Returns:
            A new InMemoryProviderInstrumentMapper representing the updated snapshot.
        """
        if not isinstance(live_catalog, LiveInstrumentCatalog):
            raise TypeError("live_catalog must be an instance of LiveInstrumentCatalog")

        new_catalog, new_mapper = cls.load_catalog_and_mapper(
            provider_records, snapshot_business_date
        )

        # Atomically replace snapshot entries in the existing catalog
        live_catalog.replace_snapshot(new_catalog.all_entries)
        return new_mapper
