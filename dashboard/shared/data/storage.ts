/**
 * SentinelX Dashboard V3 — LocalStorage Keys & Persistence Helpers
 */

export const STORAGE_KEYS = {
  ACCESS_REGISTRY: "sentinelx_access_registry_v1",
  OWNER_USERS: "sentinelx_owner_users_v1",
  OWNER_STRATEGIES: "sentinelx_owner_strategies_v1",
  OWNER_CONNECTIONS: "sentinelx_owner_connections_v1",
  OWNER_DATASETS: "sentinelx_owner_datasets_v1",
  OWNER_PLUGINS: "sentinelx_owner_plugins_v1",
  OWNER_BACKTESTS: "sentinelx_owner_backtests_v1",
  OWNER_PAPER_SESSIONS: "sentinelx_owner_paper_sessions_v1",
  OWNER_PORTFOLIOS: "sentinelx_owner_portfolios_v1",
  OWNER_POSITIONS: "sentinelx_owner_positions_v1",
  OWNER_ORDERS: "sentinelx_owner_orders_v1",
  OWNER_REPORTS: "sentinelx_owner_reports_v1",
  OWNER_AUDIT_EVENTS: "sentinelx_owner_audit_v1",
  OWNER_SESSIONS: "sentinelx_owner_sessions_v1",
  OWNER_DEVICES: "sentinelx_owner_devices_v1",
  OWNER_SETTINGS: "sentinelx_owner_settings_v1",
  THEME: "sentinelx_theme",
  STRIKE_POLICY: "sentinelx_strike_policy_v1",
} as const;

// Owner-domain fixtures may retain their frozen key labels for compatibility
// evidence, but must never persist in a browser-controlled authority store.
// This process-memory adapter intentionally resets on reload and is not an
// authentication, authorization, session, device, audit, or trading authority.
const prototypeFixtureMemory = new Map<string, string>();

export const prototypeFixtureStorage = {
  getItem(key: string): string | null {
    return prototypeFixtureMemory.get(key) ?? null;
  },
  setItem(key: string, value: string): void {
    prototypeFixtureMemory.set(key, value);
  },
};

export function safeGetJson<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    return JSON.parse(raw) as T;
  } catch (err) {
    console.warn(`[SentinelX Storage] Failed to parse key ${key}:`, err);
    return fallback;
  }
}

export function safeSetJson<T>(key: string, value: T): boolean {
  if (typeof window === "undefined") return false;
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch (err) {
    console.error(`[SentinelX Storage] Failed to save key ${key}:`, err);
    return false;
  }
}
