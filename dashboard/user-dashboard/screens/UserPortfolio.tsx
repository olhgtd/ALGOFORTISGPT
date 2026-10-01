import React, { useEffect, useState } from "react";
import { loadTradingSurface, type RuntimeSurfaceBlock, type TradingSurfaceData } from "../data/userSurfaceData";
import {
  AuthorityMessage,
  MetricCell,
  SurfacePanel,
  UserSurfaceHeader,
  displayMoney,
  displayScalar,
  evidenceValue,
} from "../components/UserSurfacePrimitives";

export interface UserPortfolioProps {
  loadData?: () => Promise<TradingSurfaceData>;
}

const asRecord = (value: unknown) => value as Record<string, unknown>;
const scalar = (row: Record<string, unknown>, keys: readonly string[]) => displayScalar(evidenceValue(row, keys));
const money = (row: Record<string, unknown>, keys: readonly string[]) => {
  const value = evidenceValue(row, keys);
  return typeof value === "number" ? displayMoney(value) : displayScalar(value);
};

const CapitalPool: React.FC<{ mode: "PAPER" | "LIVE"; block: RuntimeSurfaceBlock }> = ({ mode, block }) => {
  const snapshot = block.snapshot;
  const accounts = snapshot?.accounts ?? [];
  const positions = snapshot?.positions ?? [];

  return (
    <SurfacePanel
      eyebrow={`${mode} Capital`}
      title={mode === "PAPER" ? "Paper Capital" : "Live Capital"}
      authority={block.state}
      className="af-capital-mode-panel"
    >
      <div className="af-capital-mode-warning">
        <strong>{mode === "LIVE" ? "READ_ONLY / DISARMED" : "SIMULATION AUTHORITY"}</strong>
        <span>{mode === "LIVE" ? "Live account values never imply execution is armed." : "Paper capital remains isolated from Live broker capital."}</span>
      </div>

      {block.state !== "AVAILABLE" || !snapshot ? (
        <AuthorityMessage state="UNAVAILABLE" title={`${mode} capital`} unavailable={`${mode} portfolio authority is unavailable. No zero balance is fabricated.`} />
      ) : accounts.length === 0 ? (
        <AuthorityMessage state="AVAILABLE" isEmpty title={`${mode} capital`} unavailable="" empty={`No authoritative ${mode.toLowerCase()} account rows are available.`} />
      ) : (
        <div className="af-capital-account-list">
          {accounts.map((account, index) => {
            const row = asRecord(account);
            const accountKey = scalar(row, ["account_id", "account_ref", "broker", "session_id"]);
            return (
              <article className="af-capital-account" key={`${accountKey}-${index}`}>
                <div className="af-capital-account-head">
                  <div>
                    <span>{scalar(row, ["broker", "provider", "source", "execution_mode"])}</span>
                    <strong>{accountKey}</strong>
                  </div>
                  <span className="af-status-text">{scalar(row, ["status", "state", "connection_state"])}</span>
                </div>
                <div className="af-surface-metrics-grid compact">
                  <MetricCell label="Equity" value={money(row, ["equity", "current_equity", "net_liquidation"])} />
                  <MetricCell label="Available" value={money(row, ["available_funds", "available_cash", "cash"])} />
                  <MetricCell label="Used capital" value={money(row, ["used_capital", "margin_used", "used_margin"])} />
                  <MetricCell label="Today P&L" value={money(row, ["day_pnl", "today_pnl"])} />
                  <MetricCell label="Open P&L" value={money(row, ["unrealized_pnl", "open_pnl"])} />
                  <MetricCell label="Realized P&L" value={money(row, ["realized_pnl", "closed_pnl"])} />
                </div>
              </article>
            );
          })}
        </div>
      )}

      {block.state === "AVAILABLE" && snapshot && (
        <div className="af-portfolio-position-summary">
          <div className="af-surface-subhead"><strong>Positions</strong><span>{positions.length} authoritative row{positions.length === 1 ? "" : "s"}</span></div>
          {positions.length === 0 ? (
            <p className="af-surface-inline-note">No authoritative open positions in this capital pool.</p>
          ) : (
            <div className="af-surface-table-wrap">
              <table className="af-surface-table">
                <thead><tr><th>Strategy</th><th>Instrument</th><th>Qty</th><th>Entry</th><th>Current</th><th>P&L</th></tr></thead>
                <tbody>
                  {positions.slice(0, 25).map((position, index) => {
                    const row = asRecord(position);
                    return (
                      <tr key={`${scalar(row, ["position_id", "instrument", "symbol"])}-${index}`}>
                        <td>{scalar(row, ["strategy_name", "strategy_id"])}</td>
                        <td>{scalar(row, ["instrument", "symbol", "contract_identity"])}</td>
                        <td>{scalar(row, ["quantity", "qty", "lots"])}</td>
                        <td>{money(row, ["entry_price", "avg_price", "average_price"])}</td>
                        <td>{money(row, ["current_price", "ltp", "mark_price"])}</td>
                        <td>{money(row, ["pnl", "unrealized_pnl", "open_pnl"])}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </SurfacePanel>
  );
};

export const UserPortfolio: React.FC<UserPortfolioProps> = ({ loadData = loadTradingSurface }) => {
  const [data, setData] = useState<TradingSurfaceData | null>(null);

  useEffect(() => {
    let active = true;
    setData(null);
    loadData().then((next) => { if (active) setData(next); }).catch(() => {
      if (active) setData({
        PAPER: { state: "UNAVAILABLE", snapshot: null },
        LIVE: { state: "UNAVAILABLE", snapshot: null },
      });
    });
    return () => { active = false; };
  }, [loadData]);

  const paper = data?.PAPER ?? { state: "UNAVAILABLE" as const, snapshot: null };
  const live = data?.LIVE ?? { state: "UNAVAILABLE" as const, snapshot: null };

  return (
    <div className="af-user-surface" data-testid="portfolio-surface">
      <UserSurfaceHeader
        eyebrow="Capital & Exposure"
        title="Portfolio"
        description="Capital pools, positions, and P&L remain separated by execution mode and account authority. Paper and Live balances are not combined into a spendable total."
        aside={<div className="af-surface-lock"><span>Capital Rule</span><strong>POOLS STAY SEPARATE</strong></div>}
      />

      <div className="af-portfolio-separation-note">
        <strong>Capital pools are not combined.</strong>
        <span>Each broker/session remains its own authority and funding boundary.</span>
      </div>

      {!data && <AuthorityMessage state="LOADING" title="Portfolio authority" unavailable="" />}

      <div className="af-portfolio-pools">
        <CapitalPool mode="PAPER" block={paper} />
        <CapitalPool mode="LIVE" block={live} />
      </div>
    </div>
  );
};
