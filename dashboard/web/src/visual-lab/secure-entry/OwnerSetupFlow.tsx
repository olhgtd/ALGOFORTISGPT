import React, { useState } from "react";
import {
  executeRealWebAuthnBootstrapRegistration,
  executeRealWebAuthnAuthentication,
} from "./webauthn-client";

interface OwnerSetupFlowProps {
  onBackToGate: () => void;
  onLaunchOwnerWorkspace: () => void;
}

function sanitizeError(msg: string, token: string): string {
  if (!msg) return "Owner setup operation failed.";
  let cleaned = msg;
  if (token && token.trim()) {
    cleaned = cleaned.replaceAll(token.trim(), "[REDACTED_BOOTSTRAP_TOKEN]");
  }
  return cleaned;
}

export const OwnerSetupFlow: React.FC<OwnerSetupFlowProps> = ({
  onBackToGate,
  onLaunchOwnerWorkspace,
}) => {
  const [ownerName, setOwnerName] = useState("Root Administrator");
  const [ownerEmail, setOwnerEmail] = useState("owner@algofortis.internal");
  const [bootstrapToken, setBootstrapToken] = useState("");
  const [isProvisioning, setIsProvisioning] = useState(false);
  const [isProvisioned, setIsProvisioned] = useState(false);
  const [isAuthenticating, setIsAuthenticating] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);

  const handleProvision = async (e: React.FormEvent) => {
    e.preventDefault();
    const cleanToken = bootstrapToken.trim();
    if (!ownerName.trim() || !ownerEmail.trim()) {
      setErrorMessage("Owner name and email are required.");
      return;
    }
    if (!cleanToken) {
      setErrorMessage("One-time bootstrap authorization token is required.");
      return;
    }

    setIsProvisioning(true);
    setErrorMessage(null);

    try {
      await executeRealWebAuthnBootstrapRegistration(cleanToken, `Owner Key (${ownerName.trim()})`);
      setIsProvisioning(false);
      setIsProvisioned(true);
    } catch (err) {
      setIsProvisioning(false);
      const raw = err instanceof Error ? err.message : "Bootstrap registration failed.";
      setErrorMessage(sanitizeError(raw, cleanToken));
    }
  };

  const handleAuthenticateAndLaunch = async () => {
    setIsAuthenticating(true);
    setAuthError(null);

    try {
      await executeRealWebAuthnAuthentication();
      setIsAuthenticating(false);
      onLaunchOwnerWorkspace();
    } catch (err) {
      setIsAuthenticating(false);
      const raw = err instanceof Error ? err.message : "Authentication failed.";
      setAuthError(raw);
    }
  };

  return (
    <div className="secure-access-card" id="owner-setup-card">
      <div className="card-header-block">
        <div className="access-returning-badge">
          <span>●</span>
          <span>ROOT AUTHORITY INITIALIZATION · OD-AUTH-06</span>
        </div>
        <h2 className="card-title">AlgoFortis Owner Provisioning</h2>
        <p className="card-subtitle">
          Initialize the primary hardware-backed Owner authenticator.
        </p>
      </div>

      {!isProvisioned ? (
        <form onSubmit={handleProvision} id="owner-provision-form">
          {errorMessage && (
            <div className="auth-error-alert" id="owner-setup-error-message" role="alert" aria-live="polite" style={{ marginBottom: "14px" }}>
              <span className="auth-error-text">{errorMessage}</span>
            </div>
          )}

          <div className="form-field-group">
            <label htmlFor="owner-name-input" className="field-label">
              Owner Display Name
            </label>
            <div className="field-input-wrapper">
              <input
                id="owner-name-input"
                type="text"
                className="field-input"
                placeholder="Root Administrator"
                value={ownerName}
                onChange={(e) => setOwnerName(e.target.value)}
                disabled={isProvisioning}
                required
              />
            </div>
          </div>

          <div className="form-field-group">
            <label htmlFor="owner-email-input" className="field-label">
              Owner Email Address
            </label>
            <div className="field-input-wrapper">
              <input
                id="owner-email-input"
                type="email"
                className="field-input"
                placeholder="owner@algofortis.internal"
                value={ownerEmail}
                onChange={(e) => setOwnerEmail(e.target.value)}
                disabled={isProvisioning}
                required
              />
            </div>
          </div>

          <div className="form-field-group">
            <label htmlFor="bootstrap-token-input" className="field-label">
              Bootstrap Token
            </label>
            <div className="field-input-wrapper">
              <input
                id="bootstrap-token-input"
                type="password"
                className="field-input mono-input"
                placeholder="SX-BST-..."
                value={bootstrapToken}
                onChange={(e) => setBootstrapToken(e.target.value)}
                disabled={isProvisioning}
                required
                autoComplete="off"
              />
            </div>
          </div>

          <div className="auth-action-stack">
            <button
              type="submit"
              className="btn-passkey-hardware"
              disabled={isProvisioning || !bootstrapToken.trim()}
              id="provision-owner-btn"
            >
              <span className="passkey-icon">🛡</span>
              <span>{isProvisioning ? "REGISTERING SECURITY KEY..." : "ENROLL OWNER WEBAUTHN KEY"}</span>
            </button>
          </div>

          <div className="card-footer-actions">
            <button
              type="button"
              className="footer-link-btn"
              onClick={onBackToGate}
              disabled={isProvisioning}
              id="owner-back-to-gate-btn"
            >
              Return to Access Gate
            </button>
          </div>
        </form>
      ) : (
        <div className="verification-status-panel success" id="owner-provision-success-panel">
          <div className="status-icon-badge success">
            <span>✓</span>
          </div>

          <h3 className="status-panel-title">Owner Key Enrolled</h3>
          <p className="status-panel-desc">
            Primary Owner WebAuthn credential registered. Authenticate with your key to enter the Owner Control Center.
          </p>

          {authError && (
            <div className="auth-error-alert" id="owner-auth-error-message" role="alert" aria-live="polite" style={{ marginTop: "14px" }}>
              <span className="auth-error-text">{authError}</span>
            </div>
          )}

          <div className="auth-action-stack" style={{ marginTop: "18px" }}>
            <button
              type="button"
              className="btn-passkey-hardware"
              onClick={handleAuthenticateAndLaunch}
              disabled={isAuthenticating}
              id="owner-authenticate-launch-btn"
            >
              <span className="passkey-icon">🔑</span>
              <span>{isAuthenticating ? "AUTHENTICATING..." : "ENTER OWNER WORKSPACE"}</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
