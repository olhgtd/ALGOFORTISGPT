import React, { useState } from "react";
import { api, setSessionToken } from "../../api";

interface LocalLoginCardProps {
  onLoginSuccess: () => void;
}

export const LocalLoginCard: React.FC<LocalLoginCardProps> = ({ onLoginSuccess }) => {
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
      });

      setSessionToken(res.access_token);
      onLoginSuccess();
    } catch (err: any) {
      setIsSubmitting(false);
      let msg = "Invalid email or password.";
      if (err instanceof Error) {
        if (err.message.includes("429") || err.message.toLowerCase().includes("too many") || err.message.toLowerCase().includes("cooldown")) {
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
      <div className="access-gate-badge" style={{ marginBottom: "12px" }}>
        <span style={{ color: "#10b981" }}>●</span>
        <span>DESKTOP AUTHENTICATION</span>
      </div>

      <h2
        className="card-title"
        style={{ fontSize: "20px", fontWeight: 700, letterSpacing: "0.04em", color: "#f8fafc" }}
      >
        ALGOfORTIS LOGIN
      </h2>
      <p className="card-subtitle" style={{ fontSize: "12.5px", color: "#94a3b8", marginBottom: "20px" }}>
        Enter your Super Owner credentials to unlock the desktop workspace.
      </p>

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
          <label htmlFor="login-email" className="field-label" style={{ fontSize: "11px", fontWeight: 600, color: "#cbd5e1" }}>
            Email Address
          </label>
          <div className="field-input-wrapper">
            <input
              id="login-email"
              type="email"
              className="field-input"
              placeholder="owner@algofortis.internal"
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
            <label htmlFor="login-password" className="field-label" style={{ fontSize: "11px", fontWeight: 600, color: "#cbd5e1" }}>
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
              placeholder="••••••••••••"
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
          className="submit-btn"
          disabled={isSubmitting}
          style={{
            marginTop: "8px",
            background: "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
            color: "#0f172a",
            fontWeight: 700,
            fontSize: "13px",
            padding: "11px 16px",
            borderRadius: "6px",
            border: "none",
            cursor: isSubmitting ? "not-allowed" : "pointer",
            letterSpacing: "0.05em",
            opacity: isSubmitting ? 0.7 : 1,
            transition: "all 0.2s ease",
          }}
        >
          {isSubmitting ? "AUTHENTICATING..." : "SIGN IN TO WORKSPACE"}
        </button>
      </form>

      <div style={{ marginTop: "18px", textAlign: "center", fontSize: "11.5px", color: "#64748b" }}>
        Protected by AlgoFortis Local Security Vault
      </div>
    </div>
  );
};
