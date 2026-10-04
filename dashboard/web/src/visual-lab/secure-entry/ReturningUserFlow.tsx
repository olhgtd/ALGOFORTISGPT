import React, { useEffect, useState } from "react";
import type { VerificationState } from "./types";
import { api, clearSessionToken, setSessionToken } from "../../api";

interface ReturningUserFlowProps {
  algofortisId: string;
  onIdChange: (id: string) => void;
  verificationState: VerificationState;
  onStartVerification: () => void;
  onVerifySuccess: (token?: string) => void;
  onVerifyFailure: (error: string) => void;
  onSwitchToAccessGate: () => void;
  onSwitchToOwnerSetup: () => void;
  onSwitchToRecovery: () => void;
  requiredRole?: "OWNER" | "USER";
  onEnterWorkspace: (role?: "OWNER" | "USER") => void;
  isMobileLayout?: boolean;
}

export const ReturningUserFlow: React.FC<ReturningUserFlowProps> = ({
  algofortisId,
  onIdChange,
  onVerifySuccess,
  onVerifyFailure,
  onSwitchToAccessGate,
  onSwitchToRecovery,
  requiredRole,
  onEnterWorkspace,
}) => {
  const [identifier, setIdentifier] = useState(algofortisId);
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (algofortisId && algofortisId !== identifier) setIdentifier(algofortisId);
  }, [identifier, algofortisId]);

  const changeIdentifier = (value: string) => {
    setIdentifier(value);
    onIdChange(value);
  };

  const handleStandardSignIn = async (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage(null);
    const cleanIdentifier = identifier.trim();
    if (!cleanIdentifier || !password) {
      setErrorMessage("User ID/email and password are required.");
      return;
    }

    setIsVerifying(true);
    try {
      const result = await api.passwordLogin({ identifier: cleanIdentifier, password });
      if (requiredRole && result.role !== requiredRole) {
        clearSessionToken();
        setPassword("");
        const message = requiredRole === "USER"
          ? "This account belongs to the Owner workspace. Open AlgoFortis Owner."
          : "This account belongs to the User workspace.";
        setErrorMessage(message);
        onVerifyFailure(message);
        return;
      }
      setSessionToken(result.access_token);
      setPassword("");
      onVerifySuccess(result.access_token);
      // Workspace is derived only from the authoritative backend role.
      onEnterWorkspace(result.role);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Authentication unavailable.";
      setPassword("");
      setErrorMessage(message);
      onVerifyFailure(message);
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <div className="secure-access-card" id="returning-user-card">
      <form onSubmit={handleStandardSignIn} id="returning-user-signin-form">
        <div className="card-header-block">
          <div className="access-returning-badge">
            <span>●</span>
            <span>OWNER / USER · SECURE SIGN IN</span>
          </div>
          <h2 className="card-title">AlgoFortis Sign In</h2>
          <p className="card-subtitle">
            Sign in with your AlgoFortis User ID or registered email and password. Your backend account role selects the workspace.
          </p>
        </div>

        <div className="dev-preview-banner" style={{ marginBottom: "14px" }}>
          <span className="banner-tag">AUTH POLICY</span>
          <span>ONE ACCOUNT GATE · WebAuthn remains mandatory for protected Owner step-up actions.</span>
        </div>

        {errorMessage && (
          <div className="auth-error-alert" id="returning-auth-error-message" role="alert" aria-live="polite" style={{ marginBottom: "14px" }}>
            <span className="auth-error-text">{errorMessage}</span>
          </div>
        )}

        <div className="form-field-group">
          <label htmlFor="algofortis-id-input" className="field-label">User ID or Email</label>
          <div className="field-input-wrapper">
            <input
              id="algofortis-id-input"
              type="text"
              className="field-input mono-input"
              placeholder="AF-U-XXXX-XXXX / OWNER-001 / registered email"
              value={identifier}
              onChange={(event) => changeIdentifier(event.target.value)}
              autoComplete="username"
              disabled={isVerifying}
              required
            />
          </div>
        </div>

        <div className="form-field-group">
          <div className="field-label-row">
            <label htmlFor="returning-password-input" className="field-label">Password</label>
            <button
              type="button"
              className="footer-link-btn"
              onClick={() => setShowPassword((value) => !value)}
              disabled={isVerifying}
            >
              {showPassword ? "Hide" : "Show"}
            </button>
          </div>
          <div className="field-input-wrapper">
            <input
              id="returning-password-input"
              type={showPassword ? "text" : "password"}
              className="field-input"
              placeholder="••••••••••••"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              disabled={isVerifying}
              required
            />
          </div>
        </div>

        <div className="auth-action-stack">
          <button
            type="submit"
            className="btn-primary-continue"
            disabled={isVerifying || !identifier.trim() || !password}
            id="standard-signin-btn"
          >
            {isVerifying ? "AUTHENTICATING..." : "SIGN IN TO WORKSPACE"}
          </button>
        </div>

        <div className="card-footer-actions">
          <button type="button" className="footer-link-btn" onClick={onSwitchToAccessGate} id="nav-to-first-time-activation">
            First time? Activate User account
          </button>
          <button type="button" className="footer-link-btn" onClick={onSwitchToRecovery} id="nav-to-recovery-btn">
            Need help or account recovery?
          </button>
        </div>
      </form>
    </div>
  );
};
