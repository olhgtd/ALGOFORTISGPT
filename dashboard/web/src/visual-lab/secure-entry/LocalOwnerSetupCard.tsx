import React, { useState } from "react";
import { api, setSessionToken } from "../../api";

interface LocalOwnerSetupCardProps {
  onSetupSuccess: () => void;
  onSwitchToLogin?: () => void;
}

export const LocalOwnerSetupCard: React.FC<LocalOwnerSetupCardProps> = ({ onSetupSuccess, onSwitchToLogin }) => {
  const [displayName, setDisplayName] = useState("Super Owner");
  const [email, setEmail] = useState("");
  const [bootstrapToken, setBootstrapToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null);
  const [savedToken, setSavedToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    const cleanName = displayName.trim() || "Super Owner";
    const cleanEmail = email.trim();
    const cleanToken = bootstrapToken.trim();

    if (!cleanEmail || !cleanEmail.includes("@")) {
      setErrorMessage("Please enter a valid email address.");
      return;
    }
    if (!cleanToken) {
      setErrorMessage("Bootstrap authorization token is required.");
      return;
    }
    if (password.length < 8) {
      setErrorMessage("Password must be at least 8 characters long.");
      return;
    }
    if (password !== confirmPassword) {
      setErrorMessage("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await api.localOwnerSetup({
        display_name: cleanName,
        email: cleanEmail,
        bootstrap_token: cleanToken,
        password,
        confirm_password: confirmPassword,
      });

      if (res.recovery_codes && res.recovery_codes.length > 0) {
        setSavedToken(res.access_token);
        setRecoveryCodes(res.recovery_codes);
        setIsSubmitting(false);
      } else {
        setSessionToken(res.access_token);
        onSetupSuccess();
      }
    } catch (err: any) {
      setIsSubmitting(false);
      const msg = err instanceof Error ? err.message : "Failed to initialize owner.";
      setErrorMessage(msg);
    }
  };

  const handleCopyCodes = () => {
    if (!recoveryCodes) return;
    navigator.clipboard.writeText(recoveryCodes.join("\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 3000);
  };

  const handleCompleteSetup = () => {
    if (savedToken) {
      setSessionToken(savedToken);
    }
    onSetupSuccess();
  };

  if (recoveryCodes) {
    return (
      <div className="secure-access-card" id="recovery-codes-card">
        <div className="access-gate-badge" style={{ marginBottom: "12px" }}>
          <span style={{ color: "#10b981" }}>●</span>
          <span>SECURITY RECOVERY CODES</span>
        </div>

        <h2 className="card-title" style={{ fontSize: "19px", fontWeight: 700, letterSpacing: "0.04em", color: "#f8fafc" }}>
          SAVE YOUR RECOVERY CODES
        </h2>
        <p className="card-subtitle" style={{ fontSize: "12.5px", color: "#94a3b8", marginBottom: "16px" }}>
          These 8 single-use codes are the <strong style={{ color: "#f59e0b" }}>ONLY</strong> way to recover workspace access if you forget your password. They will <strong style={{ color: "#ef4444" }}>NEVER</strong> be displayed again.
        </p>

        <div
          style={{
            background: "rgba(15, 23, 42, 0.85)",
            border: "1px solid rgba(51, 65, 85, 0.8)",
            borderRadius: "6px",
            padding: "12px",
            marginBottom: "16px",
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "8px",
          }}
          id="recovery-codes-grid"
        >
          {recoveryCodes.map((c, i) => (
            <div
              key={i}
              style={{
                fontFamily: "monospace",
                fontSize: "12.5px",
                fontWeight: 600,
                color: "#38bdf8",
                background: "rgba(30, 41, 59, 0.7)",
                padding: "6px 10px",
                borderRadius: "4px",
                textAlign: "center",
                letterSpacing: "0.06em",
              }}
            >
              {c}
            </div>
          ))}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          <button
            type="button"
            id="copy-recovery-codes-btn"
            onClick={handleCopyCodes}
            style={{
              background: "rgba(30, 41, 59, 0.9)",
              border: "1px solid rgba(56, 189, 248, 0.4)",
              color: copied ? "#10b981" : "#38bdf8",
              fontWeight: 600,
              fontSize: "12px",
              padding: "10px 16px",
              borderRadius: "6px",
              cursor: "pointer",
              transition: "all 0.15s ease",
            }}
          >
            {copied ? "✓ COPIED TO CLIPBOARD" : "COPY RECOVERY CODES"}
          </button>

          <button
            type="button"
            id="confirm-recovery-saved-btn"
            onClick={handleCompleteSetup}
            style={{
              background: "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
              color: "#0f172a",
              fontWeight: 700,
              fontSize: "13px",
              padding: "11px 16px",
              borderRadius: "6px",
              border: "none",
              cursor: "pointer",
              letterSpacing: "0.04em",
            }}
          >
            I HAVE SAVED THESE CODES
          </button>
        </div>

        <div style={{ marginTop: "14px", textAlign: "center", fontSize: "11px", color: "#64748b" }}>
          Plaintext codes are never stored in the database. Only cryptographic hashes are retained.
        </div>
      </div>
    );
  }

  return (
    <div className="secure-access-card" id="owner-setup-card">
      <div className="access-gate-badge" style={{ marginBottom: "12px" }}>
        <span style={{ color: "#f59e0b" }}>●</span>
        <span>FIRST-RUN INITIALIZATION</span>
      </div>

      <h2 className="card-title" style={{ fontSize: "20px", fontWeight: 700, letterSpacing: "0.04em", color: "#f8fafc" }}>
        ALGOfORTIS OWNER SETUP
      </h2>
      <p className="card-subtitle" style={{ fontSize: "12.5px", color: "#94a3b8", marginBottom: "20px" }}>
        Provision platform Super Owner (<strong style={{ color: "#f59e0b" }}>OWNER-001</strong>). The bootstrap token is required once only.
      </p>

      {errorMessage && (
        <div
          role="alert"
          style={{
            background: "rgba(239, 68, 68, 0.12)",
            border: "1px solid rgba(239, 68, 68, 0.35)",
            borderRadius: "6px",
            padding: "10px 14px",
            marginBottom: "16px",
            color: "#fca5a5",
            fontSize: "12px",
            lineHeight: 1.4,
          }}
        >
          {errorMessage}
        </div>
      )}

      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "14px", width: "100%" }}>
        <div className="form-field-group">
          <label htmlFor="owner-display-name" className="field-label" style={{ fontSize: "11px", fontWeight: 600, color: "#cbd5e1" }}>
            Owner Display Name
          </label>
          <div className="field-input-wrapper">
            <input
              id="owner-display-name"
              type="text"
              className="field-input"
              placeholder="Super Owner"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              disabled={isSubmitting}
              autoComplete="name"
              required
            />
          </div>
        </div>

        <div className="form-field-group">
          <label htmlFor="owner-email" className="field-label" style={{ fontSize: "11px", fontWeight: 600, color: "#cbd5e1" }}>
            Owner Email
          </label>
          <div className="field-input-wrapper">
            <input
              id="owner-email"
              type="email"
              className="field-input"
              placeholder="owner@algofortis.internal"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={isSubmitting}
              autoComplete="email"
              required
            />
          </div>
        </div>

        <div className="form-field-group">
          <label htmlFor="owner-bootstrap-token" className="field-label" style={{ fontSize: "11px", fontWeight: 600, color: "#cbd5e1" }}>
            Bootstrap Token
          </label>
          <div className="field-input-wrapper">
            <input
              id="owner-bootstrap-token"
              type="password"
              className="field-input mono-input"
              placeholder="Paste one-time bootstrap token"
              value={bootstrapToken}
              onChange={(e) => setBootstrapToken(e.target.value)}
              disabled={isSubmitting}
              autoComplete="off"
              required
            />
          </div>
        </div>

        <div className="form-field-group">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <label htmlFor="owner-password" className="field-label" style={{ fontSize: "11px", fontWeight: 600, color: "#cbd5e1" }}>
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
              id="owner-password"
              type={showPassword ? "text" : "password"}
              className="field-input"
              placeholder="Minimum 8 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isSubmitting}
              autoComplete="new-password"
              required
            />
          </div>
        </div>

        <div className="form-field-group">
          <label htmlFor="owner-confirm-password" className="field-label" style={{ fontSize: "11px", fontWeight: 600, color: "#cbd5e1" }}>
            Confirm Password
          </label>
          <div className="field-input-wrapper">
            <input
              id="owner-confirm-password"
              type={showPassword ? "text" : "password"}
              className="field-input"
              placeholder="Confirm password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={isSubmitting}
              autoComplete="new-password"
              required
            />
          </div>
        </div>

        <div style={{ marginTop: "10px" }}>
          <button
            type="submit"
            className="btn-primary-continue"
            id="create-owner-btn"
            disabled={isSubmitting || !bootstrapToken.trim() || !email.trim() || password.length < 8}
            style={{
              background: "#f59e0b",
              color: "#090e17",
              borderColor: "#d97706",
              fontWeight: 700,
            }}
          >
            {isSubmitting ? "INITIALIZING OWNER-001..." : "CREATE OWNER"}
          </button>
        </div>
      </form>

      {onSwitchToLogin && (
        <div className="card-footer-actions" style={{ marginTop: "14px" }}>
          <button type="button" className="footer-link-btn" onClick={onSwitchToLogin} id="owner-setup-to-login">
            OWNER-001 already exists? Sign in
          </button>
        </div>
      )}
    </div>
  );
};
