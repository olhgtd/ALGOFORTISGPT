import React, { useEffect, useState } from "react";
import type { AccessGateStep } from "./types";
import { api } from "../../api";

interface FirstTimeCustomerFlowProps {
  accessId: string;
  onAccessIdChange: (code: string) => void;
  gateStep: AccessGateStep;
  onGateStepChange: (step: AccessGateStep) => void;
  onSwitchToReturningUser?: () => void;
  onSwitchToOwnerSetup?: () => void;
  onSwitchToRecovery?: () => void;
  isDevMode?: boolean;
}

export const FirstTimeCustomerFlow: React.FC<FirstTimeCustomerFlowProps> = ({
  accessId,
  onAccessIdChange,
  onSwitchToReturningUser,
}) => {
  const [identifier, setIdentifier] = useState(accessId);
  const [code, setCode] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activated, setActivated] = useState(false);

  useEffect(() => {
    if (accessId && accessId !== identifier) setIdentifier(accessId);
  }, [accessId, identifier]);

  const changeIdentifier = (value: string) => {
    const normalized = value.toUpperCase();
    setIdentifier(normalized);
    onAccessIdChange(normalized);
  };

  const activate = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);

    const cleanIdentifier = identifier.trim();
    const cleanCode = code.trim();
    const cleanEmail = email.trim();
    if (!cleanIdentifier || !cleanCode || !cleanEmail) {
      setError("User ID, activation code, and email are required.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setBusy(true);
    try {
      await api.passwordActivate({
        identifier: cleanIdentifier,
        activation_code: cleanCode,
        email: cleanEmail,
        password,
        confirm_password: confirmPassword,
      });
      setCode("");
      setPassword("");
      setConfirmPassword("");
      setActivated(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Activation unavailable.";
      setError(message);
      setPassword("");
      setConfirmPassword("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="secure-floating-form" id="access-gate-card">
      <div className="card-header-block">
        <h2 className="card-title">AlgoFortis User Activation</h2>
        <p className="card-subtitle">
          Use the User ID and one-time activation code issued by your Owner, then bind your email and password.
        </p>
      </div>

      {error && <div className="auth-error-alert" role="alert" id="activation-error">{error}</div>}

      {activated ? (
        <div id="user-enrollment-complete" className="verification-status-panel success">
          <div className="status-icon-badge success"><span>✓</span></div>
          <h3 className="status-panel-title">Account Activated</h3>
          <p className="status-panel-desc">Your AlgoFortis account is active. Sign in with your User ID or email and password.</p>
          <button className="btn-primary-continue" onClick={onSwitchToReturningUser} id="activation-signin-btn" type="button">
            SIGN IN
          </button>
        </div>
      ) : (
        <form onSubmit={activate} id="access-gate-form">
          <div className="form-field-group">
            <label className="field-label" htmlFor="access-id-input">AlgoFortis User ID</label>
            <input className="field-input mono-input" id="access-id-input" placeholder="AF-U-XXXX-XXXX / SX-U-..." value={identifier} onChange={(event) => changeIdentifier(event.target.value)} autoComplete="username" required disabled={busy} />
          </div>

          <div className="form-field-group">
            <label className="field-label" htmlFor="activation-code-input">Activation Code</label>
            <input className="field-input mono-input" id="activation-code-input" type="password" value={code} onChange={(event) => setCode(event.target.value)} autoComplete="off" required disabled={busy} />
          </div>

          <div className="form-field-group">
            <label className="field-label" htmlFor="activation-email-input">Email Address</label>
            <input className="field-input" id="activation-email-input" type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required disabled={busy} />
          </div>

          <div className="form-field-group">
            <div className="field-label-row">
              <label className="field-label" htmlFor="activation-password-input">Create Password</label>
              <button type="button" className="footer-link-btn" onClick={() => setShowPassword((value) => !value)} disabled={busy}>
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
            <input className="field-input" id="activation-password-input" type={showPassword ? "text" : "password"} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" required disabled={busy} />
          </div>

          <div className="form-field-group">
            <label className="field-label" htmlFor="activation-confirm-password-input">Confirm Password</label>
            <input className="field-input" id="activation-confirm-password-input" type={showPassword ? "text" : "password"} value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} autoComplete="new-password" required disabled={busy} />
          </div>

          <button className="btn-primary-continue" id="access-gate-continue-btn" disabled={busy || !identifier.trim() || !code.trim() || !email.trim() || password.length < 8}>
            {busy ? "ACTIVATING..." : "ACTIVATE ACCOUNT"}
          </button>
        </form>
      )}

      {!activated && (
        <button className="footer-link-btn" onClick={onSwitchToReturningUser} disabled={busy} type="button">
          Already activated? Sign in
        </button>
      )}
    </div>
  );
};
