import React, { useEffect, useRef, useState } from "react";
import { Panel, Drawer, KV, TruthChip } from "../utilities/V3Chrome";
import {
  queryOrdersPortfolio, queryOrderDetail, type OrdersPortfolioMode,
  type OrdersPortfolioSnapshot, type RuntimeEvidence,
} from "../services/integrationClient";

type Tab = "portfolio" | "positions" | "orders";
const value = (v: unknown): string => v === null || v === undefined || v === "" ? "UNAVAILABLE"
  : typeof v === "number" ? new Intl.NumberFormat("en-IN", { useGrouping: false, maximumFractionDigits: 2 }).format(v) : String(v);
const money = (v: unknown): string => typeof v === "number"
  ? new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 }).format(v)
  : "UNAVAILABLE";

const orderColumns = [
  ["order_id", "Order ID"], ["session_id", "Session"], ["execution_mode", "Mode"],
  ["strategy_name", "Strategy"], ["instrument", "Instrument"], ["side", "Side"],
  ["qty", "Quantity"], ["order_type", "Type"], ["limit_price", "Submitted price"],
  ["fill_price", "Fill price"], ["status", "Status"], ["rejection_reason", "Rejection reason"],
  ["data_source_mode", "Data source"], ["created_at_utc", "Recorded at"], ["filled_at_utc", "Filled at"],
];
const positionColumns = [
  ["resolved_contract", "Instrument"], ["session_id", "Session"], ["execution_mode", "Mode"],
  ["strategy_name", "Strategy"], ["status", "Status"], ["qty", "Quantity"],
  ["avg_price", "Average entry"], ["ltp", "Stored mark / exit"], ["current_value", "Stored value"],
  ["unrealized_pnl", "Unrealized P&L"], ["realized_pnl", "Realized P&L"],
  ["data_source_mode", "Data source"], ["feed_status", "Feed"],
];
const accountColumns = [
  ["session_id", "Session account"], ["strategy_name", "Strategy"], ["execution_mode", "Mode"],
  ["status", "Session state"], ["available_cash", "Available cash"], ["used_capital", "Committed capital"],
  ["reserved_cash", "Reserved cash"], ["current_equity", "Equity"], ["realized_pnl", "Realized P&L"],
  ["unrealized_pnl", "Unrealized P&L"], ["total_pnl", "Total P&L"], ["owner_allowance", "Owner allowance"],
  ["data_source_mode", "Data source"], ["feed_status", "Feed"],
];

