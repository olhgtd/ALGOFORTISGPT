import React from "react";
import type { HomeCommandCenterModel } from "../homeModel";

const STAGES = ["Backtest", "Walk-Forward", "OOS", "Robustness", "Validation"] as const;

export const TestingProgressSummary: React.FC<{ testing: HomeCommandCenterModel["testing"]; onOpenTesting: () => void }> = ({ testing, onOpenTesting }) => (
  <section className="af-home-card">
    <header className="af-home-card-head">
      <div><span className="af-eyebrow">Testing</span><h3>Validation Progress</h3></div>
      <button type="button" className="af-text-button" onClick={onOpenTesting}>Open Testing</button>
    </header>
    <div className="af-testing-grid">
      {STAGES.map((stage) => (
        <div className="af-testing-stage" key={stage}>
          <span>{stage}</span>
          <strong>{testing.state}</strong>
        </div>
      ))}
    </div>
    <p className="af-card-footnote">No PASS state is shown without authoritative test evidence.</p>
  </section>
);
