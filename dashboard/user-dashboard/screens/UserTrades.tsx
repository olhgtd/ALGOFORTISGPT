import React, { useEffect, useMemo, useState } from "react";
import {
  createPaperSession,
  queryPaperSessions,
  startPaperSession,
  stopPaperSession,
  type AuthoritativePaperSession,
} from "../../shared/services/integrationClient";
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
  loadPaperSessionsAction?: typeof queryPaperSessions;
  createPaperSessionAction?: typeof createPaperSession;
  startPaperSessionAction?: typeof startPaperSession;
  stopPaperSessionAction?: typeof stopPaperSession;
}

type PaperSessionAuthorityState = "LOADING" | "AVAILABLE" | "STALE" | "UNKNOWN" | "UNAVAILABLE";

const rowValue = (row: Record<string, unknown>, keys: readonly string[]) => displayScalar(evidenceValue(row, keys));
const moneyValue = (row: Record<string, unknown>, keys: readonly string[]) => {
  const value = evidenceValue(row, keys);
  return typeof value === "number" ? displayMoney(value) : displayScalar(value);
};

const sessionAuthority = (result: Awaited<ReturnType<typeof queryPaperSessions>>): PaperSessionAuthorityState => {
  if (result.source !== "BACKEND") return "UNAVAILABLE";
  if (result.trust === "FRESH") return "AVAILABLE";
  if (result.trust === "STALE") return "STALE";
  return "UNKNOWN";
};

const canStartPaper = (status: unknown) => ["INITIALIZED", "READY", "PAUSED"].includes(String(status || "").toUpperCase());
const canStopPaper = (status: unknown) => ["RUNNING", "ACTIVE", "RECONNECTING", "STALE"].includes(String(status || "").toUpperCase());

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

