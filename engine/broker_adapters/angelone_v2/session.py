"""Explicit fail-closed Angel One authentication/session lifecycle for G6.

Authentication grants broker-observation capability only. Token material is
kept private and never appears in evidence or error strings.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .contracts import AngelOneBrokerProfile, AngelOneCredentialRef


class AngelOneSessionUnavailable(RuntimeError):
    pass


class AngelOneSessionState(str, Enum):
    UNAUTHENTICATED = "UNAUTHENTICATED"
    AUTHENTICATED = "AUTHENTICATED"
    EXPIRED = "EXPIRED"
    DAILY_BOUNDARY_EXPIRED = "DAILY_BOUNDARY_EXPIRED"
    INVALID = "INVALID"
    UNAVAILABLE = "UNAVAILABLE"


def _aware(value: object, field: str) -> datetime:
    if not isinstance(value, datetime):
        raise AngelOneSessionUnavailable(f"{field} unavailable")
    if value.tzinfo is None or value.utcoffset() is None:
        raise AngelOneSessionUnavailable(f"{field} unavailable")
    return value


def _token(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AngelOneSessionUnavailable(f"{field} unavailable")
    return value.strip()


@dataclass(frozen=True, slots=True)
class AngelOneSessionEvidence:
    state: AngelOneSessionState
    observation_available: bool
    profile_ref: str
    account_ref: str
    expires_at: datetime | None
    daily_valid_until: datetime | None
    reason: str


class AngelOneSessionAuthority:
    def __init__(
        self,
        *,
        profile: AngelOneBrokerProfile,
        credential_ref: AngelOneCredentialRef,
        transport: object,
        clock: object,
    ) -> None:
        if not isinstance(profile, AngelOneBrokerProfile):
            raise TypeError("profile must be AngelOneBrokerProfile")
        if not isinstance(credential_ref, AngelOneCredentialRef):
            raise TypeError("credential_ref must be AngelOneCredentialRef")
        if transport is None or not callable(getattr(transport, "authenticate", None)) or not callable(
            getattr(transport, "refresh", None)
        ):
            raise TypeError("transport must provide authenticate() and refresh()")
        if clock is None or not callable(getattr(clock, "now", None)):
            raise TypeError("clock must provide now()")
        self._profile = profile
        self._credential_ref = credential_ref
        self._transport = transport
        self._clock = clock
        self._state = AngelOneSessionState.UNAUTHENTICATED
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: datetime | None = None
        self._daily_valid_until: datetime | None = None
        self._reason = "NOT_AUTHENTICATED"

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(profile_ref={self._profile.reference!r}, "
            f"account_ref={self._credential_ref.account_ref!r}, state={self._state.value!r})"
        )

    def _apply_response(self, response: object) -> None:
        if not isinstance(response, dict):
            raise AngelOneSessionUnavailable("authentication response unavailable")
        access = _token(response.get("access_token"), "access token")
        refresh = _token(response.get("refresh_token"), "refresh token")
        expires_at = _aware(response.get("expires_at"), "access expiry")
        daily_valid_until = _aware(response.get("daily_valid_until"), "daily boundary")
        if daily_valid_until < expires_at:
            raise AngelOneSessionUnavailable("session boundary unavailable")
        self._access_token = access
        self._refresh_token = refresh
        self._expires_at = expires_at
        self._daily_valid_until = daily_valid_until
        self._state = AngelOneSessionState.AUTHENTICATED
        self._reason = "AUTHENTICATED_READ_ONLY"

    def _clear_tokens(self) -> None:
        self._access_token = None
        self._refresh_token = None

    def authenticate(self) -> AngelOneSessionEvidence:
        try:
            response = self._transport.authenticate(
                profile=self._profile,
                credential_ref=self._credential_ref,
            )
            self._apply_response(response)
        except AngelOneSessionUnavailable:
            self._state = AngelOneSessionState.UNAVAILABLE
            self._reason = "AUTHENTICATION_UNAVAILABLE"
            self._clear_tokens()
            raise
        except Exception:
            self._state = AngelOneSessionState.UNAVAILABLE
            self._reason = "AUTHENTICATION_UNAVAILABLE"
            self._clear_tokens()
            raise AngelOneSessionUnavailable("authentication unavailable") from None
        return self.health()

    def refresh(self) -> AngelOneSessionEvidence:
        current = self.health()
        if current.state is AngelOneSessionState.DAILY_BOUNDARY_EXPIRED:
            raise AngelOneSessionUnavailable("daily session boundary expired")
        if not self._refresh_token:
            self._state = AngelOneSessionState.UNAVAILABLE
            self._reason = "REFRESH_UNAVAILABLE"
            raise AngelOneSessionUnavailable("refresh unavailable")
        try:
            response = self._transport.refresh(
                profile=self._profile,
                credential_ref=self._credential_ref,
                refresh_token=self._refresh_token,
            )
            self._apply_response(response)
        except AngelOneSessionUnavailable:
            self._state = AngelOneSessionState.UNAVAILABLE
            self._reason = "REFRESH_UNAVAILABLE"
            self._clear_tokens()
            raise
        except Exception:
            self._state = AngelOneSessionState.UNAVAILABLE
            self._reason = "REFRESH_UNAVAILABLE"
            self._clear_tokens()
            raise AngelOneSessionUnavailable("refresh unavailable") from None
        return self.health()

    def invalidate(self) -> AngelOneSessionEvidence:
        self._clear_tokens()
        self._state = AngelOneSessionState.INVALID
        self._reason = "SESSION_INVALIDATED"
        return self.health()

    def health(self) -> AngelOneSessionEvidence:
        now = self._clock.now()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            self._state = AngelOneSessionState.UNAVAILABLE
            self._reason = "CLOCK_UNAVAILABLE"
            self._clear_tokens()
        elif self._state is AngelOneSessionState.AUTHENTICATED:
            if self._daily_valid_until is None or now > self._daily_valid_until:
                self._state = AngelOneSessionState.DAILY_BOUNDARY_EXPIRED
                self._reason = "DAILY_BOUNDARY_EXPIRED"
                self._clear_tokens()
            elif self._expires_at is None or now > self._expires_at:
                self._state = AngelOneSessionState.EXPIRED
                self._reason = "ACCESS_TOKEN_EXPIRED"
                self._access_token = None

        return AngelOneSessionEvidence(
            state=self._state,
            observation_available=self._state is AngelOneSessionState.AUTHENTICATED,
            profile_ref=self._profile.reference,
            account_ref=self._credential_ref.account_ref,
            expires_at=self._expires_at,
            daily_valid_until=self._daily_valid_until,
            reason=self._reason,
        )


__all__ = [
    "AngelOneSessionAuthority",
    "AngelOneSessionEvidence",
    "AngelOneSessionState",
    "AngelOneSessionUnavailable",
]
