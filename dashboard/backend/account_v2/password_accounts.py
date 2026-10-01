"""Canonical password account primitives for the V1 entry-gate reunion.

This module deliberately reuses the existing security-store transaction,
password hashing, identity reconstruction, activation issuance, and service
entitlement contracts. It does not create a second account database.
"""
from __future__ import annotations

from datetime import datetime, timezone

from dashboard.backend.domain import (
    AccountAccessStatus,
    ActivationStatus,
    Lifecycle,
    Role,
    compute_service_expiry,
)
from dashboard.backend.identity import persisted_identity
from dashboard.backend.security_store import (
    SQLiteSecurityStore,
    SecurityStoreError,
    hash_password,
    verify_password,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_legacy_owner_activation(store: SQLiteSecurityStore) -> int:
    """Normalize legacy Owner account identity into current canonical values.

    Historical local-private builds could persist ``ACTIVATED`` even though
    current V2 identity/session contracts admit ``REDEEMED``. Some Owner rows
    also predate a durable public identifier. Because AlgoFortis has exactly
    one Owner, the canonical Owner identifier is ``OWNER-001``.

    The migration is narrow, idempotent, and never changes User rows.
    """
    with store._transaction() as cur:
        result = cur.execute(
            """UPDATE users
               SET activation_status = CASE
                       WHEN activation_status = 'ACTIVATED' THEN 'REDEEMED'
                       ELSE activation_status
                   END,
                   sx_id = CASE
                       WHEN sx_id IS NULL OR TRIM(sx_id) = '' THEN 'OWNER-001'
                       ELSE sx_id
                   END
               WHERE role = 'OWNER'
                 AND (
                     activation_status = 'ACTIVATED'
                     OR sx_id IS NULL
                     OR TRIM(sx_id) = ''
                 )"""
        )
        return int(result.rowcount or 0)


class PasswordAccountAuthority:
    """Role-neutral password activation and verification over one security store."""

    def __init__(self, store: SQLiteSecurityStore) -> None:
        self._store = store

    def activate_user_password(
        self,
        *,
        identifier: str,
        activation_code: str,
        email: str,
        password: str,
        now: datetime | None = None,
    ):
        """Atomically activate one invited User and bind a password.

        Validation and every mutation occur under one ``BEGIN IMMEDIATE``
        transaction so a failure cannot leave a half-active account.
        """
        clean_identifier = identifier.strip().upper()
        clean_email = email.strip().lower()
        if not clean_identifier or not clean_email or "@" not in clean_email:
            raise SecurityStoreError("Activation unavailable")
        if not activation_code.strip():
            raise SecurityStoreError("Activation unavailable")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long")

        now = now or _utc_now()
        with self._store._transaction() as cur:
            rows = cur.execute(
                "SELECT * FROM users WHERE UPPER(TRIM(sx_id)) = ?",
                (clean_identifier,),
            ).fetchall()
            if len(rows) != 1:
                raise SecurityStoreError("Activation unavailable")
            user = rows[0]
            if user["role"] != "USER":
                raise SecurityStoreError("Activation unavailable")
            authoritative_email = (user["bound_email"] or "").strip().lower()
            if not authoritative_email or authoritative_email != clean_email:
                raise SecurityStoreError("Activation unavailable")

            issuance = self._store._validate_activation(cur, user, activation_code, now)
            pw_hash, pw_salt = hash_password(password)
            service_term = user["service_term_type"] or "3_MONTHS"
            service_expires = compute_service_expiry(
                now,
                service_term,
                user["custom_term_value"],
                user["custom_term_unit"],
            )
            now_iso = now.isoformat()

            updated = cur.execute(
                """UPDATE users
                   SET account_status = 'ACTIVE',
                       activation_status = 'REDEEMED',
                       service_status = 'ACTIVE',
                       service_started_at = ?,
                       service_expires_at = ?,
                       password_hash = ?,
                       password_salt = ?,
                       password_updated_at_utc = ?
                   WHERE user_id = ?
                     AND role = 'USER'
                     AND account_status = 'PENDING'
                     AND activation_status = 'INVITED'
                     AND service_started_at IS NULL""",
                (
                    now_iso,
                    service_expires.isoformat() if service_expires else None,
                    pw_hash,
                    pw_salt,
                    now_iso,
                    user["user_id"],
                ),
            )
            if updated.rowcount != 1:
                raise SecurityStoreError("Activation unavailable")

            redeemed = cur.execute(
                """UPDATE activation_issuances
                   SET status = 'REDEEMED', redeemed_at_utc = ?
                   WHERE issuance_id = ?
                     AND status = 'INVITED'
                     AND redeemed_at_utc IS NULL
                     AND revoked_at_utc IS NULL""",
                (now_iso, issuance["issuance_id"]),
            )
            if redeemed.rowcount != 1:
                raise SecurityStoreError("Activation unavailable")

        return persisted_identity(self._store.get_user(user["user_id"]))

    def verify_identity_password(
        self,
        *,
        identifier: str,
        password: str,
        now: datetime | None = None,
    ):
        """Verify Owner or User credentials without deciding workspace routing."""
        clean_identifier = identifier.strip()
        if not clean_identifier or not password:
            return None
        row = self._store.find_user_by_identifier(clean_identifier)
        if row is None:
            return None
        if not row["password_hash"] or not row["password_salt"]:
            return None
        if not verify_password(password, row["password_hash"], row["password_salt"]):
            return None
        if row["lifecycle"] != Lifecycle.ACTIVE.value:
            return None
        if row["account_status"] != AccountAccessStatus.ACTIVE.value:
            return None
        if row["activation_status"] != ActivationStatus.REDEEMED.value:
            return None
        try:
            identity = persisted_identity(row)
        except (ValueError, TypeError, KeyError):
            return None
        if identity.role not in {Role.OWNER, Role.USER}:
            return None
        return identity
