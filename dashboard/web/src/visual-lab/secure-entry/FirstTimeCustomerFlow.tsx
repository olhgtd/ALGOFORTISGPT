import React, { useState } from "react";
import type { AccessGateStep } from "./types";
import { api } from "../../api";
import { executeUserEnrollment } from "./webauthn-client";

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

export const FirstTimeCustomerFlow: React.FC<FirstTimeCustomerFlowProps> = ({ accessId, onAccessIdChange, onSwitchToReturningUser }) => {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [issued, setIssued] = useState<Awaited<ReturnType<typeof api.redeemUserActivation>> | null>(null);
  const [enrolled, setEnrolled] = useState(false);
  const redeem = async (event: React.FormEvent) => {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      setIssued(await api.redeemUserActivation(accessId.trim(), code.trim()));
      setCode("");
    } catch (e) { setError(e instanceof Error ? e.message : "Activation unavailable."); }
    finally { setBusy(false); }
  };
  const enroll = async () => {
    if (!issued) return;
    setBusy(true); setError(null);
    try { await executeUserEnrollment(issued); setIssued(null); setEnrolled(true); }
    catch (e) { setError(e instanceof Error ? e.message : "Enrollment unavailable."); }
    finally { setBusy(false); }
  };
  return <div className="secure-floating-form" id="access-gate-card">
    <div className="card-header-block">
      <h2 className="card-title">AlgoFortis User Activation</h2>
      <p className="card-subtitle">Use the User ID and single-use invitation issued by your Owner.</p>
    </div>
    {error && <div className="auth-error-alert" role="alert" id="activation-error">{error}</div>}
    {enrolled ? <div id="user-enrollment-complete">
      <p>Passkey registered. Sign in with your User ID and passkey to establish a session.</p>
      <button className="btn-primary-continue" onClick={onSwitchToReturningUser} id="activation-signin-btn">SIGN IN</button>
    </div> : issued ? <div>
      <p>Invitation redeemed. Register your passkey within five minutes. If enrollment expires or fails, ask your Owner for a new invitation.</p>
      <button className="btn-primary-continue" disabled={busy} onClick={enroll} id="user-enroll-passkey-btn">{busy ? "REGISTERING..." : "REGISTER PASSKEY"}</button>
    </div> : <form onSubmit={redeem} id="access-gate-form">
      <div className="form-field-group"><label className="field-label" htmlFor="access-id-input">AlgoFortis User ID</label>
        <input className="field-input mono-input" id="access-id-input" placeholder="AF-U-XXXX-XXXX / SX-U-..." value={accessId} onChange={e => onAccessIdChange(e.target.value.toUpperCase())} autoComplete="username" required disabled={busy} />
      </div>
      <div className="form-field-group"><label className="field-label" htmlFor="activation-code-input">Activation code</label>
        <input className="field-input mono-input" id="activation-code-input" type="password" value={code} onChange={e => setCode(e.target.value)} autoComplete="off" required disabled={busy} />
      </div>
      <button className="btn-primary-continue" id="access-gate-continue-btn" disabled={busy || !accessId.trim() || !code.trim()}>{busy ? "VALIDATING..." : "REDEEM INVITATION"}</button>
    </form>}
    {!enrolled && <button className="footer-link-btn" onClick={onSwitchToReturningUser} disabled={busy}>Returning user? Sign in with passkey</button>}
  </div>;
};
