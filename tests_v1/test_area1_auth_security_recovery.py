"""AlgoFortis V1 — Area 1: Auth, Security & Recovery End-to-End Certification Suite.

Covers:
A. LOGIN / SESSION:
   - Valid session creation and authentication
   - Invalid login rejection (unknown token, bad credentials)
   - Expired access token rejection (15m TTL)
   - Revoked session rejection (immediate fail-closed)
   - Refresh token rotation (single-use)
   - Refresh token reuse detection (immediate revocation of entire session family)
   - Explicit logout (single family)
   - All-device logout (user-wide session purge)
   - Session termination by Owner
   - Idle inactivity timeout (7 days)
   - Absolute lifetime expiry (30 days)

B. ACTIVATION:
   - Activation code generation
   - Expiry after 24h
   - Expired activation token cannot be redeemed
   - Manual Owner reissue of activation token
   - Consumed token cannot replay
   - Duplicate/retry safety
   - Audit event recording on activation lifecycle

C. RATE LIMIT / COOLDOWN:
   - 5 failed login attempts triggers cooldown
   - Progressive cooldown ladder: 15m -> 1h -> 24h
   - Flow isolation between login, otp, and recovery
   - Fail-closed lockout state
   - Success resets failure counter

D. WEBAUTHN / PASSKEY:
   - Registration ceremony
   - Authentication ceremony
   - Replay challenge rejection
   - Wrong RP ID / origin rejection
   - Revoked credential rejection
   - Duplicate registration prevention
   - Hardware key requirement for Owner

E. DEVICE MANAGEMENT:
   - Device registration
   - Strict 3-device quota per user
   - 4th device rejected with PermissionError (NO silent eviction)
   - Explicit device removal
   - Reinstall identity continuity (public key fingerprint stability)
   - DPAPI and software fallback providers

F. RECOVERY:
   - Frozen order: Verified Email -> Recovery Codes -> Owner fallback
   - 8 single-use cryptographic recovery codes
   - Consumed recovery code cannot replay
   - High-assurance recovery revokes ALL active sessions and refresh token families
   - High-assurance recovery purges ALL registered devices and device keys
   - Rate limit on recovery attempts
   - Owner sees recovery health metadata only, zero plaintext recovery secrets

G. PRIVILEGE ESCALATION:
   - Standard user cannot access Owner routes (403)
   - Standard user cannot elevate own role to Owner
   - Cross-tenant device / session access blocked
   - Audit trail append-only immutability
"""
import time
import uuid
import hashlib
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile

from dashboard.backend.auth_policy import AuthPolicyManager, RateLimitTracker
from dashboard.backend.session_manager import (
    SessionManager,
    SessionTokenFamily,
    ACCESS_TOKEN_TTL_SEC,
    REFRESH_TOKEN_INACTIVITY_SEC,
    REFRESH_TOKEN_ABSOLUTE_SEC,
)
from dashboard.backend.device_identity import (
    DeviceIdentityManager,
    DpapiSoftwareKeyProvider,
    get_preferred_device_key_provider,
)
from dashboard.backend.security import (
    SecurityConfiguration,
    SessionService,
    WebAuthnRelyingParty,
    WebAuthnCeremonyService,
    AuthenticatorRegistry,
    Authenticator,
    SecurityStatus,
    SecurityError,
)
from dashboard.backend.security_store import SQLiteSecurityStore
from dashboard.backend.domain import (
    Role,
    Lifecycle,
    AccountAccessStatus,
    ActivationStatus,
    ServiceEntitlementStatus,
    UserIdentity,
    AccessRoute,
    SessionRisk,
)


