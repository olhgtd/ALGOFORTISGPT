import React from "react";
import type { UserShellStatus } from "../../shellState";

export const OperationalStateStrip: React.FC<{ status: UserShellStatus }> = ({ status }) => (
  <section className="af-home-operational" aria-label="Operational state">
    <div className="af-home-op-primary">
      <span className="af-eyebrow">Operational State</span>
      <strong>{status.modeLabel}</strong>
      {status.liveStateLabel && <span className="af-live-lock">{status.liveStateLabel}</span>}
    </div>
    <div className={`af-automation-state af-state-${status.automationState.toLowerCase().replaceAll("_", "-")}`}>
      <span>Automation</span>
      <strong>{status.automationState}</strong>
      {status.manualResumeRequired && <small>Manual resume required</small>}
    </div>
    <div className="af-home-op-facts">
      <span><b>Engine</b>{status.engineState}</span>
      <span><b>Broker</b>{status.brokerState}</span>
      <span><b>Data</b>{status.dataFreshness}</span>
    </div>
  </section>
);
