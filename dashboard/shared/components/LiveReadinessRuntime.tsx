import React, { useEffect, useRef, useState } from "react";
import { Panel, KV, TruthChip } from "../utilities/V3Chrome";
import { liveReadinessRequest, type LiveReadiness, type LiveIntentReceipt, type LiveOversight } from "../services/integrationClient";

const show = (v: unknown): string => v === null || v === undefined ? "UNAVAILABLE" : String(v);
const Rows: React.FC<{ rows: Record<string, unknown>[] | null; columns: string[] }> = ({ rows, columns }) =>
  rows === null ? <p>UNAVAILABLE — no broker observation</p> : !rows.length ? <p>No records in the broker observation.</p> :
    <div style={{ overflowX: "auto", maxWidth: "100%" }}><table className="v3-table"><thead><tr>{columns.map(c => <th key={c}>{c.replaceAll("_", " ")}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{columns.map(c => <td key={c} style={{ overflowWrap: "anywhere" }}>{show(r[c])}</td>)}</tr>)}</tbody></table></div>;

/** Runtime only. Preview mounts the existing explicit fixture screens. */
export const LiveReadinessRuntime: React.FC<{ view?: "trading" | "connections" | "owner" }> = ({ view = "trading" }) => {
  const owner = view === "owner";
  const [data, setData] = useState<LiveReadiness | null>(null);
  const [oversight, setOversight] = useState<LiveOversight | null>(null);
  const [receipt, setReceipt] = useState<LiveIntentReceipt | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [strategy, setStrategy] = useState("");
  const [instrument, setInstrument] = useState("UNRESOLVED");
  const [quantity, setQuantity] = useState("50");
  const [side, setSide] = useState("BUY");
  const origin = useRef(new Date().toISOString());
  const generation = useRef(0);
  const root = `/api/v1/${owner ? "owner" : "user"}/live-readiness`;
  const load = async (broker = false, quiet = false) => {
    const version = ++generation.current;
    if (!quiet) { setBusy(true); setData(null); setOversight(null); }
    setError(null);
    try {
      const result = await liveReadinessRequest<LiveReadiness & LiveOversight>(root + (broker ? "/refresh" : ""), broker ? {} : undefined);
      if (version !== generation.current) return;
      if (owner) setOversight(result);
      else { setData(result); setStrategy(s => s || result.strategies[0]?.id || "UNRESOLVED"); setInstrument(s => s === "UNRESOLVED" ? result.instruments[0]?.token || s : s); }
    } catch (e) { if (version === generation.current) { setError(String(e)); setReceipt(null); setData(null); setOversight(null); } }
    finally { if (version === generation.current) setBusy(false); }
  };
  useEffect(() => { void load(); return () => { generation.current++; }; }, [view]);
  // Poll backend-derived freshness; never silently perform external broker reads.
  useEffect(() => { const timer = setInterval(() => { if (!busy) void load(false, true); }, 5000); return () => clearInterval(timer); }, [view, busy]);
  const validate = async (mode: "SHADOW" | "LIVE" = "SHADOW") => {
    setBusy(true); setError(null); setReceipt(null);
    try {
      const rec = await liveReadinessRequest<LiveIntentReceipt>(root + "/intents", {
        strategy_id: strategy, instrument_token: instrument, side, quantity, timeframe: "1m", originating_timestamp: origin.current, execution_mode: mode,
      });
      setReceipt(rec);
      await load(false, true);
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  };
  const hold = async () => {
    setBusy(true); setError(null);
    try { await liveReadinessRequest(root + "/hold", { enabled: !oversight?.execution_policy.global_hold }); await load(); }
    catch (e) { setError(String(e)); } finally { setBusy(false); }
  };
  const policy = data?.execution_policy || oversight?.execution_policy;
  const changed = () => { origin.current = new Date().toISOString(); setReceipt(null); };
  const brokerConnected = data?.connection_state === "CONNECTED";
  return <div data-testid="live-readiness-runtime" style={{ minWidth: 0 }}>
    <div className="v3-screen-head"><div><h2 className="v3-screen-title">{owner ? "Live Readiness Oversight" : view === "trading" ? "Live Trading Readiness" : "Broker Connections"}</h2>
      <p className="v3-screen-sub">EXECUTION: SHADOW / READ_ONLY · {brokerConnected ? "BROKER: CONNECTED (TEST-ONLY)" : "BROKER: NOT CONNECTED"} · Real execution disabled</p></div><TruthChip kind={data || oversight ? "REAL" : "DISABLED"} title="Backend readiness authority; broker availability is reported separately" /></div>
    <div className="v3-filter-bar" style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 16 }}>
      <button className="v3-btn ghost" disabled={busy} onClick={() => void load()}>Refresh readiness</button>
      {!owner && <button className="v3-btn" disabled={busy || !data} onClick={() => void load(true)}>Read broker account</button>}
      <button className="v3-btn" disabled title="Final backend gate blocks all production mutations">Execution disabled</button>
    </div>
    {error && <p role="alert">UNAVAILABLE — {error}</p>}
    <Panel label="Execution policy"><KV k="Execution authorization" v="READ_ONLY / DISARMED — EXECUTION_DISABLED" />
      <KV k="Execution Mode" v="SHADOW / READ_ONLY" />
      <KV k="Broker Connection" v={brokerConnected ? "CONNECTED (TEST-ONLY)" : "NOT CONNECTED"} />
      <KV k="Global execution hold" v={policy ? (policy.global_hold ? "HELD" : "RELEASED — execution remains disabled") : "UNAVAILABLE"} />
      <KV k="Safe Mode" v={policy ? (policy.safe_mode ? "ON" : "OFF") : "UNAVAILABLE"} />
      {owner && <button className="v3-btn ghost" disabled={busy || !oversight} onClick={() => void hold()}>{policy?.global_hold ? "Release global hold" : "Apply global hold"}</button>}
    </Panel>
    {owner && <Panel label="Tenant readiness">{!oversight?.users.length && <p>No broker observations or configured tenant bindings.</p>}
      {oversight?.users.map(u => <div key={u.user_id} style={{ marginBottom: 20 }}><KV k="User" v={u.user_id} /><KV k="Connection / account" v={`${u.connection_state} / ${show(u.account?.user_id)}`} />
        <KV k="Market / reconciliation" v={`${u.market_data_state} / ${u.reconciliation.state}`} /><KV k="Last success / failure" v={`${show(u.last_success)} / ${show(u.last_failure)}`} />
        <Rows rows={u.intents.map(i => ({ ...i, reasons: i.reasons.map(r => r.code).join(", ") }))} columns={["intent_id", "status", "reasons", "audit_id"]} /></div>)}</Panel>}
    {data && <>
      <Panel label="Broker read authority"><KV k="Provider / connection" v={`${data.provider} / ${data.connection_state}`} /><KV k="Broker account" v={show(data.account?.user_id)} />
        <KV k="Read error" v={data.error || "NONE"} /><KV k="Last success" v={show(data.last_success)} /><KV k="Last failure" v={show(data.last_failure)} />
        <KV k="Available margin" v={show(data.funds?.available_margin)} /><KV k="Used margin" v={show(data.funds?.used_margin)} />
        <KV k="Account equity / aggregate exposure" v="UNAVAILABLE — canonical live account required" /><KV k="Reconciliation" v={data.reconciliation.state} />
        <KV k="Differences" v={data.reconciliation.differences.join(", ") || "NONE OBSERVED"} /><KV k="Audit reference" v={show(data.audit_id)} />
      </Panel>
      <Panel label={`Market data · ${data.market_data_state}`}><Rows rows={data.market_data} columns={["symbol", "ltp", "bid", "ask", "state", "exchange_timestamp", "received_timestamp", "source"]} /></Panel>
      {view === "trading" && <Panel label="Validate live intent"><p>Validation records governance and risk decisions. Every intent stops at the disabled execution gate.</p>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "end" }}>
          <label>Strategy<select className="v3-input" aria-label="Live strategy" value={strategy} onChange={e => { setStrategy(e.target.value); changed(); }}>{data.strategies.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
          <label>Instrument<select className="v3-input" aria-label="Live instrument" value={instrument} onChange={e => { setInstrument(e.target.value); changed(); }}><option value="UNRESOLVED">UNRESOLVED</option>{data.instruments.map(i => <option key={i.token} value={i.token}>{i.symbol} · lot {i.lot_size}</option>)}</select></label>
          <label>Side<select className="v3-input" value={side} onChange={e => { setSide(e.target.value); changed(); }}><option>BUY</option><option>SELL</option></select></label>
          <label>Quantity<input className="v3-input" aria-label="Live quantity" type="number" min="1" max="10000000" value={quantity} onChange={e => { setQuantity(e.target.value); changed(); }} /></label>
          <button className="v3-btn" disabled={busy || !strategy || Number(quantity) <= 0} onClick={() => void validate("SHADOW")}>Validate / Shadow Execute</button>
          <button className="v3-btn ghost" disabled={busy || !strategy || Number(quantity) <= 0} onClick={() => void validate("LIVE")}>Validate intent</button>
        </div><KV k="Risk authority" v={data.risk_state} /><KV k="Execution Mode" v="SHADOW (Dry-run validation)" />
        {receipt && <div role="status" data-testid="live-intent-result" style={{ marginTop: 16 }}>
          <h3>{receipt.status} · {receipt.execution_mode || "SHADOW"}</h3>
          <p style={{ overflowWrap: "anywhere" }}>{receipt.intent_id}</p>
          {Boolean(receipt.reasons?.length) && <ul>{receipt.reasons.map((r, i) => <li key={i}>{r.code} — {r.detail}</li>)}</ul>}
          {receipt.would_be_payload && <div data-testid="would-be-payload" style={{ marginTop: 12, padding: 12, background: "rgba(0,0,0,0.2)", borderRadius: 6 }}>
            <h4>Would-Be Broker Request Summary</h4>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 8, marginTop: 8 }}>
              {Object.entries(receipt.would_be_payload).map(([k, v]) => <KV key={k} k={k.replaceAll("_", " ")} v={show(v)} />)}
            </div>
          </div>}
          <KV k="Audit reference" v={receipt.audit_id} />
        </div>}
      </Panel>}
      <Panel label="Broker capabilities"><Rows rows={data.capabilities} columns={["name", "connector_support", "observed_available", "effective"]} /></Panel>
      <Panel label="Existing broker positions"><Rows rows={data.positions} columns={["trading_symbol", "quantity", "average_price", "last_price", "pnl"]} />
        <h3>Existing broker orders</h3><Rows rows={data.orders} columns={["order_id", "trading_symbol", "transaction_type", "quantity", "filled_quantity", "status"]} />
        <h3>Holdings</h3><Rows rows={data.holdings} columns={["trading_symbol", "quantity", "average_price"]} /></Panel>
      <Panel label="Shadow Execution History" id="shadow-execution-history-panel">
        {!data.intents.length ? <p>No shadow executions</p> :
          <Rows rows={data.intents.map(i => ({ ...i, reasons: i.reasons.map(r => r.code).join(", ") }))} columns={["intent_id", "status", "reasons", "audit_id"]} />
        }
      </Panel>
    </>}
  </div>;
};
