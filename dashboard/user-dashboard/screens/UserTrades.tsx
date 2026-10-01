import React, { useEffect, useMemo, useState } from "react";
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

export interface UserTradesProps {
  loadData?: () => Promise<TradingSurfaceData>;
}

const rowValue = (row: Record<string, unknown>, keys: readonly string[]) => displayScalar(evidenceValue(row, keys));
const moneyValue = (row: Record<string, unknown>, keys: readonly string[]) => {
  const value = evidenceValue(row, keys);
  return typeof value === "number" ? displayMoney(value) : displayScalar(value);
};

const ModeTrades: React.FC<{ mode: "PAPER" | "LIVE"; block: RuntimeSurfaceBlock }> = ({ mode, block }) => {
  const snapshot = block.snapshot;
  const orders = snapshot?.orders ?? [];
  const positions = snapshot?.positions ?? [];
  const events = snapshot?.events ?? [];

  return (
    <div className="af-trades-mode">
      <div className="af-trades-mode-head">
        <div>
          <span className="af-eyebrow">{mode} Runtime</span>
          <h2>{mode === "LIVE" ? "Live Oversight" : "Paper Trading"}</h2>
        </div>
        <div className="af-trades-mode-state">
          <span className={`af-surface-authority af-surface-authority-${block.state.toLowerCase()}`}>{block.state}</span>
          {mode === "LIVE" && <strong>READ_ONLY / DISARMED</strong>}
        </div>
      </div>

      {block.state !== "AVAILABLE" || !snapshot ? (
        <AuthorityMessage
          state="UNAVAILABLE"
          title={`${mode} trade authority`}
          unavailable={`${mode} orders/positions authority is unavailable. No sample trades are shown.`}
        />
      ) : (
        <>
          <section className="af-surface-metrics-grid compact">
            <MetricCell label="Orders" value={orders.length} />
            <MetricCell label="Positions" value={positions.length} />
            <MetricCell label="Events" value={events.length} />
            <MetricCell label="Source" value={displayScalar(snapshot.source)} />
          </section>

          <div className="af-trade-section">
            <div className="af-surface-subhead"><strong>Orders</strong><span>Authoritative blotter</span></div>
            {orders.length === 0 ? (
              <p className="af-surface-inline-note">No authoritative orders in this runtime.</p>
            ) : (
              <div className="af-surface-table-wrap">
                <table className="af-surface-table">
                  <thead><tr><th>Order</th><th>Strategy</th><th>Instrument</th><th>Side</th><th>Qty</th><th>Price</th><th>Status</th></tr></thead>
                  <tbody>
                    {orders.slice(0, 30).map((item, index) => {
                      const row = item as Record<string, unknown>;
                      return (
                        <tr key={`${rowValue(row, ["order_id", "id", "client_order_id"])}-${index}`}>
                          <td>{rowValue(row, ["order_id", "id", "client_order_id"])}</td>
                          <td>{rowValue(row, ["strategy_name", "strategy_id"])}</td>
                          <td>{rowValue(row, ["instrument", "symbol", "contract_identity"])}</td>
                          <td>{rowValue(row, ["side", "option_type", "direction"])}</td>
                          <td>{rowValue(row, ["quantity", "qty", "lots"])}</td>
                          <td>{moneyValue(row, ["price", "fill_price", "avg_price", "average_price"])}</td>
                          <td><span className="af-status-text">{rowValue(row, ["status", "state"])}</span></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="af-trade-section">
            <div className="af-surface-subhead"><strong>Open Positions</strong><span>Runtime projection</span></div>
            {positions.length === 0 ? (
              <p className="af-surface-inline-note">No authoritative open positions in this runtime.</p>
            ) : (
              <div className="af-surface-table-wrap">
                <table className="af-surface-table">
                  <thead><tr><th>Strategy</th><th>Instrument</th><th>Qty</th><th>Entry</th><th>Current</th><th>P&L</th><th>State</th></tr></thead>
                  <tbody>
                    {positions.slice(0, 30).map((item, index) => {
                      const row = item as Record<string, unknown>;
                      return (
                        <tr key={`${rowValue(row, ["position_id", "instrument", "symbol"])}-${index}`}>
                          <td>{rowValue(row, ["strategy_name", "strategy_id"])}</td>
                          <td>{rowValue(row, ["instrument", "symbol", "contract_identity"])}</td>
                          <td>{rowValue(row, ["quantity", "qty", "lots"])}</td>
                          <td>{moneyValue(row, ["entry_price", "avg_price", "average_price"])}</td>
                          <td>{moneyValue(row, ["current_price", "ltp", "mark_price"])}</td>
                          <td>{moneyValue(row, ["pnl", "unrealized_pnl", "open_pnl"])}</td>
                          <td>{rowValue(row, ["status", "state", "trade_state"])}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {snapshot.limitations.length > 0 && (
            <div className="af-runtime-limitations">
              <strong>Runtime limitations</strong>
              {snapshot.limitations.map((item, index) => <span key={`${item}-${index}`}>{item}</span>)}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export const UserTrades: React.FC<UserTradesProps> = ({ loadData = loadTradingSurface }) => {
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

  const blocks = useMemo(() => data ?? {
    PAPER: { state: "UNAVAILABLE" as const, snapshot: null },
    LIVE: { state: "UNAVAILABLE" as const, snapshot: null },
  }, [data]);

  return (
    <div className="af-user-surface" data-testid="trades-surface">
      <UserSurfaceHeader
        eyebrow="Execution Evidence"
        title="Trades"
        description="Order, fill, position, and runtime evidence separated by execution mode. This workspace observes authority; it does not bypass RiskGateV2 or broker controls."
        aside={<div className="af-surface-lock"><span>LIVE</span><strong>READ_ONLY / DISARMED</strong></div>}
      />

      {!data ? <AuthorityMessage state="LOADING" title="Trade runtime" unavailable="" /> : null}

      <div className="af-trades-stack">
        <ModeTrades mode="PAPER" block={blocks.PAPER} />
        <ModeTrades mode="LIVE" block={blocks.LIVE} />
      </div>
    </div>
  );
};
