"""Side-effect-free conformance checks for production-shaped read-only brokers."""

_REQUIRED_METHODS = ("capabilities", "profile", "orders", "trades", "positions", "funds", "health")
_REQUIRED_CAPABILITIES = frozenset({"profile", "orders", "trades", "positions", "funds", "health"})
_MUTATION_METHODS = (
    "place", "place_order", "submit", "submit_order", "modify", "modify_order",
    "cancel", "cancel_order", "create_gtt", "modify_gtt", "cancel_gtt",
)


class ReadOnlyBrokerConformanceError(RuntimeError):
    pass


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReadOnlyBrokerConformanceError(f"{field} must be a non-empty string")
    return value.strip()


def assert_read_only_broker_conformance(adapter: object, *, expected_broker: str) -> None:
    broker = _text(expected_broker, "expected_broker").upper()
    adapter_id = _text(getattr(adapter, "adapter_id", None), "adapter_id")

    for name in _REQUIRED_METHODS:
        if not callable(getattr(adapter, name, None)):
            raise ReadOnlyBrokerConformanceError(f"adapter missing required read-only method: {name}")

    for name in _MUTATION_METHODS:
        if callable(getattr(adapter, name, None)):
            raise ReadOnlyBrokerConformanceError(
                f"read-only adapter exposes forbidden mutation method: {name}"
            )

    capabilities = adapter.capabilities()
    if not isinstance(capabilities, frozenset):
        raise ReadOnlyBrokerConformanceError("adapter capabilities must be a frozenset")
    missing = _REQUIRED_CAPABILITIES - capabilities
    if missing:
        raise ReadOnlyBrokerConformanceError(f"adapter missing read-only capabilities: {sorted(missing)}")
    if any(name in capabilities for name in _MUTATION_METHODS):
        raise ReadOnlyBrokerConformanceError("adapter capabilities advertise mutation authority")

    profile = adapter.profile()
    profile_id = _text(getattr(profile, "profile_id", None), "profile.profile_id").upper()
    if broker not in profile_id and broker not in adapter_id.upper():
        raise ReadOnlyBrokerConformanceError(
            f"broker identity mismatch: expected {broker}, got {profile_id}"
        )


__all__ = ["ReadOnlyBrokerConformanceError", "assert_read_only_broker_conformance"]