export const UserTrades: React.FC<UserTradesProps> = ({
  loadData = loadTradingSurface,
  loadPaperSessionsAction = queryPaperSessions,
  createPaperSessionAction = createPaperSession,
  startPaperSessionAction = startPaperSession,
  stopPaperSessionAction = stopPaperSession,
}) => {
  const [data, setData] = useState<TradingSurfaceData | null>(null);
  const [paperSessions, setPaperSessions] = useState<AuthoritativePaperSession[]>([]);
  const [paperSessionsState, setPaperSessionsState] = useState<PaperSessionAuthorityState>("LOADING");
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const [strategyId, setStrategyId] = useState("");
  const [instrument, setInstrument] = useState("NIFTY");
  const [timeframe, setTimeframe] = useState("5m");
  const [initialCapital, setInitialCapital] = useState(50000);
  const [dataSourceMode, setDataSourceMode] = useState("HISTORICAL_REPLAY");
  const [datasetId, setDatasetId] = useState("");
  const [dateRange, setDateRange] = useState("2026-01-05");

  const applySessionsResult = (result: Awaited<ReturnType<typeof queryPaperSessions>>) => {
    const authority = sessionAuthority(result);
    setPaperSessionsState(authority);
    setPaperSessions(authority === "AVAILABLE" ? result.data : []);
  };

  useEffect(() => {
    let active = true;
    setData(null);
    setPaperSessionsState("LOADING");
    loadData().then((next) => { if (active) setData(next); }).catch(() => {
      if (active) setData({
        PAPER: { state: "UNAVAILABLE", snapshot: null },
        LIVE: { state: "UNAVAILABLE", snapshot: null },
      });
    });
    loadPaperSessionsAction().then((result) => {
      if (!active) return;
      const authority = sessionAuthority(result);
      setPaperSessionsState(authority);
      setPaperSessions(authority === "AVAILABLE" ? result.data : []);
    }).catch(() => {
      if (active) {
        setPaperSessionsState("UNAVAILABLE");
        setPaperSessions([]);
      }
    });
    return () => { active = false; };
  }, [loadData, loadPaperSessionsAction]);

  const refreshAfterMutation = async (successMessage: string) => {
    setActionMessage(successMessage);
    const [runtimeResult, sessionsResult] = await Promise.allSettled([loadData(), loadPaperSessionsAction()]);
    let refreshFailed = false;
    if (runtimeResult.status === "fulfilled") setData(runtimeResult.value);
    else refreshFailed = true;
    if (sessionsResult.status === "fulfilled") applySessionsResult(sessionsResult.value);
    else refreshFailed = true;
    if (refreshFailed) setActionMessage(`${successMessage} Refresh unavailable; previous evidence retained where available.`);
  };

  const createSession = async () => {
    if (paperSessionsState !== "AVAILABLE" || pendingAction || !strategyId.trim() || initialCapital <= 0) return;
    setPendingAction("paper-create");
    setActionMessage(null);
    try {
      const payload = {
        strategy_id: strategyId.trim(),
        instrument: instrument.trim(),
        timeframe: timeframe.trim(),
        initial_capital: initialCapital,
        data_source_mode: dataSourceMode,
        ...(datasetId.trim() ? { dataset_id: datasetId.trim() } : {}),
        ...(dateRange.trim() ? { date_range: dateRange.trim() } : {}),
      };
      const result = await createPaperSessionAction(payload);
      if (!result.ok) {
        setActionMessage(result.error || "Paper session creation rejected by backend authority.");
        return;
      }
      await refreshAfterMutation(`Paper session created${result.data?.session_id ? ` · ${result.data.session_id}` : ""}.`);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "Paper session creation failed.");
    } finally {
      setPendingAction(null);
    }
  };

  const startSession = async (sessionId: string) => {
    if (pendingAction) return;
    setPendingAction(`paper-start:${sessionId}`);
    setActionMessage(null);
    try {
      const result = await startPaperSessionAction(sessionId);
      if (!result.ok) {
        setActionMessage(result.error || "Paper session start rejected by backend authority.");
        return;
      }
      await refreshAfterMutation(`Paper session started · ${sessionId}.`);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "Paper session start failed.");
    } finally {
      setPendingAction(null);
    }
  };

  const stopSession = async (sessionId: string) => {
    if (pendingAction) return;
    setPendingAction(`paper-stop:${sessionId}`);
    setActionMessage(null);
    try {
      const result = await stopPaperSessionAction(sessionId);
      if (!result.ok) {
        setActionMessage(result.error || "Paper session stop rejected by backend authority.");
        return;
      }
      await refreshAfterMutation(`Paper session stopped · ${sessionId}.`);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "Paper session stop failed.");
    } finally {
      setPendingAction(null);
    }
  };

  const blocks = useMemo(() => data ?? {
    PAPER: { state: "UNAVAILABLE" as const, snapshot: null },
    LIVE: { state: "UNAVAILABLE" as const, snapshot: null },
  }, [data]);

  const fieldsStyle: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))",
    gap: 8,
  };

  return (
    <div className="af-user-surface" data-testid="trades-surface">
      <UserSurfaceHeader
        eyebrow="Execution Evidence"
        title="Trades"
        description="Paper runtime control and authoritative order, fill, position, and runtime evidence separated by execution mode. Real-money Live remains observation-only."
        aside={<div className="af-surface-lock"><span>LIVE</span><strong>READ_ONLY / DISARMED</strong></div>}
      />

      {!data ? <AuthorityMessage state="LOADING" title="Trade runtime" unavailable="" /> : null}
      {actionMessage && <div className="af-surface-inline-note" role="status">{actionMessage}</div>}

      <SurfacePanel eyebrow="Paper Control" title="Paper Sessions" authority={paperSessionsState}>
        <p className="af-surface-inline-note">Paper orders are simulated. Creating or starting a Paper session never routes a real broker order.</p>
        <div style={fieldsStyle}>
          <input className="v3-input" aria-label="Paper strategy ID" value={strategyId} onChange={(event) => setStrategyId(event.target.value)} placeholder="Strategy ID" />
          <input className="v3-input" aria-label="Paper instrument" value={instrument} onChange={(event) => setInstrument(event.target.value)} placeholder="Instrument" />
          <input className="v3-input" aria-label="Paper timeframe" value={timeframe} onChange={(event) => setTimeframe(event.target.value)} placeholder="Timeframe" />
          <input className="v3-input" aria-label="Paper initial capital" type="number" value={initialCapital} onChange={(event) => setInitialCapital(Number(event.target.value) || 0)} />
          <select className="v3-input" aria-label="Paper data source mode" value={dataSourceMode} onChange={(event) => setDataSourceMode(event.target.value)}>
            <option value="HISTORICAL_REPLAY">HISTORICAL_REPLAY</option>
            <option value="LIVE_MARKET">LIVE_MARKET</option>
          </select>
          <input className="v3-input" aria-label="Paper dataset ID" value={datasetId} onChange={(event) => setDatasetId(event.target.value)} placeholder="Dataset ID (historical)" />
          <input className="v3-input" aria-label="Paper date range" value={dateRange} onChange={(event) => setDateRange(event.target.value)} placeholder="YYYY-MM-DD or backend range" />
        </div>
        <button
          type="button"
          className="v3-button"
          style={{ marginTop: 10 }}
          disabled={paperSessionsState !== "AVAILABLE" || Boolean(pendingAction) || !strategyId.trim() || initialCapital <= 0}
          onClick={() => { void createSession(); }}
        >{pendingAction === "paper-create" ? "Creating…" : "Create Paper Session"}</button>
        {paperSessionsState !== "AVAILABLE" && <p className="af-surface-inline-note">Paper mutation is disabled until session authority is AVAILABLE.</p>}

        {paperSessionsState === "AVAILABLE" && (
          paperSessions.length === 0 ? (
            <p className="af-surface-inline-note">No authoritative Paper sessions are recorded.</p>
          ) : (
            <div className="af-surface-table-wrap" style={{ marginTop: 12 }}>
              <table className="af-surface-table">
                <thead><tr><th>Session</th><th>Strategy</th><th>Instrument</th><th>Source</th><th>Status</th><th>P&L</th><th>Control</th></tr></thead>
                <tbody>
                  {paperSessions.map((session) => (
                    <tr key={session.session_id}>
                      <td><strong>{session.session_id}</strong></td>
                      <td>{displayScalar(session.strategy_name || session.strategy_id)}</td>
                      <td>{displayScalar(session.instrument)} · {displayScalar(session.timeframe)}</td>
                      <td>{displayScalar(session.data_source_mode)}</td>
                      <td><span className="af-status-text">{displayScalar(session.status)}</span></td>
                      <td>{displayMoney(session.total_pnl)}</td>
                      <td>
                        {canStartPaper(session.status) && <button type="button" aria-label={`Start paper session ${session.session_id}`} disabled={Boolean(pendingAction)} onClick={() => { void startSession(session.session_id); }}>Start</button>}
                        {canStopPaper(session.status) && <button type="button" aria-label={`Stop paper session ${session.session_id}`} disabled={Boolean(pendingAction)} onClick={() => { void stopSession(session.session_id); }}>Stop</button>}
                        {!canStartPaper(session.status) && !canStopPaper(session.status) ? "—" : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        )}
      </SurfacePanel>

      <div className="af-trades-stack">
        <ModeTrades mode="PAPER" block={blocks.PAPER} />
        <ModeTrades mode="LIVE" block={blocks.LIVE} />
      </div>
    </div>
  );
};
