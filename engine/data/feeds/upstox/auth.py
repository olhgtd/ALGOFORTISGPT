"""Upstox V3 Market Data Feed Authorization Client.

Handles requesting authorized WebSocket redirect URIs for Upstox V3 Market Data Feed.
Enforces security constraints:
- Zero token persistence or disk caching
- Redaction of authorization credentials and query secrets from exceptions/logs
- Strict wss:// scheme requirement
- Pluggable HTTP requester boundary for deterministic offline unit testing
"""

from __future__ import annotations

import json
from typing import Any, Callable
import urllib.error
import urllib.request

__all__ = [
    "UpstoxAuthError",
    "UpstoxV3AuthorizationClient",
]


class UpstoxAuthError(RuntimeError):
    """Raised when Upstox V3 feed authorization fails or receives an invalid response."""


def _default_http_request(url: str, headers: dict[str, str]) -> dict[str, Any]:
    """Default HTTP requester using urllib.request with strict timeouts."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            raw_data = resp.read().decode("utf-8")
            return json.loads(raw_data)
    except urllib.error.HTTPError as exc:
        raise UpstoxAuthError(f"HTTP authorization request failed with status {exc.code}") from None
    except urllib.error.URLError as exc:
        raise UpstoxAuthError("HTTP authorization connection failed") from None
    except Exception as exc:
        raise UpstoxAuthError("Failed to parse authorization response") from None


class UpstoxV3AuthorizationClient:
    """Authorization client for Upstox Market Data Feed V3.

    Requests a fresh authorized WebSocket redirect URL on each invocation.
    Never stores or persists tokens.
    """

    DEFAULT_AUTH_URL = "https://api.upstox.com/v3/feed/market-data-feed/authorize"

    def __init__(
        self,
        access_token_provider: Callable[[], str],
        *,
        auth_url: str = DEFAULT_AUTH_URL,
        http_requester: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
    ) -> None:
        if not callable(access_token_provider):
            raise TypeError("access_token_provider must be callable")
        if not isinstance(auth_url, str) or not auth_url.strip():
            raise ValueError("auth_url must be a non-empty string")

        self._access_token_provider = access_token_provider
        self._auth_url = auth_url.strip()
        self._http_requester = http_requester or _default_http_request

    @property
    def auth_url(self) -> str:
        """Return the target authorization endpoint URL."""
        return self._auth_url

    def get_authorized_websocket_url(self) -> str:
        """Fetch a fresh authorized WebSocket streaming endpoint.

        Returns:
            A valid wss:// WebSocket URL.

        Raises:
            UpstoxAuthError: If the token is empty, request fails, response is invalid,
                             or returned URL does not use the wss:// protocol.
        """
        token = self._access_token_provider()
        if not isinstance(token, str) or not token.strip():
            raise UpstoxAuthError("Access token provider returned an empty or invalid token")

        clean_token = token.strip()
        headers = {
            "Authorization": f"Bearer {clean_token}",
            "Accept": "application/json",
        }

        try:
            payload = self._http_requester(self._auth_url, headers)
        except UpstoxAuthError:
            raise
        except Exception as exc:
            # Ensure no token leaks in exception message
            raise UpstoxAuthError("Authorization request failed") from None

        if not isinstance(payload, dict):
            raise UpstoxAuthError("Authorization response must be a JSON object")

        status = payload.get("status")
        if status != "success":
            error_msg = payload.get("message") or payload.get("errors") or "non-success status"
            raise UpstoxAuthError(f"Authorization failed: {error_msg}")

        data = payload.get("data")
        if not isinstance(data, dict):
            raise UpstoxAuthError("Authorization response missing 'data' object")

        ws_url = data.get("authorized_redirect_uri") or data.get("authorizedRedirectUri")
        if not isinstance(ws_url, str) or not ws_url.strip():
            raise UpstoxAuthError("Authorization response missing 'authorized_redirect_uri'")

        clean_ws_url = ws_url.strip()
        if not clean_ws_url.startswith("wss://"):
            raise UpstoxAuthError(
                f"Authorized redirect URI must use wss:// scheme, got: {clean_ws_url.split('?')[0]}"
            )

        return clean_ws_url
