import React, { useEffect, useMemo, useState } from "react";
import { Icon, type IconName } from "../icons/V3Icons";
import type { Truth } from "../data";

/* SentinelX Dashboard V3 — shared visual chrome.
   Every interactive control maps to one of the three truth states:
   REAL + WORKING | DEV PREVIEW / SAMPLE | DISABLED / UNAVAILABLE. */

/* ════════════════════════════════════════════════════════════
   GLOBAL REAL-TIME WALL CLOCK ENGINE
   - True wall-clock based on native Date recalculation per second
   - Instant sleep/background recovery via visibilitychange & focus listeners
   - Default timezone: IST (Asia/Kolkata) with modular multi-timezone architecture
   ════════════════════════════════════════════════════════════ */
export interface ClockConfig {
  timezone?: string;
  tzLabel?: string;
  is24h?: boolean;
}

export interface ClockState {
  time: string;
  tz: string;
  date: string;
  full: string;
  compact: string;
  raw: Date;
}

export const useRealTimeClock = (
  config: ClockConfig = { timezone: "Asia/Kolkata", tzLabel: "IST", is24h: true }
): ClockState => {
  const [now, setNow] = useState<Date>(() => new Date());

  useEffect(() => {
    const updateTime = () => setNow(new Date());

    updateTime();
    const timer = setInterval(updateTime, 1000);

    // Sleep/background recovery
    const handleVisibility = () => {
      if (document.visibilityState === "visible") {
        updateTime();
      }
    };
    const handleFocus = () => updateTime();

    document.addEventListener("visibilitychange", handleVisibility);
    window.addEventListener("focus", handleFocus);

    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", handleVisibility);
      window.removeEventListener("focus", handleFocus);
    };
  }, []);

  return useMemo(() => {
    try {
      const tz = config.timezone || "Asia/Kolkata";
      const tzLabel = config.tzLabel || "IST";

      const timeFormatter = new Intl.DateTimeFormat("en-GB", {
        timeZone: tz,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: !config.is24h,
      });

      const dateFormatter = new Intl.DateTimeFormat("en-GB", {
        timeZone: tz,
        day: "2-digit",
        month: "short",
        year: "numeric",
      });

      const timeStr = timeFormatter.format(now);
      const dateParts = dateFormatter.formatToParts(now);
      const day = dateParts.find((p) => p.type === "day")?.value || "";
      const month = (dateParts.find((p) => p.type === "month")?.value || "").toUpperCase();
      const year = dateParts.find((p) => p.type === "year")?.value || "";
      const dateStr = `${day} ${month} ${year}`;

      return {
        time: timeStr,
        tz: tzLabel,
        date: dateStr,
        full: `${timeStr} ${tzLabel} · ${dateStr}`,
        compact: `${timeStr} ${tzLabel}`,
        raw: now,
      };
    } catch {
      const pad = (n: number) => String(n).padStart(2, "0");
      const timeStr = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
      return {
        time: timeStr,
        tz: "IST",
        date: "30 AUG 2026",
        full: `${timeStr} IST · 30 AUG 2026`,
        compact: `${timeStr} IST`,
        raw: now,
      };
    }
  }, [now, config.timezone, config.tzLabel, config.is24h]);
};

export const GlobalRealTimeClock: React.FC<{
  config?: ClockConfig;
  className?: string;
  isMobile?: boolean;
}> = ({ config, className, isMobile }) => {
  const clock = useRealTimeClock(config);

  return (
    <div
      className={`v3-clock ${className ?? ""}`}
      id="v3-global-clock"
      aria-label={`Current Wall Clock: ${clock.full}`}
      title={`Live Real-Time Wall Clock (${clock.tz}) · Recalculated every second without drift`}
    >
      <span className="v3-clock-time">{clock.time}</span>
      <span className="v3-clock-tz">{clock.tz}</span>
      {!isMobile && (
        <>
          <span className="v3-clock-sep">·</span>
          <span className="v3-clock-date">{clock.date}</span>
        </>
      )}
    </div>
  );
};

export const fmtINR = (v: number, frac = 0) =>
  new Intl.NumberFormat("en-IN", { minimumFractionDigits: frac, maximumFractionDigits: frac }).format(v);

export const fmtSignedINR = (v: number, frac = 2) => {
  const abs = Math.abs(v);
  const formatted = new Intl.NumberFormat("en-IN", { minimumFractionDigits: frac, maximumFractionDigits: frac }).format(abs);
  if (v > 0) return `+₹${formatted}`;
  if (v < 0) return `-₹${formatted}`;
  return `₹${formatted}`;
};

export const fmtSignedPct = (v: number, frac = 2) => {
  const abs = Math.abs(v);
  const formatted = abs.toFixed(frac);
  if (v > 0) return `+${formatted}%`;
  if (v < 0) return `-${formatted}%`;
  return `${formatted}%`;
};

export const PnlBadge: React.FC<{ value: number; percent?: number; isCurrency?: boolean }> = ({ value, percent, isCurrency = true }) => {
  const isPos = value >= 0;
  const valStr = isCurrency ? fmtSignedINR(value) : (value >= 0 ? `+${value}` : `${value}`);
  const pctStr = percent !== undefined ? ` (${fmtSignedPct(percent)})` : "";
  return (
    <span className={isPos ? "v3-profit-badge" : "v3-loss-badge"}>
      {valStr}{pctStr}
    </span>
  );
};

