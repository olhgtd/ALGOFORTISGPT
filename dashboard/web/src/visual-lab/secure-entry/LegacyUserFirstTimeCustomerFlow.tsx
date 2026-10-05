import React, { useState } from "react";
import type { AccessGateStep } from "./types";
import { api, setSessionToken } from "../../api";

interface LegacyUserFirstTimeCustomerFlowProps {
  accessId: string;
  onAccessIdChange: (code: string) => void;
  gateStep: AccessGateStep;
  onGateStepChange: (step: AccessGateStep) => void;
  onSwitchToReturningUser?: () => void;
  onSwitchToOwnerSetup?: () => void;
  onSwitchToRecovery?: () => void;
  onCompleteActivation?: (token: string, workspace: "user" | "owner") => void;
  isDevMode?: boolean;
}

export const LegacyUserFirstTimeCustomerFlow: React.FC<LegacyUserFirstTimeCustomerFlowProps> = ({
  accessId,
  onAccessIdChange,
  gateStep,
  onGateStepChange,
  onSwitchToReturningUser,
  onCompleteActivation,
  isDevMode = false,
}) => {
  // Screen 2 inputs (Credentials)
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  // States
  const [isValidating, setIsValidating] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  /* ── Screen 1: Validate Access ID ── */
  const handleValidateAccessId = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanId = (accessId || "").trim().toUpperCase();
    if (!cleanId) return;

    setIsValidating(true);
    setAuthError(null);

    try {
      const res = await api.localAccessValidate({ access_id: cleanId });
      if (res.valid) {
        if (res.email) {
          setEmail(res.email);
        }
        setAuthError(null);
        onGateStepChange("CREATE_ACCOUNT");
      } else {
        onGateStepChange("ACCESS_DENIED");
      }
    } catch (err: any) {
      // If server returned 404 or 403, fail-closed calmly to Access Denied
      onGateStepChange("ACCESS_DENIED");
    } finally {
      setIsValidating(false);
    }
  };

  /* ── Screen 2: Submit Account Email + Password ── */
  const handleAccountSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanEmail = email.trim();
    if (!cleanEmail) {
      setAuthError("Please enter your account email address.");
      return;
    }
    if (!password || password.length < 8) {
      setAuthError("Password must be at least 8 characters long.");
      return;
    }
    if (password !== confirmPassword) {
      setAuthError("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);
    setAuthError(null);

    try {
      const res = await api.localAccessActivate({
        access_id: accessId.trim(),
        email: cleanEmail,
        password,
        confirm_password: confirmPassword,
      });

      // Persist activation marker and session
      try {
        localStorage.setItem("algofortis_user_activated", "true");
      } catch {}

      setSessionToken(res.access_token);

      if (onCompleteActivation) {
        onCompleteActivation(res.access_token, res.role.toLowerCase() as any);
      }
    } catch (err: any) {
      setAuthError(err.message || "Failed to activate user account. Please verify credentials.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="secure-floating-form" id="access-gate-card">
      {/* ──
          SCREEN 1: ACCESS GATE (ACCESS ID ONLY)
          ── */}
      {gateStep === "ENTER_ACCESS_ID" && (
        <form onSubmit={handleValidateAccessId} id="access-gate-form">
          <div className="card-header-block">
            <h2 className="card-title">AlgoFortis Access</h2>
            <p className="card-subtitle">
              Enter your invite-only Access ID to proceed.
            </p>
          </div>

          {authError && (
            <div className="auth-error-alert" id="auth-error-alert" role="alert" style={{ marginBottom: "14px" }}>
              <span className="auth-error-text">{authError}</span>
            </div>
          )}

          <div className="form-field-group">
            <label htmlFor="access-id-input" className="field-label">
              AlgoFortis Access ID
            </label>
            <div className="field-input-wrapper">
              <input
                id="access-id-input"
                type="text"
                className="field-input mono-input"
                placeholder="[ access code ]"
                value={accessId}
                onChange={(e) => onAccessIdChange(e.target.value.toUpperCase())}
                autoFocus
                spellCheck={false}
                autoComplete="off"
                disabled={isValidating}
              />
            </div>
          </div>

          <button
            type="submit"
            className="btn-primary-continue"
            id="access-gate-continue-btn"
            disabled={!accessId.trim() || isValidating}
          >
            <span>{isValidating ? "VALIDATING..." : "CONTINUE"}</span>
            {!isValidating && <span style={{ fontSize: "14px" }}>→</span>}
          </button>

          {onSwitchToReturningUser && (
            <div className="card-footer-actions" style={{ marginTop: "14px", textAlign: "center" }}>
              <button
                type="button"
                className="footer-link-btn"
                onClick={onSwitchToReturningUser}
                id="switch-to-login-btn"
                disabled={isValidating}
              >
                Already activated? Sign in with email and password
              </button>
            </div>
          )}
        </form>
      )}

      {/* ──
          SCREEN 2: ACCOUNT ACTIVATION (EMAIL + PASSWORD)
          ── */}
      {(gateStep === "CREATE_ACCOUNT" || gateStep === "VERIFY_IDENTITY") && (
        <form onSubmit={handleAccountSubmit} id="account-login-form">
          <div className="card-header-block">
            <div className="access-verified-badge">
              <span className="verified-check">✓</span>
              <span>ACCESS ID VERIFIED: {accessId}</span>
            </div>
            <h2 className="card-title">Create Account</h2>
            <p className="card-subtitle">
              Create your account credentials to access your workstation.
            </p>
          </div>

          {authError && (
            <div className="auth-error-alert" id="auth-error-alert" role="alert" style={{ marginBottom: "14px" }}>
              <span className="auth-error-text">{authError}</span>
            </div>
          )}

          <div className="form-field-group">
            <label htmlFor="account-email-input" className="field-label">
              Email Address
            </label>
            <div className="field-input-wrapper">
              <input
                id="account-email-input"
                type="email"
                className="field-input"
                placeholder="e.g. trader@algofortis.internal"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  setAuthError(null);
                }}
                autoFocus
                spellCheck={false}
                autoComplete="email"
                required
                disabled={isSubmitting}
              />
            </div>
          </div>

          <div className="form-field-group">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <label htmlFor="account-password-input" className="field-label">
                Create Password
              </label>
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={{
                  background: "none",
                  border: "none",
                  color: "#94a3b8",
                  fontSize: "11px",
                  cursor: "pointer",
                  padding: 0,
                }}
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
            <div className="field-input-wrapper">
              <input
                id="account-password-input"
                type={showPassword ? "text" : "password"}
                className="field-input"
                placeholder="Minimum 8 characters"
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value);
                  setAuthError(null);
                }}
                autoComplete="new-password"
                required
                disabled={isSubmitting}
              />
            </div>
          </div>

          <div className="form-field-group">
            <label htmlFor="account-confirm-password-input" className="field-label">
              Confirm Password
            </label>
            <div className="field-input-wrapper">
              <input
                id="account-confirm-password-input"
                type={showPassword ? "text" : "password"}
                className="field-input"
                placeholder="Confirm password"
                value={confirmPassword}
                onChange={(e) => {
                  setConfirmPassword(e.target.value);
                  setAuthError(null);
                }}
                autoComplete="new-password"
                required
                disabled={isSubmitting}
              />
            </div>
          </div>

          <button
            type="submit"
            className="btn-primary-continue"
            id="account-activate-btn"
            disabled={!email.trim() || password.length < 8 || password !== confirmPassword || isSubmitting}
          >
            <span>{isSubmitting ? "CREATING ACCOUNT..." : "CREATE ACCOUNT"}</span>
            {!isSubmitting && <span style={{ fontSize: "14px" }}>→</span>}
          </button>

          <div className="card-footer-actions">
            <button
              type="button"
              className="footer-link-btn"
              onClick={() => {
                setAuthError(null);
                onGateStepChange("ENTER_ACCESS_ID");
              }}
              id="back-to-access-id-btn"
              disabled={isSubmitting}
            >
              Back to Access ID
            </button>
          </div>
        </form>
      )}

      {/* ──
          SCREEN 3: ACCESS NOT AUTHORIZED (CALM, FAIL-CLOSED, 0 LEAKAGE)
          ── */}
      {gateStep === "ACCESS_DENIED" && (
        <div className="access-denied-view" id="access-denied-view">
          <div className="access-denied-icon-box">
            <span className="denied-cross" style={{ color: "#ef4444", fontSize: "28px" }}>✕</span>
          </div>

          <div className="card-header-block" style={{ marginBottom: "16px", textAlign: "center" }}>
            <h2 className="card-title" style={{ color: "#ffffff", fontSize: "20px", letterSpacing: "0.02em" }}>
              ACCESS NOT AUTHORIZED
            </h2>
            <p className="card-subtitle" style={{ fontSize: "13px", lineHeight: "1.5", margin: "8px auto 0", maxWidth: "38ch" }}>
              This AlgoFortis installation is invite-only. The presented Access ID was not recognized or is no longer valid.
            </p>
          </div>

          <button
            type="button"
            className="btn-primary-continue"
            onClick={() => {
              setAuthError(null);
              onGateStepChange("ENTER_ACCESS_ID");
            }}
            id="try-another-access-id-btn"
            style={{ marginTop: "8px" }}
          >
            <span>TRY ANOTHER ACCESS ID</span>
          </button>
        </div>
      )}
    </div>
  );
};
