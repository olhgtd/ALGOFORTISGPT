import React from "react";
import type { HomeCommandCenterModel } from "../homeModel";

export const StrategyStatusSummary: React.FC<{ strategies: HomeCommandCenterModel["strategies"]; onOpenStrategies: () => void }> = ({ strategies, onOpenStrategies }) => (
  <section className="af-home-card">
    <header className="af-home-card-head">
      <div><span className="af-eyebrow">Strategies</span><h3>Lifecycle Status</h3></div>
      <button type="button" className="af-text-button" onClick={onOpenStrategies}>Open Strategies</button>
    </header>
    <div className="af-empty-state">
      <strong>{strategies.state}</strong>
      <span>Authoritative strategy lifecycle summary is not wired into Home yet. No deployed/validated status is inferred.</span>
    </div>
  </section>
);
