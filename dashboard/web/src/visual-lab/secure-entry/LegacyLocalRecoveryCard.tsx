import React, { useState } from "react";
import { api } from "../../api";
import { clearSessionToken } from "../../../../shared/services/sessionStore";

interface LegacyLocalRecoveryCardProps {
  onBackToLogin: () => void;
  onRecoverySuccess?: () => void;
}

export const LegacyLocalRecoveryCard: React.FC<LegacyLocalRecoveryCardProps> = ({
  onBackToLogin,
  onRecoverySuccess,
}) => {
  const [step, setStep] = useState<"VERIFY" | "RESET" | "SUCCESS">("VERIFY");
  const [email, setEmail] = useState("");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    const cleanEmail = email.trim();
    const cleanCode = recoveryCode.trim();

    if (!cleanEmail || !cleanEmail.includes("@")) {
      setErrorMessage("Please enter a valid email address.");
      return;
    }
    if (!cleanCode) {
      setErrorMessage("Emergency recovery code is required.");
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await api.localRecoveryVerify({
        email: cleanEmail,
        recovery_code: cleanCode,
      });

      if (res.valid) {
        setIsSubmitting(false);
        setStep("RESET");
      } else {
        setIsSubmitting(false);
        setErrorMessage("Invalid recovery credentials. Please verify your email and recovery code.");
      }
    } catch (err: any) {
      setIsSubmitting(false);
      let msg = "Invalid recovery credentials. Please verify your email and recovery code.";
      if (err instanceof Error) {
        if (err.message.includes("429") || err.message.toLowerCase().includes("cooldown") || err.message.toLowerCase().includes("too many")) {
          msg = err.message;
        }
      }
      setErrorMessage(msg);
    }
  };

  const handleReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (newPassword.length < 8) {
      setErrorMessage("Password must be at least 8 characters long.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setErrorMessage("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);
    try {
      await api.localRecoveryReset({
        email: email.trim(),
        recovery_code: recoveryCode.trim(),
        new_password: newPassword,
        confirm_password: confirmPassword,
      });

      // Clear any cached local persistent session so user must sign in with new password
      clearSessionToken();

      setIsSubmitting(false);
      setStep("SUCCESS");
      if (onRecoverySuccess) {
        onRecoverySuccess();
      }
    } catch (err: any) {
      setIsSubmitting(false);
      let msg = "Failed to reset password. Recovery code may be invalid or already used.";
      if (err instanceof Error) {
        if (err.message.includes("429") || err.message.toLowerCase().includes("cooldown")) {
          msg = err.message;
        }
      }
      setErrorMessage(msg);
    }
  };

  return (
    <div className="secure-access-card" id="local-recovery-card">
      <div className="access-gate-badge" style={{ marginBottom: "12px" }}>
        <span style={{ color: "#38bdf8" }}>●</span>
        <span>EMERGENCY ACCESS</span>
      </div>

      <h2
        className="card-title"
        style={{ fontSize: "20px", fontWeight: 700, letterSpacing: "0.04em", color: "#f8fafc" }}
      >
        ALGOfORTIS ACCOUNT RECOVERY
      </h2>
      <p className="card-subtitle" style={{ fontSize: "12.5px", color: "#94a3b8", marginBottom: "20px" }}>
        {step === "VERIFY" && "Verify your Super Owner identity using an emergency single-use recovery code."}
        {step === "RESET" && "Create a new strong password. All previous sessions will be terminated."}
        {step === "SUCCESS" && "Password reset complete. You can now sign in with your new password."}
      </p>

      {errorMessage && (
        <div
          role="alert"
          id="recovery-error-alert"
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

      {step === "VERIFY" && (
        <form onSubmit={handleVerify} style={{ display: "flex", flexDirection: "column", gap: "14px", width: "100%" }}>
          <div className="form-field-group">
            <label htmlFor="recovery-email" className="field-label" style={{ fontSize: "11px", fontWeight: 600, color: "#cbd5e1" }}>
              Email Address
            </label>
            <div className="field-input-wrapper">
              <input
                id="recovery-email"
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
            <label htmlFor="recovery-code" className="field-label" style={{ fontSize: "11px", fontWeight: 600, color: "#cbd5e1" }}>
              Recovery Code
            </label>
            <div className="field-input-wrapper">
              <input
                id="recovery-code"
                type="text"
                className="field-input mono-input"
                placeholder="RC-XXXX-XXXX"
                value={recoveryCode}
                onChange={(e) => setRecoveryCode(e.target.value)}
                disabled={isSubmitting}
                autoComplete="off"
                required
              />
            </div>
          </div>

          <button
            type="submit"
            id="recovery-verify-btn"
            className="submit-btn"
            disabled={isSubmitting || !email.trim() || !recoveryCode.trim()}
            style={{
              marginTop: "8px",
              background: "linear-gradient(135deg, #0284c7 0%, #0369a1 100%)",
              color: "#ffffff",
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
            {isSubmitting ? "VERIFYING..." : "VERIFY RECOVERY CODE"}
          </button>
        </form>
      )}

      {step === "RESET" && (
        <form onSubmit={handleReset} style={{ display: "flex", flexDirection: "column", gap: "14px", width: "100%" }}>
          <div className="form-field-group">
            <label className="field-label" style={{ fontSize: "11px", fontWeight: 600, color: "#94a3b8" }}>
              Verified Owner
            </label>
            <div style={{ padding: "8px 12px", background: "rgba(30, 41, 59, 0.5)", borderRadius: "6px", fontSize: "12px", color: "#e2e8f0" }}>
              {email} <span style={{ color: "#10b981", marginLeft: "8px" }}>✓ Code Verified</span>
            </div>
          </div>

          <div className="form-field-group">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <label htmlFor="recovery-new-password" className="field-label" style={{ fontSize: "11px", fontWeight: 600, color: "#cbd5e1" }}>
                New Password
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
                id="recovery-new-password"
                type={showPassword ? "text" : "password"}
                className="field-input"
                placeholder="Minimum 8 characters"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                disabled={isSubmitting}
                autoComplete="new-password"
                autoFocus
                required
              />
            </div>
          </div>

          <div className="form-field-group">
            <label htmlFor="recovery-confirm-password" className="field-label" style={{ fontSize: "11px", fontWeight: 600, color: "#cbd5e1" }}>
              Confirm Password
            </label>
            <div className="field-input-wrapper">
              <input
                id="recovery-confirm-password"
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

          <button
            type="submit"
            id="recovery-reset-btn"
            className="submit-btn"
            disabled={isSubmitting || newPassword.length < 8 || newPassword !== confirmPassword}
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
            {isSubmitting ? "RESETTING PASSWORD..." : "RESET PASSWORD"}
          </button>
        </form>
      )}

      {step === "SUCCESS" && (
        <div style={{ textAlign: "center", padding: "10px 0" }}>
          <div
            style={{
              background: "rgba(16, 185, 129, 0.12)",
              border: "1px solid rgba(16, 185, 129, 0.35)",
              borderRadius: "6px",
              padding: "16px",
              marginBottom: "20px",
              color: "#6ee7b7",
              fontSize: "13px",
              lineHeight: 1.5,
            }}
          >
            <div style={{ fontSize: "20px", marginBottom: "8px" }}>✓</div>
            <strong>Password Reset Complete</strong>
            <p style={{ margin: "6px 0 0 0", fontSize: "12px", color: "#a7f3d0" }}>
              Your password has been securely updated and all active sessions have been revoked.
            </p>
          </div>

          <button
            type="button"
            id="recovery-success-login-btn"
            onClick={onBackToLogin}
            className="submit-btn"
            style={{
              background: "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)",
              color: "#0f172a",
              fontWeight: 700,
              fontSize: "13px",
              padding: "11px 20px",
              borderRadius: "6px",
              border: "none",
              cursor: "pointer",
              letterSpacing: "0.05em",
            }}
          >
            SIGN IN TO WORKSPACE
          </button>
        </div>
      )}

      {step !== "SUCCESS" && (
        <div style={{ marginTop: "16px", textAlign: "center" }}>
          <button
            type="button"
            id="back-to-login-btn"
            onClick={onBackToLogin}
            style={{
              background: "none",
              border: "none",
              color: "#94a3b8",
              fontSize: "12px",
              cursor: "pointer",
              padding: "4px 8px",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "#f8fafc")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "#94a3b8")}
          >
            ← Back to Login
          </button>
        </div>
      )}
    </div>
  );
};
