import React, { useState } from "react";
import { Dot, Panel } from "../../shared/utilities/V3Chrome";
import type { AuthorityState } from "../authority";

const TONE: Record<AuthorityState, "ok" | "warn" | "neg" | "dim"> = {
  AVAILABLE: "ok",
  STALE: "warn",
  UNKNOWN: "dim",
  UNAVAILABLE: "neg",
};

export const AuthorityBadge: React.FC<{ state: AuthorityState; label?: string }> = ({ state, label }) => (
  <span className={`v3-status-badge ${state.toLowerCase()}`} data-authority-state={state}>
    <Dot tone={TONE[state]} /> {label || state}
  </span>
);

export const AuthorityPanel: React.FC<{
  title: string;
  state: AuthorityState;
  children?: React.ReactNode;
  reason?: string | null;
  onRefresh?: () => void;
}> = ({ title, state, children, reason, onRefresh }) => (
  <Panel>
    <div className="v3-region-head" style={{ marginBottom: 12 }}>
      <span className="v3-region-title">{title}</span>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <AuthorityBadge state={state} />
        {onRefresh && <button type="button" className="v3-btn ghost mini" onClick={onRefresh}>Refresh</button>}
      </div>
    </div>
    {state === "AVAILABLE" ? children : (
      <div className={`owner-authority-message ${state.toLowerCase()}`} role="status">
        <strong>{state}</strong>
        <div>{reason || (state === "STALE" ? "Authority data is stale and is not treated as current." : state === "UNKNOWN" ? "Authority could not establish a current state." : "Backend authority is unavailable. No zero/healthy state is inferred.")}</div>
      </div>
    )}
  </Panel>
);

export const SafeMetric: React.FC<{ state: AuthorityState; label: string; value: number | string | null | undefined }> = ({ state, label, value }) => (
  <div>
    <div className="v3-stat-big">{state === "AVAILABLE" && value !== null && value !== undefined ? String(value) : "—"}</div>
    <div className="v3-region-note">{label}</div>
  </div>
);

export const AsyncActionButton: React.FC<{
  label: string;
  onRun: () => Promise<unknown>;
  tone?: "normal" | "danger" | "warn";
  disabled?: boolean;
  onDone?: () => void;
}> = ({ label, onRun, tone = "normal", disabled, onDone }) => {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const run = async () => {
    if (busy || disabled) return;
    setBusy(true);
    setMessage(null);
    try {
      await onRun();
      setMessage("Verified by backend");
      onDone?.();
    } catch (err: any) {
      setMessage(err?.message || "Action rejected");
    } finally {
      setBusy(false);
    }
  };
  return (
    <span style={{ display: "inline-flex", flexDirection: "column", gap: 3, alignItems: "flex-start" }}>
      <button
        type="button"
        className={`v3-btn ${tone === "danger" ? "danger" : tone === "warn" ? "warn" : "ghost"} mini`}
        onClick={run}
        disabled={busy || disabled}
      >
        {busy ? "Verifying…" : label}
      </button>
      {message && <span className="v3-region-note" style={{ maxWidth: 220 }}>{message}</span>}
    </span>
  );
};

export const SimpleTable: React.FC<{
  columns: Array<{ key: string; label: string; render?: (row: any) => React.ReactNode }>;
  rows: any[];
  emptyText?: string;
}> = ({ columns, rows, emptyText = "No authoritative records." }) => (
  <div style={{ overflowX: "auto" }}>
    <table className="v3-table">
      <thead><tr>{columns.map((column) => <th key={column.key}>{column.label}</th>)}</tr></thead>
      <tbody>
        {rows.length === 0 ? (
          <tr><td colSpan={columns.length}><span className="v3-region-note">{emptyText}</span></td></tr>
        ) : rows.map((row, index) => (
          <tr key={String(row.id || row.job_id || row.eventId || row.event_id || row.strategy_id || row.sxId || index)}>
            {columns.map((column) => <td key={column.key}>{column.render ? column.render(row) : String(row[column.key] ?? "—")}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  </div>
);
