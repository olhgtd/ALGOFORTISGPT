"""AlgoFortis V1 — Auth Policy, Rate Limiting & High-Assurance Recovery Enforcer
Implements ADR-06, ADR-11, ADR-12, ADR-13, and AUTH_ACCESS_CONTRACT_V1.
- Rate Limiting: Progressive flow-isolated cooldown escalation.
- Device Quota: Max 3 devices per user (no silent eviction).
- Activation Token: 24-hour single-use strict lifecycle.
- Recovery Codes: 8 single-use cryptographic recovery codes.
- High-Assurance Recovery: Complete revocation of all sessions, refresh tokens, devices, and keys.
"""
import time
import uuid
import hashlib
from typing import Dict, Any, List, Optional, Set, Tuple


class RateLimitTracker:
    """Tracks failed authentication attempts and computes progressive cooldowns."""

    def __init__(self, failure_threshold: int = 5):
        self.failure_threshold = failure_threshold
        # key -> (failure_count, cooldown_until_timestamp, cooldown_stage)
        self._records: Dict[str, Dict[str, Any]] = {}

    def record_failure(self, identifier: str) -> Tuple[bool, int]:
        """Record a failure. Returns (is_locked, remaining_cooldown_seconds)."""
        now = time.time()
        rec = self._records.setdefault(identifier, {"count": 0, "cooldown_until": 0, "stage": 0})

        # If currently in cooldown, reject immediately
        if now < rec["cooldown_until"]:
            return True, int(rec["cooldown_until"] - now)

        rec["count"] += 1
        
        if rec["count"] >= self.failure_threshold:
            # Progressive cooldown ladder: 15m (900s) -> 1h (3600s) -> 24h (86400s)
            rec["stage"] += 1
            if rec["stage"] == 1:
                duration = 900
            elif rec["stage"] == 2:
                duration = 3600
            else:
                duration = 86400

            rec["cooldown_until"] = now + duration
            rec["count"] = 0  # reset count for next evaluation
            return True, duration

        return False, 0

    def record_success(self, identifier: str):
        """Reset failures on successful authentication."""
        self._records.pop(identifier, None)

    def is_locked_out(self, identifier: str) -> Tuple[bool, int]:
        """Check if identifier is currently locked out."""
        rec = self._records.get(identifier)
        if not rec:
            return False, 0
        now = time.time()
        if now < rec["cooldown_until"]:
            return True, int(rec["cooldown_until"] - now)
        return False, 0

    def record_request(self, identifier: str, max_requests: int | None = None, window_seconds: int = 60) -> Tuple[bool, int]:
        """Record a request for throttle-tracking. If threshold exceeded, activates cooldown.
        Returns (is_throttled, remaining_cooldown_seconds)."""
        now = time.time()
        threshold = max_requests if max_requests is not None else self.failure_threshold
        rec = self._records.setdefault(identifier, {"count": 0, "cooldown_until": 0, "stage": 0, "reset_at": now + window_seconds})
        if now < rec["cooldown_until"]:
            return True, int(rec["cooldown_until"] - now)
        if now > rec.get("reset_at", 0):
            rec["count"] = 0
            rec["reset_at"] = now + window_seconds
        rec["count"] += 1
        if rec["count"] > threshold:
            duration = min(window_seconds, 60)
            rec["cooldown_until"] = now + duration
            return True, duration
        return False, 0