/** Mounted only in authenticated runtime. Preview mounts the existing fixture screens. */
export const OrdersPortfolioRuntime: React.FC<{ owner?: boolean; initialTab?: Tab }> = ({ owner = false, initialTab = "portfolio" }) => {
  const [tab, setTab] = useState<Tab>(initialTab);
  const [mode, setMode] = useState<OrdersPortfolioMode>("PAPER");
  const [snapshot, setSnapshot] = useState<OrdersPortfolioSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<RuntimeEvidence | null>(null);
  const [search, setSearch] = useState("");
  const generation = useRef(0);

  const refresh = async () => {
    const request = ++generation.current;
    setLoading(true); setSnapshot(null); setSelected(null); setError(null);
    try {
      const data = await queryOrdersPortfolio(owner, mode);
      if (request === generation.current) setSnapshot(data);
    } catch (e) {
      if (request === generation.current) setError(e instanceof Error ? e.message : "Authority unavailable");
    } finally {
      if (request === generation.current) setLoading(false);
    }
  };
  useEffect(() => { void refresh(); return () => { generation.current++; }; }, [owner, mode]);
  useEffect(() => { setTab(initialTab); setSelected(null); }, [initialTab]);
  const authoritative = snapshot?.availability === "AVAILABLE" && (snapshot.source === "PERSISTED_PAPER_RUNTIME" || snapshot.source === "ALGOFORTIS_SHADOW_RUNTIME");
  const accounts = snapshot?.accounts ?? [];
  const matching = (rows: RuntimeEvidence[]) => rows.filter(row =>
    !search || Object.values(row).some(v => String(v ?? "").toLowerCase().includes(search.toLowerCase())));
  const rows = matching(tab === "orders" ? snapshot?.orders ?? [] : tab === "positions" ? snapshot?.positions ?? [] : accounts);
  const columns = (owner ? [["user_id", "User"]] : []).concat(tab === "orders" ? orderColumns : tab === "positions" ? positionColumns : accountColumns);

  const inspect = async (row: RuntimeEvidence) => {
    if (tab !== "orders" || owner) { setSelected(row); return; }
    const request = generation.current;
    try {
      const detail = await queryOrderDetail(row.session_id, String(row.order_id));
      if (request === generation.current) setSelected(detail);
    } catch (e) {
      if (request === generation.current) { setSelected(null); setSnapshot(null); setError(String(e)); }
    }
  };
  const title = owner ? "Portfolio & Orders Oversight" : initialTab === "orders" ? "Orders" : "Portfolio";
  return <div data-testid="orders-portfolio-runtime">
    <div className="v3-screen-head">
      <div><h2 className="v3-screen-title">{title}</h2><p className="v3-screen-sub">Persisted paper execution · session accounts · read-only {owner ? "system-wide oversight" : "your orders and positions"}</p></div>
      <TruthChip kind={authoritative ? "REAL" : "DISABLED"} title={authoritative ? "Loaded from persisted paper runtime evidence" : "Authoritative data unavailable"} />
    </div>
    <div className="v3-filter-bar" style={{ display: "flex", flexWrap: "wrap", gap: 10, marginBottom: 16 }}>
      <label style={{ display: "flex", alignItems: "center", gap: 8 }}>Execution mode <select className="v3-input" style={{ width: 260 }} aria-label="Execution mode" value={mode} onChange={e => { setSnapshot(null); setSelected(null); setMode(e.target.value as OrdersPortfolioMode); }}>
        <option value="PAPER">PAPER</option><option value="LIVE">LIVE — UNAVAILABLE</option><option value="BACKTEST">BACKTEST — Backtesting screen</option><option value="SHADOW">SHADOW — Dry-Run Validation</option>
      </select></label>
      <input className="v3-input" style={{ width: 260 }} aria-label="Search persisted evidence" placeholder="Search session, instrument, status…" value={search} onChange={e => setSearch(e.target.value)} />
      <button type="button" className="v3-btn ghost mini" onClick={() => void refresh()} disabled={loading}>Refresh</button>
    </div>
    <p className="v3-screen-sub">PAPER uses virtual execution. LIVE broker execution is UNAVAILABLE. Historical option prices are modeled; marks shown are stored values.</p>
    {loading && <p role="status">Loading authoritative evidence…</p>}
    {error && <p role="alert">{error}. UNAVAILABLE — refresh to retry.</p>}
    {snapshot?.availability === "UNAVAILABLE" && <p role="status">{mode} Orders / Portfolio UNAVAILABLE{mode === "BACKTEST" ? "; inspect runs in Backtesting." : "; no live broker orders or accounts are connected."}</p>}
    {authoritative && <>
      <div className="v3-tabs" role="tablist" aria-label="Orders and portfolio views" style={{ marginBottom: 16 }}>
        {(["portfolio", "positions", "orders"] as Tab[]).map(t => <button type="button" role="tab" aria-selected={tab === t} className={`v3-btn ghost mini ${tab === t ? "active" : ""}`} key={t} onClick={() => { setTab(t); setSelected(null); }}>{t === "portfolio" ? "Accounts" : t === "positions" ? "Positions" : "Orders"}</button>)}
      </div>
      {tab === "portfolio" && accounts.length === 1 && <div className="v3-grid" style={{ marginBottom: 16 }}>
        {[["available_cash", "Available Cash"], ["current_equity", "Account Equity"], ["realized_pnl", "Realized P&L"], ["unrealized_pnl", "Unrealized P&L"]].map(([key, label]) => <div className="v3-kpi v3-sp3" key={key}><div className="v3-kpi-title">{label}</div><div className="v3-kpi-value">{money(accounts[0][key])}</div></div>)}
      </div>}
      <Panel label={tab === "portfolio" ? "Paper Session Accounts" : tab === "positions" ? "Open & Closed Positions" : "Order & Fill Evidence"} meta={`${rows.length} persisted records · INR`}>
        <div style={{ overflowX: "auto", maxHeight: 520 }} tabIndex={0} role="region" aria-label="Scrollable persisted evidence"><table className="v3-table" style={{ width: "max-content", minWidth: "100%", whiteSpace: "nowrap" }} data-testid="runtime-evidence-table"><thead><tr><th scope="col">Inspect</th>{columns.map(([key, label]) => <th scope="col" key={key}>{label}</th>)}</tr></thead>
          <tbody>{rows.map((row, i) => <tr key={`${row.session_id}:${row.order_id ?? row.position_id ?? i}`}><td><button type="button" className="v3-btn ghost mini" aria-label={`Inspect ${row.order_id ?? row.position_id ?? row.session_id}`} onClick={() => void inspect(row)}>Details</button></td>{columns.map(([key]) => <td key={key} title={value(row[key])} style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", textAlign: typeof row[key] === "number" ? "right" : "left", fontFamily: typeof row[key] === "number" || key.endsWith("_id") ? "var(--v3-mono)" : undefined }}>{value(row[key])}</td>)}</tr>)}</tbody></table></div>
        {rows.length === 0 && <p role="status" style={{ padding: 16 }}>{tab === "orders" ? "No orders yet" : tab === "positions" ? "No positions" : "No persisted accounts in this scope."}</p>}
      </Panel>
      <Panel label="Paper Runtime Events & Risk Blocks" meta="Session event identity; Core Audit link unavailable">
        <div style={{ overflow: "auto", maxHeight: 360 }} tabIndex={0} role="region" aria-label="Scrollable paper events"><table className="v3-table" style={{ minWidth: 900 }} data-testid="runtime-events-table"><thead><tr>{["Event ID", "Session", "Time", "Status", "Source", "Evidence"].map(x => <th scope="col" key={x}>{x}</th>)}</tr></thead><tbody>{matching(snapshot.events).map(event => <tr key={`${event.session_id}:${event.event_id}`}>{[event.event_id, event.session_id, event.event_time, event.status, event.source, event.detail].map((v, i) => <td key={i} style={{ whiteSpace: i < 5 ? "nowrap" : undefined, minWidth: i === 5 ? 400 : undefined, overflowWrap: "anywhere" }}>{value(v)}</td>)}</tr>)}</tbody></table></div>
      </Panel>
      <p className="v3-screen-sub">Account figures are stored paper runtime summaries. Reserved cash, aggregate exposure, protective links, per-position realized P&amp;L and engine reconciliation reports: UNAVAILABLE. Session accounts remain separate.</p>
    </>}
    {selected && <Drawer open title="Persisted Runtime Evidence" onClose={() => setSelected(null)}>{Object.entries(selected).map(([key, v]) => <KV key={key} k={key.replaceAll("_", " ")} v={value(v)} />)}</Drawer>}
  </div>;
};
