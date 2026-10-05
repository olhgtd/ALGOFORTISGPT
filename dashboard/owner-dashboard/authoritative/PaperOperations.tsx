import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Panel } from "../../shared/utilities/V3Chrome";
import { AsyncActionButton, SimpleTable } from "./components";
import { useAsyncResource } from "./hooks";
import {
  createOwnerPaperSession,
  engageOwnerPaperHold,
  getOwnerPaperEvents,
  getOwnerPaperOrders,
  getOwnerPaperPositions,
  listOwnerPaperSessions,
  releaseOwnerPaperHold,
  startOwnerPaperSession,
  stopOwnerPaperSession,
} from "./paperOps";

const rowsFrom = (payload: any, key: string): any[] => Array.isArray(payload) ? payload : Array.isArray(payload?.[key]) ? payload[key] : [];

export const PaperOperations: React.FC = () => {
  const load = useCallback(() => listOwnerPaperSessions(), []);
  const { data, loading, error, refresh } = useAsyncResource(load);
  const sessions = useMemo(() => rowsFrom(data, "sessions"), [data]);
  const [strategyId, setStrategyId] = useState("");
  const [instrument, setInstrument] = useState("NIFTY");
  const [timeframe, setTimeframe] = useState("1m");
  const [capital, setCapital] = useState(50000);
  const [datasetId, setDatasetId] = useState("nse-tick-primary");
  const [dateRange, setDateRange] = useState("2026-01-05");
  const [selected, setSelected] = useState<string>("");
  const [detail, setDetail] = useState<{ positions: any[]; orders: any[]; events: any[] } | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    if (!selected) { setDetail(null); return; }
    let cancelled = false;
    Promise.all([getOwnerPaperPositions(selected), getOwnerPaperOrders(selected), getOwnerPaperEvents(selected)])
      .then(([positions, orders, events]) => {
        if (!cancelled) {
          setDetail({ positions: rowsFrom(positions, "positions"), orders: rowsFrom(orders, "orders"), events: rowsFrom(events, "events") });
          setDetailError(null);
        }
      })
      .catch((err) => { if (!cancelled) { setDetail(null); setDetailError(err?.message || "UNAVAILABLE"); } });
    return () => { cancelled = true; };
  }, [selected]);

  if (loading && !data) return <Panel>Loading Paper authority…</Panel>;

  return <>
    <div className="v3-screen-head"><div><h2 className="v3-screen-title">Paper Trading</h2><p className="v3-screen-sub">Simulated Paper authority only. Live remains READ_ONLY / DISARMED and no real broker order path is exposed.</p></div></div>
    {error && <div className="owner-authority-message unavailable"><strong>UNAVAILABLE</strong><div>{error}</div></div>}

    <Panel>
      <div className="v3-region-head"><span className="v3-region-title">Create Paper Session</span></div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 8 }}>
        <input className="v3-input" value={strategyId} onChange={(e) => setStrategyId(e.target.value)} placeholder="Strategy ID" />
        <input className="v3-input" value={instrument} onChange={(e) => setInstrument(e.target.value)} placeholder="Instrument" />
        <input className="v3-input" value={timeframe} onChange={(e) => setTimeframe(e.target.value)} placeholder="Timeframe" />
        <input className="v3-input" type="number" value={capital} onChange={(e) => setCapital(Number(e.target.value) || 0)} placeholder="Initial capital" />
        <input className="v3-input" value={datasetId} onChange={(e) => setDatasetId(e.target.value)} placeholder="Dataset ID" />
        <input className="v3-input" value={dateRange} onChange={(e) => setDateRange(e.target.value)} placeholder="Replay date range" />
      </div>
      <div style={{ marginTop: 12 }}>
        <AsyncActionButton label="Create Paper Session" disabled={!strategyId.trim()} onRun={() => createOwnerPaperSession({ strategy_id: strategyId.trim(), instrument: instrument.trim(), timeframe: timeframe.trim(), initial_capital: capital, data_source_mode: "HISTORICAL_REPLAY", dataset_id: datasetId.trim(), date_range: dateRange.trim() })} onDone={refresh} />
      </div>
    </Panel>

    <section className="v3-region v3-sp12">
      <div className="v3-region-head"><span className="v3-region-title">All Paper Sessions</span></div>
      <SimpleTable rows={sessions} columns={[
        { key: "session_id", label: "Session" }, { key: "strategy_id", label: "Strategy" }, { key: "status", label: "Status" },
        { key: "owner_hold", label: "HOLD" },
        { key: "actions", label: "Controls", render: (row) => {
          const id = String(row.session_id || row.id || "");
          return <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button type="button" className="v3-btn ghost mini" onClick={() => setSelected(id)}>Inspect</button>
            <AsyncActionButton label="Start" disabled={!id} onRun={() => startOwnerPaperSession(id)} onDone={refresh} />
            <AsyncActionButton label="Stop" tone="warn" disabled={!id} onRun={() => stopOwnerPaperSession(id)} onDone={refresh} />
            <AsyncActionButton label="HOLD" tone="danger" disabled={!id} onRun={() => engageOwnerPaperHold(id, "Owner safety hold")} onDone={refresh} />
            <AsyncActionButton label="Release HOLD" tone="warn" disabled={!id} onRun={() => releaseOwnerPaperHold(id, "Owner verified hold release")} onDone={refresh} />
          </div>;
        } },
      ]} />
    </section>

    {selected && <Panel>
      <div className="v3-region-head"><span className="v3-region-title">Session Detail · {selected}</span></div>
      {detailError && <div className="owner-authority-message unavailable"><strong>UNAVAILABLE</strong><div>{detailError}</div></div>}
      <div className="v3-grid">
        <section className="v3-region v3-sp4"><div className="v3-region-title">Positions</div><SimpleTable rows={detail?.positions || []} columns={[{ key: "instrument", label: "Instrument" }, { key: "quantity", label: "Qty" }, { key: "pnl", label: "PnL" }]} /></section>
        <section className="v3-region v3-sp4"><div className="v3-region-title">Orders</div><SimpleTable rows={detail?.orders || []} columns={[{ key: "order_id", label: "Order" }, { key: "side", label: "Side" }, { key: "status", label: "Status" }]} /></section>
        <section className="v3-region v3-sp4"><div className="v3-region-title">Events</div><SimpleTable rows={detail?.events || []} columns={[{ key: "event_type", label: "Event" }, { key: "timestamp", label: "Time" }]} /></section>
      </div>
    </Panel>}
  </>;
};
