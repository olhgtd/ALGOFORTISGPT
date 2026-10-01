import React from "react";
import type { HomeCommandCenterModel } from "../homeModel";

export const RiskSummary: React.FC<{ risk: HomeCommandCenterModel["risk"] }> = ({ risk }) => (
  <section className="af-home-card af-risk-card">
    <header className="af-home-card-head">
      <div><span className="af-eyebrow">Risk</span><h3>Operational Risk</h3></div>
      <span className={`af-authority af-authority-${risk.state.toLowerCase()}`}>{risk.state}</span>
    </header>
    {risk.level ? (
      <div className="af-risk-level"><strong>{risk.level}</strong>{risk.reasons.map((reason) => <span key={reason}>{reason}</span>)}</div>
    ) : (
      <div className="af-empty-state"><strong>UNKNOWN</strong><span>Authoritative risk summary unavailable. UNKNOWN is never treated as healthy.</span></div>
    )}
    <div className="af-emergency-legend" aria-label="Emergency control meanings">
      <span>Pause / HALT_ENTRIES</span><span>Cancel Pending</span><span>Flatten / Exit</span>
    </div>
  </section>
);
