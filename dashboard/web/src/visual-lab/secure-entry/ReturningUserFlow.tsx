import React, { useState } from "react";
import type { VerificationState } from "./types";
import { executeRealWebAuthnAuthentication } from "./webauthn-client";

interface ReturningUserFlowProps {
  sentinelxId: string;
  onIdChange: (id: string) => void;
  verificationState: VerificationState;
  onStartVerification: () => void;
  onVerifySuccess: (token?: string) => void;
  onVerifyFailure: (error: string) => void;
  onSwitchToAccessGate: () => void;
  onSwitchToOwnerSetup: () => void;
  onSwitchToRecovery: () => void;
  onEnterWorkspace: (role?: "OWNER" | "USER") => void;
  isMobileLayout?: boolean;
}

export const ReturningUserFlow: React.FC<ReturningUserFlowProps> = ({
  sentinelxId,
  onIdChange,
  verificationState,
  onStartVerification,
  onVerifySuccess,
  onVerifyFailure,
  onSwitchToAccessGate,
  onSwitchToOwnerSetup,
  onSwitchToRecovery,
  onEnterWorkspace,
  isMobileLayout = false,
}) => {
  const [password, setPassword] = useState("");
  const [showAdvancedSecurity, setShowAdvancedSecurity] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleStandardSignIn = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage("Password authentication is disabled. Please sign in with your WebAuthn security key or passkey.");
  };

  const handleTriggerRealPasskey = async () => {
    onStartVerification();
    setIsVerifying(true);
    setErrorMessage(null);

    try {
      const result = await executeRealWebAuthnAuthentication(sentinelxId);
      setIsVerifying(false);
      onVerifySuccess(result.access_token);
      setTimeout(() => {
        onEnterWorkspace(result.role);
      }, 1200);
    } catch (err) {
      setIsVerifying(false);
      const msg = err instanceof Error ? err.message : "WebAuthn authentication failed.";
      setErrorMessage(msg);
      onVerifyFailure(msg);
    }
  };

  return (
    <div className="secure-access-card" id="returning-user-card">
      {/* ── State 1: Returning User Sign-In ── */}
      {verificationState === "ID_ENTRY" && (
        <form onSubmit={handleStandardSignIn} id="returning-user-signin-form">
          <div className="card-header-block">
            <div className="access-returning-badge">
              <span>●</span>
              <span>RETURNING OPERATOR SIGN-IN · FIDO2 / WEBAUTHN</span>
            </div>
            <h2 className="card-title">AlgoFortis Sign In</h2>
            <p className="card-subtitle">
              Hardware-backed WebAuthn / Passkey authentication is mandatory.
            </p>
          </div>

          <div className="dev-preview-banner" style={{ marginBottom: "14px" }}>
            <span className="banner-tag">AUTH POLICY</span>
            <span>FIDO2 / WEBAUTHN MANDATORY · Password login is disabled by architecture contract.</span>
          </div>

          {errorMessage && (
            <div className="auth-error-alert" id="returning-auth-error-message" role="alert" aria-live="polite" style={{ marginBottom: "14px" }}>
              <span className="auth-error-text">{errorMessage}</span>
            </div>
          )}

          <div className="form-field-group">
            <label htmlFor="sentinelx-id-input" className="field-label">
              User ID or email (blank for local Owner)
            </label>
            <div className="field-input-wrapper">
              <input
                id="sentinelx-id-input"
                type="text"
                className="field-input mono-input"
                placeholder="AF-U-XXXX-XXXX / SX-U-... or registered email"
                value={sentinelxId}
                onChange={(e) => onIdChange(e.target.value)}
                autoComplete="username"
                disabled={isVerifying}
              />
            </div>
          </div>

          <div className="form-field-group">
            <div className="field-label-row">
              <label htmlFor="returning-password-input" className="field-label">
                Password
              </label>
              <span className="field-policy-note">Disabled by architecture contract</span>
            </div>
            <div className="field-input-wrapper disabled-input">
              <input
                id="returning-password-input"
                type="password"
                className="field-input"
                placeholder="••••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                disabled
              />
            </div>
          </div>

          <div className="auth-action-stack">
            <button
              type="button"
              className="btn-passkey-hardware"
              onClick={handleTriggerRealPasskey}
              disabled={isVerifying}
              id="fido2-hardware-login-btn"
            >
              <span className="passkey-icon">🔑</span>
              <span>{isVerifying ? "VERIFYING SECURITY KEY..." : "AUTHENTICATE WITH WEBAUTHN / PASSKEY"}</span>
            </button>

            <button
              type="submit"
              className="btn-primary-continue"
              disabled
              id="standard-signin-disabled-btn"
              style={{ opacity: 0.45, cursor: "not-allowed" }}
            >
              SIGN IN WITH PASSWORD (DISABLED)
            </button>
          </div>

          <div className="card-footer-actions">
            <button
              type="button"
              className="footer-link-btn"
              onClick={onSwitchToAccessGate}
              id="nav-to-first-time-activation"
            >
              First time? Redeem 24h Activation Invitation
            </button>
            <button
              type="button"
              className="footer-link-btn"
              onClick={onSwitchToRecovery}
              id="nav-to-recovery-btn"
            >
              Need help or account recovery?
            </button>
          </div>
        </form>
      )}

      {/* ── State 2: FIDO2 Hardware Challenge Active ── */}
      {verificationState === "CHALLENGE_ACTIVE" && (
        <div className="verification-status-panel" id="fido2-challenge-active-panel">
          <div className="fido2-pulse-indicator">
            <div className="fido2-spinner-ring" />
            <span className="fido2-icon">🔑</span>
          </div>

          <h3 className="status-panel-title">WebAuthn Assertion Active</h3>
          <p className="status-panel-desc">
            Touch your registered hardware security key, complete biometric verification, or confirm the Windows Hello prompt.
          </p>

          <div className="telemetry-box">
            <div className="telemetry-row">
              <span className="telemetry-key">AUTHENTICATION CHANNEL:</span>
              <span className="telemetry-val text-accent">FIDO2 / WEBAUTHN</span>
            </div>
            <div className="telemetry-row">
              <span className="telemetry-key">CHALLENGE TIMEOUT:</span>
              <span className="telemetry-val">60s BOUNDED</span>
            </div>
          </div>

          <div className="card-footer-actions">
            <button
              type="button"
              className="footer-link-btn"
              onClick={() => onVerifyFailure("Authentication cancelled by user.")}
              id="cancel-challenge-btn"
            >
              Cancel &amp; Return
            </button>
          </div>
        </div>
      )}

      {/* ── State 3: Verification Success ── */}
      {verificationState === "VERIFICATION_SUCCESS" && (
        <div className="verification-status-panel success" id="fido2-verification-success-panel">
          <div className="status-icon-badge success">
            <span>✓</span>
          </div>

          <h3 className="status-panel-title">WebAuthn Verified</h3>
          <p className="status-panel-desc">
            Operator identity attested by hardware passkey. Establishing workspace session...
          </p>

          <div className="telemetry-box">
            <div className="telemetry-row">
              <span className="telemetry-key">ATTESTATION STATUS:</span>
              <span className="telemetry-val text-success">PASSED · ZERO-KNOWLEDGE</span>
            </div>
            <div className="telemetry-row">
              <span className="telemetry-key">WORKSPACE SESSION:</span>
              <span className="telemetry-val">ISSUED</span>
            </div>
          </div>
        </div>
      )}

      {/* ── State 4: Verification Failed ── */}
      {verificationState === "VERIFICATION_FAILED" && (
        <div className="verification-status-panel failed" id="fido2-verification-failed-panel">
          <div className="status-icon-badge failed">
            <span>✕</span>
          </div>

          <h3 className="status-panel-title">Authentication Failed</h3>
          <p className="status-panel-desc">
            {errorMessage || "The security key signature was rejected or the request timed out."}
          </p>

          <div className="auth-action-stack" style={{ marginTop: "16px" }}>
            <button
              type="button"
              className="btn-passkey-hardware"
              onClick={handleTriggerRealPasskey}
              id="retry-fido2-btn"
            >
              <span className="passkey-icon">↺</span>
              <span>RETRY WEBAUTHN / PASSKEY</span>
            </button>
            <button
              type="button"
              className="btn-secondary-action"
              onClick={onSwitchToAccessGate}
              id="failed-return-to-gate-btn"
            >
              Return to Gate
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
