"""AlgoFortis V1 — Session Model & Dual-Token Family Manager
Implements ADR-09, ADR-33.
- Access Token: 15-minute strict lifespan.
- Refresh Token: Rotating single-use token.
- Refresh Absolute Maximum Lifetime: 30 days.
- Refresh Idle Inactivity Timeout: 7 days.
- Reused Refresh Token Detection: Immediately revokes the entire session family.
"""
import time
import uuid
import hmac
import hashlib
import json
import base64
from typing import Dict, Any, Optional, Tuple, List

ACCESS_TOKEN_TTL_SEC = 15 * 60          # 15 Minutes
REFRESH_TOKEN_INACTIVITY_SEC = 7 * 86400  # 7 Days
REFRESH_TOKEN_ABSOLUTE_SEC = 30 * 86400  # 30 Days


class SessionTokenFamily:
    def __init__(self, family_id: str, user_id: str, device_id: str, role: str):
        self.family_id = family_id
        self.user_id = user_id
        self.device_id = device_id
        self.role = role
        self.created_at = time.time()
        self.last_active_at = time.time()
        self.absolute_expiry = self.created_at + REFRESH_TOKEN_ABSOLUTE_SEC
        self.active_refresh_token_hash: Optional[str] = None
        self.consumed_refresh_token_hashes: set = set()
        self.revoked = False
        self.revocation_reason: Optional[str] = None


class SessionManager:
    """Manages short-lived access tokens and rotating refresh token families."""

    def __init__(self, signing_secret: Optional[bytes] = None):
        self._secret = signing_secret or uuid.uuid4().bytes
        self._families: Dict[str, SessionTokenFamily] = {}  # family_id -> SessionTokenFamily
        self._active_tokens: Dict[str, Dict[str, Any]] = {} # access_token -> payload

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_session(self, user_id: str, device_id: str, role: str) -> Tuple[str, str, Dict[str, Any]]:
        """Create a new session family. Returns (access_token, refresh_token, session_info)."""
        family_id = f"fam_{uuid.uuid4().hex[:16]}"
        family = SessionTokenFamily(family_id, user_id, device_id, role)
        
        access_token = f"af_at_{uuid.uuid4().hex}"
        refresh_token = f"af_rt_{uuid.uuid4().hex}"
        
        family.active_refresh_token_hash = self._hash_token(refresh_token)
        self._families[family_id] = family
        
        access_payload = {
            "token": access_token,
            "family_id": family_id,
            "user_id": user_id,
            "device_id": device_id,
            "role": role,
            "expires_at": time.time() + ACCESS_TOKEN_TTL_SEC
        }
        self._active_tokens[access_token] = access_payload

        return access_token, refresh_token, {
            "family_id": family_id,
            "user_id": user_id,
            "device_id": device_id,
            "role": role,
            "access_expires_at": access_payload["expires_at"],
            "refresh_absolute_expires_at": family.absolute_expiry
        }

    def validate_access_token(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Validate short-lived access token against session family state."""
        payload = self._active_tokens.get(access_token)
        if not payload:
            return None
        
        if time.time() > payload["expires_at"]:
            self._active_tokens.pop(access_token, None)
            return None
        
        family = self._families.get(payload["family_id"])
        if not family or family.revoked:
            self._active_tokens.pop(access_token, None)
            return None
        
        return payload

    def rotate_refresh_token(self, presented_refresh_token: str) -> Tuple[str, str]:
        """Rotate single-use refresh token. If reuse is detected, revoke the entire family!"""
        token_hash = self._hash_token(presented_refresh_token)
        
        # Find matching family
        matched_family: Optional[SessionTokenFamily] = None
        for family in self._families.values():
            if family.active_refresh_token_hash == token_hash:
                matched_family = family
                break
            elif token_hash in family.consumed_refresh_token_hashes:
                # TOKEN REUSE DETECTED! Immediate fail-closed revocation of family.
                family.revoked = True
                family.revocation_reason = "REFRESH_TOKEN_REUSE_ATTACK_DETECTED"
                raise PermissionError("Refresh token reuse detected: entire session family revoked.")

        if not matched_family:
            raise PermissionError("Invalid or unknown refresh token.")

        if matched_family.revoked:
            raise PermissionError(f"Session family is revoked ({matched_family.revocation_reason}).")

        now = time.time()
        # Check absolute expiry (30 days)
        if now > matched_family.absolute_expiry:
            matched_family.revoked = True
            matched_family.revocation_reason = "ABSOLUTE_LIFETIME_EXPIRED"
            raise PermissionError("Session lifetime expired (30-day max). Re-authentication required.")

        # Check idle inactivity (7 days)
        if now - matched_family.last_active_at > REFRESH_TOKEN_INACTIVITY_SEC:
            matched_family.revoked = True
            matched_family.revocation_reason = "INACTIVITY_TIMEOUT_EXPIRED"
            raise PermissionError("Session expired due to inactivity (7-day idle limit).")

        # Mark presented token as consumed
        matched_family.consumed_refresh_token_hashes.add(token_hash)
        matched_family.last_active_at = now

        # Generate new pair
        new_access_token = f"af_at_{uuid.uuid4().hex}"
        new_refresh_token = f"af_rt_{uuid.uuid4().hex}"
        matched_family.active_refresh_token_hash = self._hash_token(new_refresh_token)

        # Register access token
        self._active_tokens[new_access_token] = {
            "token": new_access_token,
            "family_id": matched_family.family_id,
            "user_id": matched_family.user_id,
            "device_id": matched_family.device_id,
            "role": matched_family.role,
            "expires_at": now + ACCESS_TOKEN_TTL_SEC
        }

        return new_access_token, new_refresh_token

    def revoke_session_family(self, family_id: str, reason: str = "EXPLICIT_LOGOUT"):
        """Revoke a specific session family."""
        family = self._families.get(family_id)
        if family:
            family.revoked = True
            family.revocation_reason = reason

    def revoke_all_user_sessions(self, user_id: str, reason: str = "GLOBAL_USER_REVOCATION"):
        """Revoke all session families belonging to a specific user across all devices."""
        for family in self._families.values():
            if family.user_id == user_id:
                family.revoked = True
                family.revocation_reason = reason
