import React from "react";
import type { HomeCommandCenterModel } from "./homeModel";
import { CapitalSummary } from "./components/CapitalSummary";
import { MarketSnapshotCard } from "./components/MarketSnapshotCard";
import { OperationalStateStrip } from "./components/OperationalStateStrip";
import { PositionsSummary } from "./components/PositionsSummary";
import { RecentActivitySummary } from "./components/RecentActivitySummary";
import { RiskSummary } from "./components/RiskSummary";
import { StrategyStatusSummary } from "./components/StrategyStatusSummary";
import { TestingProgressSummary } from "./components/TestingProgressSummary";

export interface HomeCommandCenterProps {
  model: HomeCommandCenterModel;
  onNavigate: (screen: string) => void;
}

export const HomeCommandCenter: React.FC<HomeCommandCenterProps> = ({ model, onNavigate }) => (
  <div className="af-home-command-center">
    <header className="af-home-header">
      <div>
        <span className="af-eyebrow">Home / Command Center</span>
        <h1>{model.profile.displayName ? `Welcome, ${model.profile.displayName}` : "AlgoFortis Command Center"}</h1>
        <p>{model.profile.sxId ?? "Authoritative identity metadata unavailable"}</p>
      </div>
      <div className="af-home-actions" aria-label="Quick navigation">
        <button type="button" onClick={() => onNavigate("markets")}>Markets</button>
        <button type="button" onClick={() => onNavigate("strategies")}>Strategies</button>
        <button type="button" onClick={() => onNavigate("testing")}>Testing</button>
        <button type="button" onClick={() => onNavigate("trades")}>Trades</button>
      </div>
    </header>

    <OperationalStateStrip status={model.shell} />

    <section className="af-home-market-grid" aria-label="Market snapshot">
      {model.markets.map((market) => <MarketSnapshotCard key={market.symbol} market={market} />)}
    </section>

    <CapitalSummary capital={model.capital} />

    <div className="af-home-grid two">
      <PositionsSummary positions={model.positions} onOpenTrades={() => onNavigate("trades")} />
      <RiskSummary risk={model.risk} />
    </div>

    <div className="af-home-grid two">
      <StrategyStatusSummary strategies={model.strategies} onOpenStrategies={() => onNavigate("strategies")} />
      <TestingProgressSummary testing={model.testing} onOpenTesting={() => onNavigate("testing")} />
    </div>

    <RecentActivitySummary activity={model.recentActivity} />
  </div>
);
