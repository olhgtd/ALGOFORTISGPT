"""AlgoFortis V1 — Data Sovereignty & Storage Authority Enforcer
Implements ADR-14, ADR-32.
Strict classification between Server-Authoritative and Local-Only storage domains.
Guarantees that broker secrets, proprietary strategy source code, orders, and
positions NEVER leave the local user machine.
"""
import enum
from typing import Dict, Any, List, Set

class StorageAuthority(str, enum.Enum):
    LOCAL_ONLY = "LOCAL_ONLY"
    SERVER_AUTHORITATIVE = "SERVER_AUTHORITATIVE"


DATA_AUTHORITY_MATRIX: Dict[str, StorageAuthority] = {
    # Server-Authoritative Categories
    "account_identity": StorageAuthority.SERVER_AUTHORITATIVE,
    "device_public_keys": StorageAuthority.SERVER_AUTHORITATIVE,
    "webauthn_public_credentials": StorageAuthority.SERVER_AUTHORITATIVE,
    "session_state": StorageAuthority.SERVER_AUTHORITATIVE,
    "entitlement_leases": StorageAuthority.SERVER_AUTHORITATIVE,
    "user_preferences": StorageAuthority.SERVER_AUTHORITATIVE,

    # Strictly Local-Only Categories
    "broker_api_secrets": StorageAuthority.LOCAL_ONLY,
    "broker_passwords_pins": StorageAuthority.LOCAL_ONLY,
    "strategy_source_code": StorageAuthority.LOCAL_ONLY,
    "strategy_parameters": StorageAuthority.LOCAL_ONLY,
    "live_positions": StorageAuthority.LOCAL_ONLY,
    "active_orders": StorageAuthority.LOCAL_ONLY,
    "execution_ledgers": StorageAuthority.LOCAL_ONLY,
    "device_private_keys": StorageAuthority.LOCAL_ONLY,
    "device_dpapi_blobs": StorageAuthority.LOCAL_ONLY,
    "raw_tick_datasets": StorageAuthority.LOCAL_ONLY,
}


def assert_can_sync_to_cloud(category: str) -> None:
    """Validate that a data category is permitted to synchronize to central cloud services.
    Fails closed if category is local-only or unknown."""
    authority = DATA_AUTHORITY_MATRIX.get(category)
    if authority != StorageAuthority.SERVER_AUTHORITATIVE:
        raise PermissionError(
            f"DATA SOVEREIGNTY VIOLATION: Category '{category}' is classified as "
            f"{authority or 'UNKNOWN'} and must NEVER leave the local device."
        )
