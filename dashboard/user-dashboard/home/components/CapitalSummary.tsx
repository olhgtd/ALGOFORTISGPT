import React from "react";
import type { HomeCommandCenterModel } from "../homeModel";

const money = (value: number | null) => value === null
  ? "UNAVAILABLE"
  : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(value);

export const CapitalSummary: React.FC<{ capital: HomeCommandCenterModel["capital"] }> = ({ capital }) => (
  <section className="af-home-card af-capital-card">
    <header className="af-home-card-head">
      <div><span className="af-eyebrow">Capital</span><h3>Account / Session Pools</h3></div>
      <span className={`af-authority af-authority-${capital.state.toLowerCase()}`}>{capital.state}</span>
    </header>
    {capital.pools === null ? (
      <div className="af-empty-state"><strong>UNAVAILABLE</strong><span>No authoritative capital-pool evidence is available.</span></div>
    ) : capital.pools.length === 0 ? (
      <div className="af-empty-state"><strong>No capital pools recorded</strong><span>The authority returned an empty collection.</span></div>
    ) : (
      <div className="af-capital-pools">
        {capital.pools.map((pool) => (
          <article className="af-capital-pool" key={pool.id}>
            <div className="af-capital-pool-title"><strong>{pool.id}</strong><span>{pool.executionMode ?? "Mode unavailable"}</span></div>
            <div className="af-metric-grid compact">
              <div><span>Equity</span><strong>{money(pool.equity)}</strong></div>
              <div><span>Available</span><strong>{money(pool.availableFunds)}</strong></div>
              <div><span>Used</span><strong>{money(pool.usedCapital)}</strong></div>
              <div><span>Open P&amp;L</span><strong>{money(pool.unrealizedPnl)}</strong></div>
              <div><span>Realized P&amp;L</span><strong>{money(pool.realizedPnl)}</strong></div>
            </div>
            <div className="af-home-meta"><span>{pool.strategy ?? "Strategy unavailable"}</span><span>{pool.source ?? "Source unavailable"}</span></div>
          </article>
        ))}
      </div>
    )}
    <p className="af-card-footnote">Pools remain distinct. AlgoFortis does not present them as one freely routable spendable balance.</p>
  </section>
);
