import React, { useMemo, useState } from "react";
import { Panel } from "../../shared/utilities/V3Chrome";
import type { AuthorityState } from "../authority";
import { queryOwnerUserInspection, type InspectionTabName, type InspectionSurface, type OwnerUserInspectionSnapshot } from "./inspectionApi";
import { AuthorityBadge, AuthorityPanel, AsyncActionButton, SimpleTable } from "./components";
import { useOwnerAuthority } from "./hooks";

const TABS: InspectionTabName[] = [
  "Profile",
  "Strategies",
  "Backtests",
  "Paper",
  "Portfolio",
  "Orders",
  "Connections",
  "Reports",
  "Sessions",
  "Security State",
];

const asState = (value: unknown): AuthorityState => (
  value === "AVAILABLE" || value === "STALE" || value === "UNKNOWN" || value === "UNAVAILABLE"
    ? value
    : "UNKNOWN"
);

const isScalar = (value: unknown) => value === null || ["string", "number", "boolean"].includes(typeof value);

const safeColumns = (rows: Array<Record<string, unknown>>) => {
  const keys = Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
  return keys
    .filter((key) => rows.some((row) => isScalar(row[key])))
    .filter((key) => !/(password|secret|token|credential_data|hash)$/i.test(key))
    .slice(0, 8)
    .map((key) => ({ key, label: key.replaceAll("_", " ") }));
};

const InspectionData: React.FC<{ surface: InspectionSurface }> = ({ surface }) => {
  const state = asState(surface.authority_state);
  if (state !== "AVAILABLE") {
    return <div className={`owner-authority-message ${state.toLowerCase()}`}>
      {surface.error || `${state}: authoritative data is not current or unavailable.`}
    </div>;
  }

  const value = surface.data as any;
  if (Array.isArray(value)) {
    if (value.length === 0) return <div className="v3-region-note">Authoritative source returned 0 records.</div>;
    const rows = value.filter((row) => row && typeof row === "object") as Array<Record<string, unknown>>;
    return <SimpleTable rows={rows} columns={safeColumns(rows)} />;
  }
  if (!value || typeof value !== "object") return <div className="v3-region-note">No structured authoritative payload.</div>;

  const entries = Object.entries(value as Record<string, unknown>);
  const scalarEntries = entries.filter(([, item]) => isScalar(item) && !/(password|secret|token|credential_data|hash)$/i.test(String(item)));
  const arrayEntries = entries.filter(([, item]) => Array.isArray(item));
  return <div style={{ display: "grid", gap: 14 }}>
    {scalarEntries.length > 0 && <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(210px,1fr))", gap: 10 }}>
      {scalarEntries.map(([key, item]) => <div key={key} className="v3-kv-row">
        <span className="v3-kv-key">{key.replaceAll("_", " ")}</span>
        <strong className="v3-kv-value">{item === null ? "—" : String(item)}</strong>
      </div>)}
    </div>}
    {arrayEntries.map(([key, item]) => {
      const rows = (item as unknown[]).filter((row) => row && typeof row === "object") as Array<Record<string, unknown>>;
      return <section key={key} className="v3-region" style={{ padding: 12 }}>
        <div className="v3-region-head"><span className="v3-region-title">{key.replaceAll("_", " ")}</span><span className="v3-region-note">{rows.length} records</span></div>
        {rows.length > 0 ? <SimpleTable rows={rows} columns={safeColumns(rows)} /> : <div className="v3-region-note">0 authoritative records.</div>}
      </section>;
    })}
  </div>;
};

export const OwnerUsersInspectionScreen: React.FC = () => {
  const { snapshot, loading, error, refresh } = useOwnerAuthority();
  const [selected, setSelected] = useState<string | null>(null);
  const [inspection, setInspection] = useState<OwnerUserInspectionSnapshot | null>(null);
  const [inspectionError, setInspectionError] = useState<string | null>(null);
  const [inspectionLoading, setInspectionLoading] = useState(false);
  const [tab, setTab] = useState<InspectionTabName>("Profile");

  const access = snapshot?.surfaces.access;
  const state = asState(access?.authority_state);
  const rows = useMemo(() => state === "AVAILABLE" && Array.isArray(access?.records) ? access.records as any[] : [], [access, state]);

  const open = async (identifier: string) => {
    setSelected(identifier);
    setInspection(null);
    setInspectionError(null);
    setInspectionLoading(true);
    setTab("Profile");
    try {
      setInspection(await queryOwnerUserInspection(identifier));
    } catch (err: any) {
      setInspectionError(err?.message || "USER_INSPECTION_AUTHORITY_UNAVAILABLE");
    } finally {
      setInspectionLoading(false);
    }
  };

  if (loading) return <Panel>Loading users…</Panel>;

  if (selected) {
    const surface = inspection?.tabs?.[tab];
    return <>
      <div className="v3-screen-head">
        <div><h2 className="v3-screen-title">Owner User Inspection</h2><p className="v3-screen-sub">Read-only governance oversight. No trading, RiskGate, broker mutation, or hidden sample authority.</p></div>
        <button className="v3-btn ghost" onClick={() => { setSelected(null); setInspection(null); setInspectionError(null); }}>← Back to Users</button>
      </div>
      <div className="dev-preview-banner" style={{ marginBottom: 14 }}>
        <span className="banner-tag">READ ONLY</span>
        <span>User {inspection?.sx_id || selected} · LIVE {inspection?.live_state || "READ_ONLY/DISARMED"}</span>
      </div>
      <div style={{ display: "flex", gap: 7, flexWrap: "wrap", marginBottom: 14 }}>
        {TABS.map((item) => <button key={item} className={`v3-btn ${tab === item ? "primary" : "ghost"} mini`} onClick={() => setTab(item)}>{item}</button>)}
      </div>
      {inspectionLoading && <Panel>Loading authoritative user inspection…</Panel>}
      {inspectionError && <AuthorityPanel title={tab} state="UNAVAILABLE" reason={inspectionError} />}
      {!inspectionLoading && !inspectionError && surface && <section className="v3-region v3-sp12">
        <div className="v3-region-head"><span className="v3-region-title">{tab}</span><AuthorityBadge state={asState(surface.authority_state)} /></div>
        <div style={{ marginTop: 12 }}><InspectionData surface={surface} /></div>
      </section>}
    </>;
  }

  return <>
    <div className="v3-screen-head">
      <div><h2 className="v3-screen-title">Users Oversight</h2><p className="v3-screen-sub">Open any user into the ten-tab authoritative inspection workspace.</p></div>
    </div>
    <AuthorityPanel title="User Accounts" state={access ? state : "UNAVAILABLE"} reason={error || String(access?.error || "")} onRefresh={refresh}>
      <SimpleTable rows={rows} columns={[
        { key: "sxId", label: "SX ID" },
        { key: "displayName", label: "Name" },
        { key: "emailMasked", label: "Email" },
        { key: "accountStatus", label: "Account" },
        { key: "serviceStatus", label: "Service" },
        { key: "inspect", label: "Inspection", render: (row) => <AsyncActionButton label="Open User" onRun={() => open(String(row.sxId || row.id))} /> },
      ]} />
    </AuthorityPanel>
  </>;
};