export const TruthChip: React.FC<{ kind: Truth; title?: string }> = ({ kind, title }) => (
  <span
    className={`v3-chip ${kind === "REAL" ? "real" : kind === "SAMPLE" ? "sample" : "disabled"}`}
    title={title ?? (kind === "REAL"
      ? "Connected to authoritative state and verified working in this prototype."
      : kind === "SAMPLE"
        ? "DEV PREVIEW / SAMPLE — simulated data, non-authoritative."
        : "DISABLED / UNAVAILABLE — intentionally not wired in this phase.")}
  >
    {kind === "REAL" ? "REAL + WORKING" : kind === "SAMPLE" ? "DEV PREVIEW / SAMPLE" : "DISABLED / UNAVAILABLE"}
  </span>
);

export type DotTone = "ok" | "neg" | "warn" | "dim" | "live";
export const Dot: React.FC<{ tone: DotTone }> = ({ tone }) => <span className={`v3-dot ${tone}`} aria-hidden="true" />;

export const Panel: React.FC<{
  label: string; meta?: React.ReactNode; truth?: Truth; action?: React.ReactNode;
  className?: string; children: React.ReactNode; id?: string;
}> = ({ label, meta, truth, action, className, children, id }) => (
  <section className={`v3-panel ${className ?? ""}`} id={id}>
    <div className="v3-panel-head">
      <span className="v3-panel-label">{label}</span>
      <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {meta != null && <span className="v3-panel-meta">{meta}</span>}
        {truth && <TruthChip kind={truth} />}
        {action}
      </span>
    </div>
    {children}
  </section>
);

export const Sparkline: React.FC<{ points: number[]; height?: number; width?: number }> = ({ points, height = 56, width = 240 }) => {
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const step = width / (points.length - 1);
  const isUp = points[points.length - 1] >= points[0];
  const strokeColor = isUp ? "#10b981" : "#ef4444";
  const fillColor = isUp ? "rgba(16, 185, 129, 0.08)" : "rgba(239, 68, 68, 0.08)";
  const d = points.map((p, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${(height - 4 - ((p - min) / span) * (height - 10)).toFixed(1)}`).join(" ");
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label="Portfolio equity curve (sample)">
      <path d={d} fill="none" stroke={strokeColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity="0.95" />
      <path d={`${d} L${width},${height} L0,${height} Z`} fill={fillColor} stroke="none" />
    </svg>
  );
};

export const KV: React.FC<{ k: string; v: React.ReactNode; vClass?: string }> = ({ k, v, vClass }) => (
  <div className="v3-kv"><dt>{k}</dt><dd className={vClass}>{v}</dd></div>
);

/* ── Contextual detail drawer ───────────────────────────────────────── */
export const Drawer: React.FC<{
  open: boolean; title: string; sub?: string; onClose: () => void; children: React.ReactNode;
}> = ({ open, title, sub, onClose, children }) => {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <>
      <button className="v3-backdrop" aria-label="Close details" onClick={onClose} />
      <aside className="v3-drawer" role="dialog" aria-modal="true" aria-label={title}>
        <div className="v3-drawer-head">
          <div style={{ minWidth: 0 }}>
            <h3 className="v3-drawer-title">{title}</h3>
            {sub && <div className="v3-row-sub">{sub}</div>}
          </div>
          <button className="v3-btn ghost mini" onClick={onClose} aria-label="Close details panel">
            <Icon name="close" size={14} /> Close
          </button>
        </div>
        <div className="v3-drawer-body">{children}</div>
      </aside>
    </>
  );
};

/* ── Command palette (REAL + WORKING within the prototype) ──────────── */
export interface PaletteCmd { id: string; label: string; hint: string; icon: IconName; run: () => void; }

export const CommandPalette: React.FC<{
  open: boolean; commands: PaletteCmd[]; onClose: () => void;
}> = ({ open, commands, onClose }) => {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    return t ? commands.filter((c) => c.label.toLowerCase().includes(t) || c.hint.toLowerCase().includes(t)) : commands;
  }, [q, commands]);
  useEffect(() => { if (open) { setQ(""); setSel(0); } }, [open]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, filtered.length - 1)); }
      if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
      if (e.key === "Enter" && filtered[sel]) { filtered[sel].run(); onClose(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
  if (!open) return null;
  return (
    <div className="v3-palette-wrap" role="presentation" onClick={onClose}>
      <div className="v3-palette" role="dialog" aria-modal="true" aria-label="Command palette" onClick={(e) => e.stopPropagation()}>
        <input
          autoFocus
          value={q}
          placeholder="Search screens and actions…"
          onChange={(e) => { setQ(e.target.value); setSel(0); }}
          aria-label="Search screens and actions"
        />
        <div className="v3-palette-list">
          {filtered.length === 0 && <div style={{ padding: "14px 12px", color: "var(--v3-ink-dim)", fontSize: 12.5 }}>No matches.</div>}
          {filtered.map((c, i) => (
            <button
              key={c.id}
              className={`v3-palette-item ${i === sel ? "sel" : ""}`}
              onClick={() => { c.run(); onClose(); }}
              onMouseEnter={() => setSel(i)}
            >
              <Icon name={c.icon} size={15} />
              {c.label}
              <span className="hint">{c.hint}</span>
            </button>
          ))}
        </div>
        <div style={{ padding: "8px 14px", borderTop: "1px solid var(--v3-line)", display: "flex", gap: 8, alignItems: "center" }}>
          <TruthChip kind="REAL" title="Palette navigation works within the visual prototype." />
          <span className="v3-panel-meta">↑↓ navigate · Enter open · Esc close</span>
        </div>
      </div>
    </div>
  );
};
