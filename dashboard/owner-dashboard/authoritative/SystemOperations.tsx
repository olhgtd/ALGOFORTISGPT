import React, { useCallback } from "react";
import { Panel } from "../../shared/utilities/V3Chrome";
import { useAsyncResource } from "./hooks";
import { querySystemOperations } from "./systemOps";

const unavailable = (value: any) => value === undefined || value === null || value === "" ? "UNAVAILABLE" : String(value);

export const SystemOperations: React.FC = () => {
  const load = useCallback(() => querySystemOperations(), []);
  const { data, loading, error, refresh } = useAsyncResource(load);
  if (loading && !data) return <Panel>Loading system operations authority…</Panel>;
  const product = data?.productOps || {};
  const health = data?.authority?.surfaces?.health || {};
  const incidents = Array.isArray(data?.incidents?.incidents) ? data.incidents.incidents : [];
  const audit = Array.isArray(data?.audit?.events) ? data.audit.events : Array.isArray(data?.audit) ? data.audit : [];
  return <>
    <div className="v3-screen-head"><div><h2 className="v3-screen-title">System Operations</h2><p className="v3-screen-sub">Bounded operational health and recovery evidence only. No terminal, arbitrary file path, or process-control authority is exposed.</p></div><button type="button" className="v3-btn ghost mini" onClick={refresh}>Refresh</button></div>
    {error && <div className="owner-authority-message unavailable"><strong>UNAVAILABLE</strong><div>{error}</div></div>}
    <div className="v3-grid">
      <section className="v3-region v3-sp4"><div className="v3-region-title">Persistence</div><div className="v3-stat-big">{unavailable(health.authority_state || health.status)}</div><div className="v3-region-note">Source: backend health authority</div></section>
      <section className="v3-region v3-sp4"><div className="v3-region-title">Audit</div><div className="v3-stat-big">{audit.length}</div><div className="v3-region-note">Authoritative audit rows loaded</div></section>
      <section className="v3-region v3-sp4"><div className="v3-region-title">Incidents</div><div className="v3-stat-big">{data ? incidents.length : "—"}</div><div className="v3-region-note">Security/operational incident rows</div></section>
    </div>
    <div className="v3-grid">
      <section className="v3-region v3-sp3"><div className="v3-region-title">Backup</div><div className="v3-stat-big">{unavailable(product.backup_status)}</div><div className="v3-region-note">No bounded command authority is attached; evidence only.</div></section>
      <section className="v3-region v3-sp3"><div className="v3-region-title">Restore</div><div className="v3-stat-big">{unavailable(product.restore_status)}</div><div className="v3-region-note">UNAVAILABLE as a command unless a canonical bounded authority is attached.</div></section>
      <section className="v3-region v3-sp3"><div className="v3-region-title">Rollback</div><div className="v3-stat-big">{unavailable(product.rollback_status)}</div><div className="v3-region-note">UNAVAILABLE as a command unless a canonical bounded authority is attached.</div></section>
      <section className="v3-region v3-sp3"><div className="v3-region-title">Runbooks</div><div className="v3-stat-big">{unavailable(product.runbook_status)}</div><div className="v3-region-note">Read-model status only.</div></section>
    </div>
    <Panel><div className="v3-region-head"><span className="v3-region-title">Product / Privacy Operations</span></div><div className="v3-region-note">Live: {unavailable(product.live_state)} · AI: {unavailable(product.ai_authority)} · Alert health: {unavailable(product.alert_health)}</div></Panel>
  </>;
};
