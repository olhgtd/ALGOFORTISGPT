import React from "react";

interface HelpRecoveryFlowProps {
  onBackToReturningUser: () => void;
  onBackToAccessGate?: () => void;
}

export const HelpRecoveryFlow: React.FC<HelpRecoveryFlowProps> = ({
  onBackToReturningUser,
  onBackToAccessGate,
}) => {
  return (
    <div className="secure-access-card" id="recovery-help-card">
      <div className="card-header-block">
        <h2 className="card-title">Access Recovery &amp; Help</h2>
        <p className="card-subtitle">
          AlgoFortis institutional security recovery protocols.
        </p>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "20px" }}>
        <div
          style={{
            padding: "12px",
            background: "var(--sx-surface-3)",
            borderRadius: "6px",
            border: "1px solid var(--sx-hairline-strong)",
            fontSize: "12px",
            lineHeight: "1.4",
            textAlign: "left",
          }}
        >
          <strong style={{ color: "var(--sx-ink-primary)", display: "block", marginBottom: "4px" }}>
            Lost Hardware Authenticator?
          </strong>
          <span style={{ color: "var(--sx-ink-secondary)" }}>
            Self-service web credential reset is disabled. Contact Owner to provision a replacement FIDO2 passkey or re-enroll out-of-band.
          </span>
        </div>

        <div
          style={{
            padding: "12px",
            background: "var(--sx-surface-3)",
            borderRadius: "6px",
            border: "1px solid var(--sx-hairline-strong)",
            fontSize: "12px",
            lineHeight: "1.4",
            textAlign: "left",
          }}
        >
          <strong style={{ color: "var(--sx-ink-primary)", display: "block", marginBottom: "4px" }}>
            Emergency Recovery
          </strong>
          <span style={{ color: "var(--sx-ink-secondary)" }}>
            Automated break-glass recovery is disabled. If the runtime is unresponsive, restart AlgoFortis and sign in again. If access is still unavailable, contact Owner. No terminal commands are required.
          </span>
        </div>
      </div>

      <div className="card-footer-actions">
        <button
          type="button"
          className="footer-link-btn"
          onClick={onBackToReturningUser}
          id="recovery-back-to-login"
        >
          Return to Sign In
        </button>
        {onBackToAccessGate && (
          <button
            type="button"
            className="footer-link-btn"
            onClick={onBackToAccessGate}
            id="recovery-back-to-gate"
          >
            Return to Access Gate
          </button>
        )}
      </div>
    </div>
  );
};
