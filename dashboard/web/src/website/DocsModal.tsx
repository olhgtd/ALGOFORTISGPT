/**
 * AlgoFortis Public Website – Architectural Documentation Modal
 * Surface: algofortis.com
 */

import React, { useState } from "react";

interface DocsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const DocsModal: React.FC<DocsModalProps> = ({ isOpen, onClose }) => {
  const [activeTab, setActiveTab] = useState<"governance" | "engine" | "security">("governance");

  if (!isOpen) return null;

  return (
    <div className="sx-modal-overlay" onClick={onClose}>
      <div className="sx-modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="sx-modal-header">
          <div className="sx-modal-title">
            <span style={{ color: "var(--sx-sky-text)" }}>📖</span>
            <span>AlgoFortis Architectural Documentation & Specifications</span>
          </div>
          <button className="sx-modal-close-btn" onClick={onClose}>✕</button>
        </div>

        <div style={{ display: "flex", gap: "8px", padding: "12px 20px", background: "var(--sx-surface-2)", borderBottom: "1px solid var(--sx-hairline)" }}>
          <button
            className={`sx-btn ${activeTab === "governance" ? "sx-btn-primary" : "sx-btn-secondary"}`}
            onClick={() => setActiveTab("governance")}
            style={{ fontSize: "11px", padding: "4px 12px" }}
          >
            Strategy Governance Spec
          </button>
          <button
            className={`sx-btn ${activeTab === "engine" ? "sx-btn-primary" : "sx-btn-secondary"}`}
            onClick={() => setActiveTab("engine")}
            style={{ fontSize: "11px", padding: "4px 12px" }}
          >
            Deterministic Engine Invariants
          </button>
          <button
            className={`sx-btn ${activeTab === "security" ? "sx-btn-primary" : "sx-btn-secondary"}`}
            onClick={() => setActiveTab("security")}
            style={{ fontSize: "11px", padding: "4px 12px" }}
          >
            FIDO2 WebAuthn Perimeter
          </button>
        </div>

        <div className="sx-modal-content">
          {activeTab === "governance" && (
            <div>
              <h4 style={{ fontSize: "14px", fontWeight: "700", marginBottom: "8px", color: "var(--sx-ink-primary)" }}>
                Strategy State Machine Lifecycle Rules (§4.2)
              </h4>
              <p style={{ fontSize: "13px", color: "var(--sx-ink-secondary)", marginBottom: "12px" }}>
                Every strategy transitions through strict discrete states. No backward transitions are permitted without full re-validation.
              </p>
              <div className="sx-code-block">
                {`# Canonical State Transition Graph
DRAFT
  └──[ Static AST Lint & Invariant Check ]──> VALIDATED
        └──[ Zero-Lookahead Backtest (Sharpe > 1.8) ]──> BACKTESTED
              └──[ 72h Real-Time Paper Sandbox ]──> PAPER_APPROVED
                    └──[ FIDO2 Hardware Key Sign-Off ]──> LIVE_LOCKED`}
              </div>
            </div>
          )}

          {activeTab === "engine" && (
            <div>
              <h4 style={{ fontSize: "14px", fontWeight: "700", marginBottom: "8px", color: "var(--sx-ink-primary)" }}>
                Execution Engine Determinism & Latency Bounds (§2.1)
              </h4>
              <p style={{ fontSize: "13px", color: "var(--sx-ink-secondary)", marginBottom: "12px" }}>
                The core order processing path is bounded to sub-50μs with zero memory allocation during steady-state tick handling.
              </p>
              <div className="sx-code-block">
                {`typedef struct {
    uint64_t sequence_id;
    uint64_t timestamp_ns;
    char     symbol[16];
    uint8_t  side;          /* 1 = BUY, 2 = SELL */
    uint32_t quantity;
    double   limit_price;
    uint8_t  state_flags;   /* FAIL_CLOSED, RISK_ARMED */
} sentinelx_order_event_t;`}
              </div>
            </div>
          )}

          {activeTab === "security" && (
            <div>
              <h4 style={{ fontSize: "14px", fontWeight: "700", marginBottom: "8px", color: "var(--sx-ink-primary)" }}>
                Hardware Security Key Authentication (§131)
              </h4>
              <p style={{ fontSize: "13px", color: "var(--sx-ink-secondary)", marginBottom: "12px" }}>
                FIDO2 WebAuthn physical security tokens provide cryptographic challenge-response authentication. Passwords and shared secrets are architecturally banned.
              </p>
              <div className="sx-code-block">
                {`{
  "publicKey": {
    "challenge": "e2a78f10...",
    "timeout": 60000,
    "userVerification": "required",
    "authenticatorSelection": {
      "authenticatorAttachment": "cross-platform",
      "requireResidentKey": true,
      "userVerification": "required"
    }
  }
}`}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
