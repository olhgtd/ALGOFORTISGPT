"""Optional HTTPS roaming password identity client for cross-PC AlgoFortis login.

The desktop remains fully fail-closed when no central account authority URL is
configured. Credentials are posted only to the configured HTTPS AlgoFortis
account authority and are never stored by this adapter.
"""
from __future__ import annotations

from datetime import datetime
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, ProxyHandler

from dashboard.backend.domain import (
    AccountAccessStatus,
    ActivationStatus,
    Lifecycle,
    Role,
    ServiceEntitlementStatus,
    UserIdentity,
)
from dashboard.backend.security import SecurityError
from .repository import AccountAuthorityUnavailable


class RemoteAccountAccessUnavailable(PermissionError):
    """Credentials resolved, but the central account cannot enter a workspace."""


class HttpRoamingIdentity:
    """Authenticate against one server-authoritative AlgoFortis account plane."""

    configured = True

    def __init__(self, base_url: str, *, timeout_seconds: float = 8.0) -> None:
        clean = base_url.strip().rstrip("/")
        parsed = urlparse(clean)
        loopback = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
            raise ValueError("central account authority must use HTTPS")
        if not parsed.hostname:
            raise ValueError("central account authority host is required")
        self._base_url = clean
        self._timeout = float(timeout_seconds)
        self._opener = build_opener(ProxyHandler({}))

    @property
    def base_url(self) -> str:
        return self._base_url

    def verify(self, assertion: dict) -> UserIdentity:
        raise SecurityError("Assertion-based roaming verification is not configured on this adapter")

    def _request_json(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, object] | None = None,
        token: str | None = None,
    ) -> dict[str, object]:
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {"accept": "application/json"}
        if body is not None:
            headers["content-type"] = "application/json"
        if token:
            headers["authorization"] = f"Bearer {token}"
        request = Request(self._base_url + path, data=body, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            if exc.code == 401:
                raise LookupError("remote credentials rejected") from None
            if exc.code == 403:
                raise RemoteAccountAccessUnavailable("remote account access unavailable") from None
            raise AccountAuthorityUnavailable("central account authority unavailable") from None
        except (URLError, TimeoutError, OSError):
            raise AccountAuthorityUnavailable("central account authority unavailable") from None
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise AccountAuthorityUnavailable("central account authority response is invalid") from None
        if not isinstance(value, dict):
            raise AccountAuthorityUnavailable("central account authority response is invalid")
        return value

    @staticmethod
    def _parse_time(value: object) -> datetime | None:
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            raise AccountAuthorityUnavailable("central identity time is invalid")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise AccountAuthorityUnavailable("central identity time is invalid") from None
        if parsed.tzinfo is None:
            raise AccountAuthorityUnavailable("central identity time is not timezone-aware")
        return parsed

    @classmethod
    def _identity_from_profile(cls, profile: dict[str, object]) -> UserIdentity:
        try:
            from uuid import UUID
            return UserIdentity(
                user_id=UUID(str(profile["user_id"])),
                role=Role(str(profile["role"])),
                lifecycle=Lifecycle(str(profile["lifecycle"])),
                display_name=str(profile["display_name"]),
                sx_id=str(profile["sx_id"]) if profile.get("sx_id") else None,
                account_status=AccountAccessStatus(str(profile["account_status"])),
                activation_status=ActivationStatus(str(profile["activation_status"])),
                service_status=ServiceEntitlementStatus(str(profile["service_status"])),
                service_started_at=cls._parse_time(profile.get("service_started_at")),
                service_expires_at=cls._parse_time(profile.get("service_expires_at")),
                service_term_type=str(profile["service_term_type"]) if profile.get("service_term_type") else None,
                custom_term_value=int(profile["custom_term_value"]) if profile.get("custom_term_value") is not None else None,
                custom_term_unit=str(profile["custom_term_unit"]) if profile.get("custom_term_unit") else None,
            )
        except (KeyError, ValueError, TypeError):
            raise AccountAuthorityUnavailable("central identity profile is invalid") from None

    def authenticate_password(self, *, identifier: str, password: str) -> UserIdentity | None:
        try:
            login = self._request_json(
                "/api/v1/auth/password/login",
                method="POST",
                payload={"identifier": identifier, "password": password},
            )
        except LookupError:
            return None

        token = login.get("access_token")
        if not isinstance(token, str) or not token:
            raise AccountAuthorityUnavailable("central login did not return an access token")

        profile = self._request_json("/api/v1/users/current", token=token)
        identity = self._identity_from_profile(profile)

        if str(login.get("subject") or "") != str(identity.user_id):
            raise AccountAuthorityUnavailable("central login subject mismatch")
        if str(login.get("role") or "") != identity.role.value:
            raise AccountAuthorityUnavailable("central login role mismatch")
        login_sx_id = login.get("sx_id")
        if login_sx_id and identity.sx_id and str(login_sx_id) != identity.sx_id:
            raise AccountAuthorityUnavailable("central login identity mismatch")
        return identity


def roaming_identity_from_environment() -> HttpRoamingIdentity | None:
    url = os.environ.get("ALGOFORTIS_ACCOUNT_AUTHORITY_URL", "").strip()
    if not url:
        return None
    timeout_raw = os.environ.get("ALGOFORTIS_ACCOUNT_AUTHORITY_TIMEOUT_SECONDS", "8").strip()
    try:
        timeout = float(timeout_raw)
    except ValueError:
        raise ValueError("ALGOFORTIS_ACCOUNT_AUTHORITY_TIMEOUT_SECONDS must be numeric") from None
    if timeout <= 0 or timeout > 30:
        raise ValueError("central account authority timeout must be in (0, 30]")
    return HttpRoamingIdentity(url, timeout_seconds=timeout)