class AuthPolicyManager:
    """Authoritative enforcer for user quotas, activation, recovery, and security lifecycles."""

    MAX_DEVICES_PER_USER = 3
    ACTIVATION_TTL_SEC = 24 * 3600  # 24 Hours
    INITIAL_RECOVERY_CODES_COUNT = 8

    def __init__(self):
        # Flow-isolated rate limiters
        self.login_limiter = RateLimitTracker(failure_threshold=5)
        self.otp_limiter = RateLimitTracker(failure_threshold=3)
        self.recovery_limiter = RateLimitTracker(failure_threshold=3)
        self.expensive_limiter = RateLimitTracker(failure_threshold=30)
        
        # In-memory storage for policy demonstrations / unit tests
        self._activations: Dict[str, Dict[str, Any]] = {}  # code -> metadata
        self._user_devices: Dict[str, Set[str]] = {}      # user_id -> set(device_ids)
        self._recovery_codes: Dict[str, Set[str]] = {}    # user_id -> set(hashed_codes)

    def generate_activation_code(self, user_id: str, email: str, role: str = "USER") -> str:
        """Issue a 24-hour single-use activation code."""
        code = f"AF-ACT-{uuid.uuid4().hex[:4].upper()}-{uuid.uuid4().hex[:4].upper()}-{uuid.uuid4().hex[:4].upper()}"
        self._activations[code] = {
            "code": code,
            "user_id": user_id,
            "email": email,
            "role": role,
            "created_at": time.time(),
            "expires_at": time.time() + self.ACTIVATION_TTL_SEC,
            "redeemed": False
        }
        return code

    def redeem_activation_code(self, code: str) -> Dict[str, Any]:
        """Redeem activation code. Fails closed if expired or already redeemed."""
        rec = self._activations.get(code)
        if not rec:
            raise ValueError("Activation token invalid or unknown.")
        if rec["redeemed"]:
            raise ValueError("Activation token has already been redeemed.")
        if time.time() > rec["expires_at"]:
            raise ValueError("Activation token expired (24-hour lifetime exceeded). Contact Owner.")

        rec["redeemed"] = True
        return rec

    def register_device(self, user_id: str, device_id: str) -> None:
        """Register a device for a user, enforcing strict 3-device quota with zero silent evictions."""
        devices = self._user_devices.setdefault(user_id, set())
        if device_id in devices:
            return  # Already registered

        if len(devices) >= self.MAX_DEVICES_PER_USER:
            raise PermissionError(
                f"Maximum device limit ({self.MAX_DEVICES_PER_USER}) reached. "
                "Explicitly revoke an existing device before enrolling a new one."
            )

        devices.add(device_id)

    def revoke_device(self, user_id: str, device_id: str) -> None:
        """Revoke a specific device."""
        devices = self._user_devices.get(user_id)
        if devices and device_id in devices:
            devices.remove(device_id)

    def generate_recovery_codes(self, user_id: str) -> List[str]:
        """Generate 8 single-use cryptographic recovery codes."""
        raw_codes = [f"RC-{uuid.uuid4().hex[:4].upper()}-{uuid.uuid4().hex[:4].upper()}" for _ in range(self.INITIAL_RECOVERY_CODES_COUNT)]
        hashed_set = {hashlib.sha256(c.encode("utf-8")).hexdigest() for c in raw_codes}
        self._recovery_codes[user_id] = hashed_set
        return raw_codes

    def execute_high_assurance_recovery(self, user_id: str, recovery_code: str, session_manager=None) -> bool:
        """Execute high-assurance recovery:
        1. Validate single-use recovery code.
        2. Revoke ALL active sessions & refresh token families.
        3. Revoke ALL registered devices & device keys.
        4. Invalidate used recovery code.
        """
        is_locked, cooldown = self.recovery_limiter.is_locked_out(user_id)
        if is_locked:
            raise PermissionError(f"Recovery flow locked out. Cooldown active for {cooldown}s.")

        code_hash = hashlib.sha256(recovery_code.strip().encode("utf-8")).hexdigest()
        user_codes = self._recovery_codes.get(user_id, set())

        if code_hash not in user_codes:
            locked, rem = self.recovery_limiter.record_failure(user_id)
            if locked:
                raise PermissionError(f"Invalid recovery code. Flow locked out for {rem}s.")
            raise ValueError("Invalid recovery code.")

        # Consume code
        user_codes.remove(code_hash)
        self.recovery_limiter.record_success(user_id)

        # 1. Revoke all sessions
        if session_manager:
            session_manager.revoke_all_user_sessions(user_id, reason="HIGH_ASSURANCE_RECOVERY_PURGE")

        # 2. Purge all registered devices
        self._user_devices[user_id] = set()

        return True
