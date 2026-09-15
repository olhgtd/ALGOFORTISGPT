ALLOWED_METHODS = {"expiry", "volume", "open_interest"}
TRIGGER_FIELDS = {
    "expiry": "expiry_trigger",
    "volume": "volume_trigger",
    "open_interest": "open_interest_trigger",
}


def validate_rollover_config(rollover: dict) -> None:
    """Validate the approved per-strategy futures-rollover framework."""
    if rollover.get("missing_data_policy", "error") != "error":
        raise ValueError("Rollover missing_data_policy must be 'error'.")

    if not rollover.get("enabled", False):
        return

    method = rollover.get("method")
    if method not in ALLOWED_METHODS:
        raise ValueError(
            "Enabled rollover method must be one of: expiry, volume, open_interest."
        )

    trigger_field = TRIGGER_FIELDS[method]
    if rollover.get(trigger_field) is None:
        raise ValueError(
            f"Enabled rollover method {method!r} requires {trigger_field!r}."
        )
