import React, { useCallback } from "react";
import { Panel } from "../../shared/utilities/V3Chrome";
import { AsyncActionButton, AuthorityBadge } from "./components";
import { useAsyncResource } from "./hooks";
import { engageGlobalHold, engageSafeMode, queryOwnerSafety, releaseGlobalHold } from "./safetyOps";

const state = (value: any) => value === "AVAILABLE" || value === "STALE" || value === "UNKNOWN" || value === "UNAVAILABLE" ? value : "UNAVAILABLE";

export const RiskSafetyScreen: React.FC = () => {
  const load = useCallback(() => queryOwnerSafety(), []);
  const { data, loading, error, refresh } = useAsyncResource(load);
  if (loading && !data) return <Panel>Loading safety authority…</Panel>;
  const safe = data?.safe_mode || { state: "UNAVAILABLE", enabled: null };
  const hold = data?.global_hold || { state: "UNAVAILABLE", enabled: null };
  const risk = data?.risk_gate || { state: "UNAVAILABLE" };
  const kill = data?.kill_switch || { state: "NOT_CONNECTED" };
  return <>
    <div className="v3-screen-head"><div><h2 className="v3-screen-title">Risk & Safety</h2><p className="v3-screen-sub">Truthful safety authority only. Live is permanently READ_ONLY/DISARMED in this runtime.</p></div></div>
    {error && <div className="owner-authority-message unavailable"><strong>UNAVAILABLE</strong><div>{error}</div></div>}
    <div className="v3-grid">
      <section className="v3-region v3-sp4"><div className="v3-region-head"><span className="v3-region-title">Safe Mode</span><AuthorityBadge state={state(safe.state)} /></div><div className="v3-stat-big">{safe.enabled === true ? "ENGAGED" : safe.enabled === false ? "CLEAR" : "—"}</div><AsyncActionButton label="Engage Safe Mode" tone="danger" disabled={safe.state !== "AVAILABLE" || safe.enabled === true} onRun={engageSafeMode} onDone={refresh} /></section>
      <section className="v3-region v3-sp4"><div className="v3-region-head"><span className="v3-region-title">Global Hold</span><AuthorityBadge state={state(hold.state)} /></div><div className="v3-stat-big">{hold.enabled === true ? "ACTIVE" : hold.enabled === false ? "CLEAR" : "—"}</div><div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}><AsyncActionButton label="Engage Global Hold" tone="danger" disabled={hold.state !== "AVAILABLE" || hold.enabled === true} onRun={engageGlobalHold} onDone={refresh} /><AsyncActionButton label="Release Global Hold" tone="warn" disabled={hold.state !== "AVAILABLE" || hold.enabled !== true} onRun={releaseGlobalHold} onDone={refresh} /></div></section>
      <section className="v3-region v3-sp4"><div className="v3-region-head"><span className="v3-region-title">RiskGate Snapshot</span><AuthorityBadge state={state(risk.state)} /></div><div className="v3-stat-big">{risk.state === "AVAILABLE" ? "AVAILABLE" : "UNAVAILABLE"}</div><div className="v3-region-note">{risk.reason || "Backend-authoritative risk snapshot connected."}</div></section>
      <section className="v3-region v3-sp6"><div className="v3-region-head"><span className="v3-region-title">Live Execution</span></div><div className="v3-stat-big">READ_ONLY/DISARMED</div><div className="v3-region-note">Broker mutation: {data?.broker_mutation || "ABSENT"}</div></section>
      <section className="v3-region v3-sp6"><div className="v3-region-head"><span className="v3-region-title">Kill Switch Authority</span></div><div className="v3-stat-big">{kill.state || "NOT_CONNECTED"}</div><div className="v3-region-note">{kill.reason || "UNAVAILABLE"}</div></section>
    </div>
  </>;
};
