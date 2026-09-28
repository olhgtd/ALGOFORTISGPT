import React from "react";
import type { HomeCommandCenterModel } from "../homeModel";

const money = (value: number | null) => value === null
  ? "UNAVAILABLE"
  : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(value);

const pnlClass = (value: number | null): string => {
  if (value === null) return "af-value-unavailable";
  if (value > 0) return "af-value-positive";
  if (value < 0) return "af-value-negative";
  return "af-value-neutral";
};

export const PositionsSummary: React.FC<{ positions: HomeCommandCenterModel["positions"]; onOpenTrades: () => void }> = ({ positions, onOpenTrades }) => (
  <section className="af-home-card">
    <header className="af-home-card-head">
      <div><span className="af-eyebrow">Positions</span><h3>Active Positions</h3></div>
      <button type="button" className="af-text-button" onClick={onOpenTrades}>Open Trades</button>
    </header>
    {positions.items === null ? (
      <div className="af-empty-state"><strong>UNAVAILABLE</strong><span>Position authority is not available. No empty-state assumption is made.</span></div>
    ) : positions.items.length === 0 ? (
      <div className="af-empty-state"><strong>No positions</strong><span>The authoritative source returned an empty collection.</span></div>
    ) : (
      <div className="af-compact-table-wrap">
        <table className="af-compact-table">
          <thead><tr><th>Instrument</th><th>Strategy</th><th>Qty</th><th>Lots</th><th>P&amp;L</th><th>Status</th></tr></thead>
          <tbody>
            {positions.items.slice(0, 6).map((row) => (
              <tr key={row.id}>
                <td>{row.instrument ?? "UNAVAILABLE"}</td>
                <td>{row.strategy ?? "UNAVAILABLE"}</td>
                <td>{row.quantity ?? "UNAVAILABLE"}</td>
                <td>{row.lots ?? "UNAVAILABLE"}</td>
                <td className={pnlClass(row.pnl)}>{money(row.pnl)}</td>
                <td>{row.status ?? "UNAVAILABLE"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </section>
);
