import React from "react";
import type { HomeCommandCenterModel } from "../homeModel";

const show = (value: number | null): string => value === null ? "UNAVAILABLE" : String(value);

export const StrategyStatusSummary: React.FC<{ strategies: HomeCommandCenterModel["strategies"]; onOpenStrategies: () => void }> = ({ strategies, onOpenStrategies }) => (
  <section className="af-home-card">
    <header className="af-home-card-head">
      <div><span className="af-eyebrow">Strategies</span><h3>Lifecycle Status</h3></div>
      <button type="button" className="af-text-button" onClick={onOpenStrategies}>Open Strategies</button>
    </header>
    {strategies.state === "AVAILABLE" ? (
      <dl className="af-home-kv-grid">
        <div><dt>Registered</dt><dd>{show(strategies.total)}</dd></div>
        <div><dt>Deployments</dt><dd>{show(strategies.deployments)}</dd></div>
        <div><dt>Paper ready</dt><dd>{show(strategies.paperReady)}</dd></div>
        <div><dt>Live ready</dt><dd>{show(strategies.liveReady)}</dd></div>
      </dl>
    ) : (
      <div className="af-empty-state">
        <strong>{strategies.state}</strong>
        <span>Authoritative strategy lifecycle summary is unavailable. No deployed or validated state is inferred.</span>
      </div>
    )}
    <p className="af-card-footnote">Counts reflect backend registry/readiness/deployment authorities only. Live readiness never arms execution.</p>
  </section>
);
