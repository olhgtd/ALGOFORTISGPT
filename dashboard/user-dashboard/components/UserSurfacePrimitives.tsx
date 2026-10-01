import React from "react";
import type { UserSurfaceAuthorityState } from "../data/userSurfaceData";

export const AuthorityBadge: React.FC<{ state: UserSurfaceAuthorityState | "LOADING"; label?: string }> = ({ state, label }) => (
  <span className={`af-surface-authority af-surface-authority-${state.toLowerCase()}`}>
    {label ?? state}
  </span>
);

export const UserSurfaceHeader: React.FC<{
  eyebrow: string;
  title: string;
  description: string;
  aside?: React.ReactNode;
}> = ({ eyebrow, title, description, aside }) => (
  <header className="af-surface-header">
    <div>
      <span className="af-eyebrow">{eyebrow}</span>
      <h1>{title}</h1>
      <p>{description}</p>
    </div>
    {aside && <div className="af-surface-header-aside">{aside}</div>}
  </header>
);

export const AuthorityMessage: React.FC<{
  state: UserSurfaceAuthorityState | "LOADING";
  title: string;
  unavailable: string;
  loading?: string;
  stale?: string;
  unknown?: string;
  empty?: string;
  isEmpty?: boolean;
}> = ({
  state,
  title,
  unavailable,
  loading = "Loading authoritative data…",
  stale = "Authoritative evidence is stale. Stale records are withheld until fresh evidence is available.",
  unknown = "Authority trust is unknown. UNKNOWN is not treated as available.",
  empty = "No authoritative records.",
  isEmpty = false,
}) => {
  if (state === "AVAILABLE" && !isEmpty) return null;
  const body = state === "LOADING"
    ? loading
    : state === "AVAILABLE"
      ? empty
      : state === "STALE"
        ? stale
        : state === "UNKNOWN"
          ? unknown
          : unavailable;
  return (
    <div className="af-surface-message" role="status">
      <AuthorityBadge state={state} />
      <strong>{title}</strong>
      <span>{body}</span>
    </div>
  );
};

export const SurfacePanel: React.FC<{
  eyebrow?: string;
  title: string;
  authority?: UserSurfaceAuthorityState | "LOADING";
  children: React.ReactNode;
  className?: string;
}> = ({ eyebrow, title, authority, children, className = "" }) => (
  <section className={`af-surface-panel ${className}`.trim()}>
    <div className="af-surface-panel-head">
      <div>
        {eyebrow && <span className="af-eyebrow">{eyebrow}</span>}
        <h2>{title}</h2>
      </div>
      {authority && <AuthorityBadge state={authority} />}
    </div>
    {children}
  </section>
);

export const MetricCell: React.FC<{ label: string; value: React.ReactNode; tone?: "positive" | "negative" | "neutral" | "warning" }> = ({ label, value, tone = "neutral" }) => (
  <div className="af-surface-metric">
    <span>{label}</span>
    <strong className={`af-surface-value-${tone}`}>{value}</strong>
  </div>
);

export const displayScalar = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "YES" : "NO";
  return String(value);
};

export const displayNumber = (value: unknown, digits = 2): string => {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
};

export const displayMoney = (value: unknown): string => {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return `₹${value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

export const evidenceValue = (row: Record<string, unknown>, keys: readonly string[]): unknown => {
  for (const key of keys) {
    const value = row[key];
    if (value !== null && value !== undefined && value !== "") return value;
  }
  return null;
};