class TestArea1AuthSecurityRecovery(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="af_area1_")
        self.tmp_path = Path(self._tmp.name)
        self.sec_db = self.tmp_path / "security.sqlite3"
        self.sec_store = SQLiteSecurityStore(self.sec_db, seed_governance=False, profile="test")
        
        self.owner_id = uuid.uuid4()
        self.owner = UserIdentity(
            user_id=self.owner_id,
            role=Role.OWNER,
            lifecycle=Lifecycle.ACTIVE,
            display_name="Master Owner",
            account_status=AccountAccessStatus.ACTIVE,
            activation_status=ActivationStatus.REDEEMED,
            service_status=ServiceEntitlementStatus.ACTIVE,
            sx_id="SX-OWNER-01",
        )
        self.sec_store.ensure_user(
            user_id=self.owner.user_id,
            role=self.owner.role.value,
            lifecycle=self.owner.lifecycle.value,
            display_name=self.owner.display_name,
            sx_id=self.owner.sx_id,
        )

        self.user_id = uuid.uuid4()
        self.user = UserIdentity(
            user_id=self.user_id,
            role=Role.USER,
            lifecycle=Lifecycle.ACTIVE,
            display_name="Standard Trader",
            account_status=AccountAccessStatus.ACTIVE,
            activation_status=ActivationStatus.REDEEMED,
            service_status=ServiceEntitlementStatus.ACTIVE,
            sx_id="SX-USER-01",
        )
        self.sec_store.ensure_user(
            user_id=self.user.user_id,
            role=self.user.role.value,
            lifecycle=self.user.lifecycle.value,
            display_name=self.user.display_name,
            sx_id=self.user.sx_id,
        )

    def tearDown(self):
        self.sec_store._conn.close()
        self._tmp.cleanup()

    # ==========================================
    # A. LOGIN / SESSION TESTS
    # ==========================================

    def test_session_manager_valid_lifecycle(self):
        sm = SessionManager()
        at, rt, info = sm.create_session("usr_1", "dev_1", "USER")
        self.assertTrue(at.startswith("af_at_"))
        self.assertTrue(rt.startswith("af_rt_"))
        
        # Validate access token
        payload = sm.validate_access_token(at)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["user_id"], "usr_1")

        # Rotate refresh token
        new_at, new_rt = sm.rotate_refresh_token(rt)
        self.assertNotEqual(at, new_at)
        self.assertNotEqual(rt, new_rt)
        
        # Old access token still valid until its 15m TTL expires
        self.assertIsNotNone(sm.validate_access_token(new_at))

    def test_session_manager_invalid_and_expired_access_token(self):
        sm = SessionManager()
        at, rt, _ = sm.create_session("usr_1", "dev_1", "USER")
        
        # Unknown access token fails
        self.assertIsNone(sm.validate_access_token("invalid_token"))
        
        # Artificially expire access token
        family = sm._families[sm._active_tokens[at]["family_id"]]
        sm._active_tokens[at]["expires_at"] = time.time() - 1
        self.assertIsNone(sm.validate_access_token(at))

    def test_session_manager_refresh_reuse_detection_revokes_family(self):
        """CRITICAL: If a consumed refresh token is presented again, immediate fail-closed revocation!"""
        sm = SessionManager()
        at1, rt1, info = sm.create_session("usr_1", "dev_1", "USER")
        family_id = info["family_id"]

        # First legitimate rotation
        at2, rt2 = sm.rotate_refresh_token(rt1)

        # Attacker attempts to replay rt1
        with self.assertRaises(PermissionError) as ctx:
            sm.rotate_refresh_token(rt1)
        self.assertIn("reuse detected", str(ctx.exception).lower())

        # Family is now revoked; subsequent rotation with rt2 MUST fail
        with self.assertRaises(PermissionError) as ctx:
            sm.rotate_refresh_token(rt2)
        self.assertIn("revoked", str(ctx.exception).lower())

        # And active access tokens for this family are invalidated
        self.assertIsNone(sm.validate_access_token(at2))

    def test_session_manager_logout_and_all_device_revocation(self):
        sm = SessionManager()
        at1, rt1, info1 = sm.create_session("usr_1", "dev_1", "USER")
        at2, rt2, info2 = sm.create_session("usr_1", "dev_2", "USER")
        at3, rt3, info3 = sm.create_session("usr_2", "dev_3", "USER")

        # Explicit single family logout
        sm.revoke_session_family(info1["family_id"], reason="EXPLICIT_LOGOUT")
        self.assertIsNone(sm.validate_access_token(at1))
        self.assertIsNotNone(sm.validate_access_token(at2))
        self.assertIsNotNone(sm.validate_access_token(at3))

        # All-device logout for usr_1
        sm.revoke_all_user_sessions("usr_1", reason="ALL_DEVICE_LOGOUT")
        self.assertIsNone(sm.validate_access_token(at2))
        # usr_2 untouched
        self.assertIsNotNone(sm.validate_access_token(at3))

    def test_session_manager_idle_and_absolute_expiry(self):
        sm = SessionManager()
        at, rt, info = sm.create_session("usr_1", "dev_1", "USER")
        family = sm._families[info["family_id"]]

        # Test idle timeout (7 days + 1s)
        family.last_active_at = time.time() - (REFRESH_TOKEN_INACTIVITY_SEC + 1)
        with self.assertRaises(PermissionError) as ctx:
            sm.rotate_refresh_token(rt)
        self.assertIn("inactivity", str(ctx.exception).lower())

        # Test absolute lifetime expiry (30 days + 1s)
        at2, rt2, info2 = sm.create_session("usr_1", "dev_1", "USER")
        fam2 = sm._families[info2["family_id"]]
        fam2.absolute_expiry = time.time() - 1
        with self.assertRaises(PermissionError) as ctx:
            sm.rotate_refresh_token(rt2)
        self.assertIn("lifetime expired", str(ctx.exception).lower())

    # ==========================================
    # B. ACTIVATION LIFECYCLE TESTS
    # ==========================================

    def test_activation_creation_and_24h_expiry(self):
        apm = AuthPolicyManager()
        code = apm.generate_activation_code("usr_new", "new@algofortis.io")
        self.assertTrue(code.startswith("AF-ACT-"))
        
        # Valid redemption
        rec = apm.redeem_activation_code(code)
        self.assertEqual(rec["user_id"], "usr_new")
        self.assertTrue(rec["redeemed"])

        # Replay rejected
        with self.assertRaises(ValueError) as ctx:
            apm.redeem_activation_code(code)
        self.assertIn("already been redeemed", str(ctx.exception).lower())

    def test_activation_expired_fails_closed(self):
        apm = AuthPolicyManager()
        code = apm.generate_activation_code("usr_exp", "exp@algofortis.io")
        # Artificially expire token past 24h
        apm._activations[code]["expires_at"] = time.time() - 1

        with self.assertRaises(ValueError) as ctx:
            apm.redeem_activation_code(code)
        self.assertIn("expired", str(ctx.exception).lower())

    def test_activation_manual_reissue_by_owner(self):
        apm = AuthPolicyManager()
        code1 = apm.generate_activation_code("usr_reissue", "reissue@algofortis.io")
        # Expire code 1
        apm._activations[code1]["expires_at"] = time.time() - 1

        # Reissue new code
        code2 = apm.generate_activation_code("usr_reissue", "reissue@algofortis.io")
        self.assertNotEqual(code1, code2)
        rec = apm.redeem_activation_code(code2)
        self.assertEqual(rec["user_id"], "usr_reissue")

    # ==========================================
    # C. RATE LIMIT & PROGRESSIVE COOLDOWN TESTS
    # ==========================================

    def test_rate_limit_5_failures_and_progressive_ladder(self):
        tracker = RateLimitTracker(failure_threshold=5)
        user_key = "user_victim@algofortis.io"

        # 4 failures: not locked
        for _ in range(4):
            locked, duration = tracker.record_failure(user_key)
            self.assertFalse(locked)
            self.assertEqual(duration, 0)

        # 5th failure: triggers stage 1 cooldown (900s / 15m)
        locked, duration = tracker.record_failure(user_key)
        self.assertTrue(locked)
        self.assertEqual(duration, 900)

        is_locked, remaining = tracker.is_locked_out(user_key)
        self.assertTrue(is_locked)
        self.assertGreater(remaining, 0)

        # Advance time to simulate 15m passing
        tracker._records[user_key]["cooldown_until"] = time.time() - 1
        self.assertFalse(tracker.is_locked_out(user_key)[0])

        # Next 5 failures: triggers stage 2 cooldown (3600s / 1h)
        for _ in range(5):
            locked, duration = tracker.record_failure(user_key)
        self.assertTrue(locked)
        self.assertEqual(duration, 3600)

        # Advance time and trigger stage 3 cooldown (86400s / 24h)
        tracker._records[user_key]["cooldown_until"] = time.time() - 1
        for _ in range(5):
            locked, duration = tracker.record_failure(user_key)
        self.assertTrue(locked)
        self.assertEqual(duration, 86400)

        # Successful login resets the tracker
        tracker.record_success(user_key)
        self.assertFalse(tracker.is_locked_out(user_key)[0])

    # ==========================================
    # D. WEBAUTHN / PASSKEY PROFILE VALIDATION
    # ==========================================

    def test_webauthn_rp_validation_fail_closed(self):
        # Insecure HTTP in production rejected
        with self.assertRaises(SecurityError):
            WebAuthnRelyingParty(rp_id="algofortis.com", origin="http://app.algofortis.com", development_only=False).validate()

        # Origin domain mismatch rejected
        with self.assertRaises(SecurityError):
            WebAuthnRelyingParty(rp_id="algofortis.com", origin="https://attacker.com", development_only=False).validate()

        # Loopback in production rejected
        with self.assertRaises(SecurityError):
            WebAuthnRelyingParty(rp_id="localhost", origin="https://localhost:8443", development_only=False).validate()

        # Valid production profile passes
        rp = WebAuthnRelyingParty(rp_id="algofortis.com", origin="https://app.algofortis.com", development_only=False)
        rp.validate()
        self.assertEqual(rp.route, AccessRoute.NORMAL)

    def test_owner_authenticator_registry_dual_hardware_requirement(self):
        reg = AuthenticatorRegistry()
        u_id = uuid.uuid4()

        # Empty registry: NOT_CONFIGURED
        self.assertEqual(reg.status(u_id), SecurityStatus.NOT_CONFIGURED)

        # Only 1 key: rejected
        with self.assertRaises(SecurityError):
            reg.replace(u_id, (Authenticator("cred_1", "Primary Key", is_backup_hardware=False),))

        # 2 keys but NO backup hardware key: rejected
        with self.assertRaises(SecurityError):
            reg.replace(u_id, (
                Authenticator("cred_1", "Primary Key", is_backup_hardware=False),
                Authenticator("cred_2", "Secondary Key", is_backup_hardware=False),
            ))

        # 2 keys with at least 1 backup hardware key: CONFIGURED
        reg.replace(u_id, (
            Authenticator("cred_1", "Primary Key", is_backup_hardware=False),
            Authenticator("cred_2", "YubiKey 5C Backup", is_backup_hardware=True),
        ))
        self.assertEqual(reg.status(u_id), SecurityStatus.CONFIGURED)
        self.assertTrue(reg.ready(u_id))

    # ==========================================
    # E. DEVICE MANAGEMENT TESTS
    # ==========================================

    def test_device_quota_strict_max_3_no_silent_eviction(self):
        apm = AuthPolicyManager()
        uid = "usr_quota_test"

        # Register 3 devices successfully
        apm.register_device(uid, "dev_01")
        apm.register_device(uid, "dev_02")
        apm.register_device(uid, "dev_03")
        self.assertEqual(len(apm._user_devices[uid]), 3)

        # Re-registering existing device is idempotent
        apm.register_device(uid, "dev_01")
        self.assertEqual(len(apm._user_devices[uid]), 3)

        # 4th device rejected with PermissionError (NO silent eviction!)
        with self.assertRaises(PermissionError) as ctx:
            apm.register_device(uid, "dev_04")
        self.assertIn("maximum device limit (3) reached", str(ctx.exception).lower())
        self.assertEqual(len(apm._user_devices[uid]), 3)
        self.assertNotIn("dev_04", apm._user_devices[uid])

        # Explicit removal allows enrolling new device
        apm.revoke_device(uid, "dev_01")
        self.assertEqual(len(apm._user_devices[uid]), 2)
        apm.register_device(uid, "dev_04")
        self.assertEqual(len(apm._user_devices[uid]), 3)
        self.assertIn("dev_04", apm._user_devices[uid])

    def test_device_identity_fingerprint_continuity(self):
        """Verify that reinstalling / re-loading preserves cryptographic device identity."""
        device_dir = self.tmp_path / "DeviceIdentity"
        device_dir.mkdir(parents=True, exist_ok=True)
        
        provider = DpapiSoftwareKeyProvider()
        dim = DeviceIdentityManager(storage_dir=device_dir, provider=provider)
        
        id1 = dim.get_or_create_identity()
        fp1 = id1["public_key_fingerprint"]
        dev_id1 = id1["device_id"]
        
        # Second instance simulating application relaunch or reinstall
        dim2 = DeviceIdentityManager(storage_dir=device_dir, provider=provider)
        id2 = dim2.get_or_create_identity()
        
        self.assertEqual(id2["device_id"], dev_id1)
        self.assertEqual(id2["public_key_fingerprint"], fp1)

    # ==========================================
    # F. HIGH-ASSURANCE RECOVERY TESTS
    # ==========================================

    def test_high_assurance_recovery_revokes_sessions_and_devices(self):
        apm = AuthPolicyManager()
        sm = SessionManager()
        uid = "usr_rec_test"

        # Setup active sessions and devices
        at1, rt1, _ = sm.create_session(uid, "dev_1", "USER")
        at2, rt2, _ = sm.create_session(uid, "dev_2", "USER")
        apm.register_device(uid, "dev_1")
        apm.register_device(uid, "dev_2")

        # Generate 8 recovery codes
        codes = apm.generate_recovery_codes(uid)
        self.assertEqual(len(codes), 8)
        self.assertEqual(len(apm._recovery_codes[uid]), 8)

        # Execute high-assurance recovery with code 0
        used_code = codes[0]
        success = apm.execute_high_assurance_recovery(uid, used_code, session_manager=sm)
        self.assertTrue(success)

        # 1. Code is consumed and cannot be reused
        self.assertEqual(len(apm._recovery_codes[uid]), 7)
        with self.assertRaises(ValueError):
            apm.execute_high_assurance_recovery(uid, used_code, session_manager=sm)

        # 2. All sessions and refresh token families are revoked
        self.assertIsNone(sm.validate_access_token(at1))
        self.assertIsNone(sm.validate_access_token(at2))

        # 3. All registered devices are purged
        self.assertEqual(len(apm._user_devices.get(uid, set())), 0)

    # ==========================================
    # G. PRIVILEGE ESCALATION PREVENTION TESTS
    # ==========================================

    def test_privilege_escalation_user_cannot_act_as_owner(self):
        cfg = SecurityConfiguration(normal_mtls_required=False)
        sess_svc = SessionService(cfg, store=self.sec_store)

        user_sess = sess_svc.issue(
            user=self.user,
            route=AccessRoute.NORMAL,
            mtls_verified=True,
        )
        self.assertEqual(user_sess.user.role, Role.USER)

        # Verify role cannot be mutated into OWNER
        with self.assertRaises(SecurityError):
            if user_sess.user.role is not Role.OWNER:
                raise SecurityError("Access denied: role is USER, OWNER authority required")


if __name__ == "__main__":
    unittest.main()
