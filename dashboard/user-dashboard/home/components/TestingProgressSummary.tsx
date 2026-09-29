import React from "react";
import type { HomeCommandCenterModel } from "../homeModel";

const show = (value: number | null): string => value === null ? "UNAVAILABLE" : String(value);

export const TestingProgressSummary: React.FC<{ testing: HomeCommandCenterModel["testing"]; onOpenTesting: () => void }> = ({ testing, onOpenTesting }) => (
  <section className="af-home-card">
    <header className="af-home-card-head">
      <div><span className="af-eyebrow">Testing</span><h3>Validation Evidence</h3></div>
      <button type="button" className="af-text-button" onClick={onOpenTesting}>Open Testing</button>
    </header>
    <div className="af-testing-grid">
      <div className="af-testing-stage"><span>Backtests</span><strong>{show(testing.backtests)}</strong></div>
      <div className="af-testing-stage"><span>Walk-Forward</span><strong>{show(testing.walkForward)}</strong></div>
      <div className="af-testing-stage"><span>Reports</span><strong>{show(testing.reports)}</strong></div>
      <div className="af-testing-stage"><span>Active Jobs</span><strong>{show(testing.activeJobs)}</strong></div>
    </div>
    <p className="af-card-footnote">Authority: {testing.state}. Counts are evidence inventory only; no PASS or promotion result is inferred.</p>
  </section>
);
