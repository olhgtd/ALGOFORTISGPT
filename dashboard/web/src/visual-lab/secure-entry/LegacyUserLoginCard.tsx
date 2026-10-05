import React, { useState } from "react";
import { api, clearSessionToken, setSessionToken } from "../../api";

interface LegacyUserLoginCardProps {
  appTarget?: "owner" | "user";
  onLoginSuccess: () => void;
  onForgotPassword?: () => void;
  onSwitchToAccessGate?: () => void;
}

export const LegacyUserLoginCard: React.FC<LegacyUserLoginCardProps> = ({
  appTarget = "owner",
  onLoginSuccess,
  onForgotPassword,
  onSwitchToAccessGate,
}) => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    const cleanEmail = email.trim();
    if (!cleanEmail || !cleanEmail.includes("@")) {
      setErrorMessage("Please enter a valid email address.");
      return;
    }
    if (!password) {
      setErrorMessage("Password is required.");
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await api.localLogin({
        email: cleanEmail,
        password,
        app_target: appTarget,
      });

      if (appTarget === "user" && res.role !== "USER") {
        clearSessionToken();
        setPassword("");
        setIsSubmitting(false);
        setErrorMessage("ROLE_NOT_ALLOWED_FOR_APPLICATION: Owner credentials cannot access AlgoFortis User. Please launch AlgoFortis Owner.");
        return;
      }

      setSessionToken(res.access_token);
      onLoginSuccess();
    } catch (err: any) {
      setIsSubmitting(false);
      let msg = "Invalid email or password.";
      if (err instanceof Error) {
        if (err.message.includes("ROLE_NOT_ALLOWED_FOR_APPLICATION")) {
          msg = appTarget === "user"
            ? "ROLE_NOT_ALLOWED_FOR_APPLICATION: Owner credentials cannot access AlgoFortis User. Please launch AlgoFortis Owner."
            : "ROLE_NOT_ALLOWED_FOR_APPLICATION: Standard user credentials cannot access AlgoFortis Owner. Please launch AlgoFortis User.";
        } else if (err.message.includes("429") || err.message.toLowerCase().includes("too many") || err.message.toLowerCase().includes("cooldown")) {
          msg = err.message;
        } else if (err.message.includes("INVALID_EMAIL_OR_PASSWORD") || err.message.toLowerCase().includes("invalid")) {
          msg = "Invalid email or password.";
        } else {
          msg = err.message;
        }
      }
      setErrorMessage(msg);
    }
  };

  return (
    <div className="secure-access-card" id="local-login-card">
      <div className="card-header-block" style={{ textAlign: "center", marginBottom: "20px" }}>
        <h2 className="card-title" style={{ fontSize: "20px", fontWeight: 700, letterSpacing: "0.02em", color: "#ffffff" }}>
          AlgoFortis Sign In
        </h2>
        <p className="card-subtitle" style={{ fontSize: "13px", color: "var(--sx-ink-muted)", marginTop: "6px" }}>
          Enter your registered email and password to access your workspace.
        </p>
      </div>

      {errorMessage && (
        <div
          role="alert"
          id="login-error-alert"
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
          <label htmlFor="login-email" className="field-label">
            Email Address
          </label>
          <div className="field-input-wrapper">
            <input
              id="login-email"
              type="email"
              className="field-input"
              placeholder={appTarget === "owner" ? "owner@algofortis.internal" : "trader@algofortis.internal"}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={isSubmitting}
              autoComplete="email"
              autoFocus
              required
            />
          </div>
        </div>

        <div className="form-field-group">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <label htmlFor="login-password" className="field-label">
              Password
            </label>
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              style={{
                background: "transparent",
                border: "none",
                color: "#94a3b8",
                fontSize: "11px",
                cursor: "pointer",
                padding: "2px 4px",
              }}
            >
              {showPassword ? "Hide" : "Show"}
            </button>
          </div>
          <div className="field-input-wrapper">
            <input
              id="login-password"
              type={showPassword ? "text" : "password"}
              className="field-input"
              placeholder="Enter password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isSubmitting}
              autoComplete="current-password"
              required
            />
          </div>
        </div>

        <button
          type="submit"
          id="login-submit-btn"
          className="btn-primary-continue"
          disabled={isSubmitting || !email.trim() || !password}
        >
          <span>{isSubmitting ? "AUTHENTICATING..." : "SIGN IN TO WORKSPACE"}</span>
          {!isSubmitting && <span style={{ fontSize: "14px" }}> →</span>}
        </button>
      </form>

      {appTarget === "owner" && onForgotPassword && (
        <div className="card-footer-actions" style={{ marginTop: "14px", textAlign: "center" }}>
          <button
            type="button"
            className="footer-link-btn"
            id="forgot-password-btn"
            onClick={onForgotPassword}
          >
            Forgot password?
          </button>
        </div>
      )}

      {appTarget === "user" && onSwitchToAccessGate && (
        <div className="card-footer-actions" style={{ marginTop: "14px", textAlign: "center" }}>
          <button
            type="button"
            className="footer-link-btn"
            id="switch-to-access-gate-btn"
            onClick={onSwitchToAccessGate}
          >
            Have an invite? Enter Access ID
          </button>
        </div>
      )}

      <div style={{ marginTop: "16px", textAlign: "center", fontSize: "11.5px", color: "#64748b" }}>
        Protected by AlgoFortis Local Security Vault
      </div>
    </div>
  );
};
