/**
 * AlgoFortis Phase BI-1 — Read-Only Integration Client
 * 
 * Provides typed queries for:
 * 1. D16 Audit Event Read Projection
 * 2. Persistence / System Health Read Projection
 * 
 * Implements strict fallback to local prototype fixtures when the backend
 * is unavailable, preserving the DEV PREVIEW / SAMPLE label.
 */
import {
  getStoredOwnerAuditEvents,
  getStoredOwnerSessions,
  getStoredOwnerDevices,
  getStoredOwnerStrategies,
  getStoredOwnerConnections,
  getStoredOwnerDatasets,
  type OwnerAuditRow,
  type OwnerSessionRow,
  type OwnerDeviceRow,
  type StrategyRow,
  type OwnerConnectionRow,
  type OwnerDatasetRow,
  type ConnectionCapability,
  type OwnerAllowanceStatus,
  type ConnectionOwnerAllowance,
  type CapabilityOwnerAllowance,
  type DatasetOwnerApproval,
} from "../../owner-dashboard/data";
import { getSessionToken } from "./sessionStore";

export type IntegrationSource = "BACKEND" | "SAMPLE_FALLBACK" | "UNAVAILABLE";
export type IntegrationTrust = "FRESH" | "STALE" | "UNKNOWN";

export type OrdersPortfolioMode = "PAPER" | "BACKTEST" | "LIVE" | "SHADOW";
export interface LiveExecutionPolicy { arming_state: "READ_ONLY"; mutation_allowed: false; global_hold: boolean; safe_mode: boolean; }
export interface LiveIntentReceipt {
  intent_id: string;
  status: "SHADOW_READY" | "SHADOW_BLOCKED" | "SHADOW_REJECTED" | "BLOCKED";
  audit_id: string;
  execution_mode?: "SHADOW" | "LIVE";
  reasons: { code: string; detail: string }[];
  would_be_payload?: Record<string, unknown> | null;
  idempotency_key?: string;
  checked_at?: string;
  broker_mutation_sent?: boolean;
}
export interface LiveReadiness {
  user_id: string; provider: string; connection_state: string; error: string | null;
  account: Record<string, unknown> | null; funds: Record<string, unknown> | null;
  positions: Record<string, unknown>[] | null; orders: Record<string, unknown>[] | null; holdings: Record<string, unknown>[] | null;
  market_data: Record<string, unknown>[]; market_data_state: string; risk_state: string;
  last_success: string | null; last_failure: string | null; audit_id: string | null;
  reconciliation: { state: string; differences: string[] };
  capabilities: Record<string, unknown>[]; execution_policy: LiveExecutionPolicy;
  strategies: { id: string; name: string }[]; instruments: { token: string; symbol: string; lot_size: string }[];
  intents: LiveIntentReceipt[];
  shadow_orders?: LiveIntentReceipt[];
}
export interface LiveOversight { execution_policy: LiveExecutionPolicy; users: LiveReadiness[]; }
export async function liveReadinessRequest<T>(endpoint: string, body?: object): Promise<T> {
  if (!isBackendEnabled()) throw new Error("Live readiness authority unavailable");
  const res = await fetchWithTimeout(`${getApiBaseUrl()}${endpoint}`, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }, 30000);
  if (!res.ok) throw new Error(`Live readiness authority unavailable (HTTP ${res.status})`);
  return await res.json();
}
export interface RuntimeEvidence {
  [key: string]: string | number | null;
  session_id: string;
  user_id: string;
  execution_mode: string;
  strategy_name: string;
  data_source_mode: string;
}
export interface OrdersPortfolioSnapshot {
  execution_mode: OrdersPortfolioMode;
  availability: "AVAILABLE" | "UNAVAILABLE";
  source: string | null;
  accounts: RuntimeEvidence[];
  positions: RuntimeEvidence[];
  orders: RuntimeEvidence[];
  events: RuntimeEvidence[];
  aggregate_exposure: null;
  limitations: string[];
}

/** Runtime-only projection. Missing authority rejects; sample fixtures are never used. */
export async function queryOrdersPortfolio(owner: boolean, mode: OrdersPortfolioMode): Promise<OrdersPortfolioSnapshot> {
  if (!isBackendEnabled()) throw new Error("Orders and portfolio authority unavailable");
  const res = await fetchWithTimeout(`${getApiBaseUrl()}/api/v1/${owner ? "owner" : "user"}/orders-portfolio?mode=${mode}`);
  if (!res.ok) throw new Error(`Orders and portfolio authority unavailable (HTTP ${res.status})`);
  return await res.json();
}

export async function queryOrderDetail(sessionId: string, orderId: string): Promise<RuntimeEvidence> {
  if (!isBackendEnabled()) throw new Error("Order authority unavailable");
  const res = await fetchWithTimeout(`${getApiBaseUrl()}/api/v1/paper/sessions/${encodeURIComponent(sessionId)}/orders/${encodeURIComponent(orderId)}`);
  if (!res.ok) throw new Error(`Order authority unavailable (HTTP ${res.status})`);
  return await res.json();
}

export type MarketChartMode = "LIVE" | "FROZEN_HISTORICAL" | "BACKTEST";
export type MarketChartState =
  | "LOADING"
  | "AVAILABLE"
  | "NO_DATA"
  | "DATA_PROVIDER_NOT_CONFIGURED"
  | "BACKEND_UNAVAILABLE"
  | "ERROR";
export interface MarketCandle {
  time: string; open: number; high: number; low: number; close: number; volume?: number;
}
export interface MarketChartResult {
  state: MarketChartState;
  instrument: string;
  timeframe: string;
  mode: MarketChartMode;
  candles: MarketCandle[];
  detail?: string;
}

/** F-8: chart reads resolve ONLY through the backend canonical data service.
 * Fail-closed: no SAMPLE fallback, no synthetic candles — unavailable data is
 * reported as NO_DATA / DATA_PROVIDER_NOT_CONFIGURED / BACKEND_UNAVAILABLE. */
export async function queryMarketChart(params: {
  instrument: string; timeframe: string; mode: MarketChartMode;
  start_date?: string; end_date?: string; limit?: number;
}): Promise<MarketChartResult> {
  const query = new URLSearchParams({
    instrument: params.instrument, timeframe: params.timeframe, mode: params.mode,
  });
  if (params.start_date) query.set("start_date", params.start_date);
  if (params.end_date) query.set("end_date", params.end_date);
  if (params.limit) query.set("limit", String(params.limit));
  let res: Response;
  try {
    res = await fetchWithTimeout(`${getApiBaseUrl()}/api/v1/market/chart?${query.toString()}`);
  } catch {
    return { state: "BACKEND_UNAVAILABLE", instrument: params.instrument, timeframe: params.timeframe, mode: params.mode, candles: [] };
  }
  if (!res.ok) {
    return {
      state: "BACKEND_UNAVAILABLE", instrument: params.instrument, timeframe: params.timeframe,
      mode: params.mode, candles: [], detail: `HTTP ${res.status}`,
    };
  }
  let payload: any;
  try {
    payload = await res.json();
  } catch {
    return { state: "ERROR", instrument: params.instrument, timeframe: params.timeframe, mode: params.mode, candles: [], detail: "invalid chart payload" };
  }
  const rawState: string | undefined = payload?.candles?.state;
  const values: MarketCandle[] = Array.isArray(payload?.candles?.value) ? payload.candles.value : [];
  if (rawState === "AVAILABLE" && values.length > 0) {
    return { state: "AVAILABLE", instrument: payload.instrument, timeframe: payload.timeframe, mode: params.mode, candles: values };
  }
  if (rawState === "DATA_PROVIDER_NOT_CONFIGURED") {
    return { state: "DATA_PROVIDER_NOT_CONFIGURED", instrument: params.instrument, timeframe: params.timeframe, mode: params.mode, candles: [] };
  }
  if (rawState === "NO_DATA" || rawState === "DATA_INVALID" || values.length === 0) {
    return { state: "NO_DATA", instrument: params.instrument, timeframe: params.timeframe, mode: params.mode, candles: [] };
  }
  return { state: "ERROR", instrument: params.instrument, timeframe: params.timeframe, mode: params.mode, candles: [], detail: rawState };
}

export async function queryMarketTimeframes(instrument: string, mode: MarketChartMode): Promise<string[]> {
  let res: Response;
  try {
    res = await fetchWithTimeout(
      `${getApiBaseUrl()}/api/v1/market/timeframes?instrument=${encodeURIComponent(instrument)}&mode=${mode}`);
  } catch {
    return [];
  }
  if (!res.ok) return [];
  try {
    const payload = await res.json();
    return Array.isArray(payload?.timeframes) ? payload.timeframes : [];
  } catch {
    return [];
  }
}

export interface IntegrationResult<T> {
  data: T;
  source: IntegrationSource;
  trust: IntegrationTrust;
  asOf: string;
  isFallback: boolean;
  error?: string;
}

export interface BackendPersistenceHealth {
  adapterReachable: boolean;
  databaseConnected: boolean;
  schemaVersion: number | null;
  journalMode: string;
  auditStoreOperational: boolean;
  auditEventCount: number;
  subsystems: Record<string, string>;
}

// Dynamic endpoint and authority configuration
export function getApiBaseUrl(): string {
  if (typeof window !== "undefined" && (window as any).__ALGOFORTIS_API_URL__) {
    return (window as any).__ALGOFORTIS_API_URL__;
  }
  return "";
}

export function isBackendEnabled(): boolean {
  if (typeof window === "undefined") return false;
  // Explicit override: false takes precedence
  if ((window as any).__ALGOFORTIS_ENABLE_BACKEND__ === false) return false;
  // Explicit test harness or dev override
  if ((window as any).__ALGOFORTIS_ENABLE_BACKEND__ === true) return true;
  if (Boolean((window as any).__ALGOFORTIS_API_URL__)) return true;
  // Normal authenticated runtime: active session token indicates backend authority
  if (Boolean(getSessionToken())) return true;
  return false;
}

export function isForceDemo(): boolean {
  if (typeof window === "undefined") return false;
  // Strictly in-memory flag; query string tricks or URL params are NEVER used.
  return (window as any).__ALGOFORTIS_FORCE_DEMO__ === true;
}

const REQUEST_TIMEOUT_MS = 2500;

function getAuthHeaders(): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getSessionToken();
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

async function fetchWithTimeout(url: string, options: RequestInit = {}, timeoutMs: number = REQUEST_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const headers = {
      ...getAuthHeaders(),
      ...(options.headers || {}),
    };
    const res = await fetch(url, { ...options, headers, signal: controller.signal });
    clearTimeout(timeoutId);
    return res;
  } catch (err) {
    clearTimeout(timeoutId);
    throw err;
  }
}

export interface MutationResult<T = any> {
  success: boolean;
  data?: T;
  activationCode?: string | null;
  error?: string;
  isFallback: boolean;
}

/**
 * Query D16 Audit Events from backend persistence authority.
 * Falls back to local sample fixture state if backend is offline.
 */
export async function queryAuditEvents(params?: {
  limit?: number;
  offset?: number;
  eventFamily?: string;
  severity?: string;
}): Promise<IntegrationResult<OwnerAuditRow[]>> {
  const queryParams = new URLSearchParams();
  if (params?.limit) queryParams.set("limit", String(params.limit));
  if (params?.offset) queryParams.set("offset", String(params.offset));
  if (params?.eventFamily && params.eventFamily !== "ALL") queryParams.set("event_family", params.eventFamily);
  if (params?.severity && params.severity !== "ALL") queryParams.set("severity", params.severity);

  const url = `${getApiBaseUrl()}/api/v1/integration/audit/events?${queryParams.toString()}`;

  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        if (json && Array.isArray(json.events)) {
          return {
            data: json.events,
            source: "BACKEND",
            trust: (json.trust as IntegrationTrust) || "FRESH",
            asOf: json.as_of_utc || new Date().toISOString(),
            isFallback: false,
          };
        }
      }
    } catch {
      // Backend offline / network unreachable -> proceed to fallback
    }
  }

  if (isForceDemo()) {
    const fallback = getStoredOwnerAuditEvents();
    return {
      data: fallback,
      source: "SAMPLE_FALLBACK",
      trust: "UNKNOWN",
      asOf: new Date().toISOString(),
      isFallback: true,
    };
  }

  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

/**
 * Query verified persistence and subsystem health facts.
 * Falls back to prototype status if backend is offline.
 */
export async function queryPersistenceHealth(): Promise<IntegrationResult<BackendPersistenceHealth>> {
  const url = `${getApiBaseUrl()}/api/v1/integration/system/health`;

  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        if (json && json.subsystems) {
          return {
            data: {
              adapterReachable: Boolean(json.adapter_reachable),
              databaseConnected: Boolean(json.database_connected),
              schemaVersion: json.schema_version ?? null,
              journalMode: json.journal_mode || "UNKNOWN",
              auditStoreOperational: Boolean(json.audit_store_operational),
              auditEventCount: Number(json.audit_event_count || 0),
              subsystems: json.subsystems,
            },
            source: "BACKEND",
            trust: (json.trust as IntegrationTrust) || "FRESH",
            asOf: json.as_of_utc || new Date().toISOString(),
            isFallback: false,
          };
        }
      }
    } catch {
      // Backend offline -> proceed to fallback
    }
  }

  if (isForceDemo()) {
    return {
      data: {
        adapterReachable: false,
        databaseConnected: false,
        schemaVersion: null,
        journalMode: "UNKNOWN",
        auditStoreOperational: false,
        auditEventCount: 0,
        subsystems: {
          backend_api: "NOT_CONNECTED",
          persistence: "PROTOTYPE_LOCAL",
          audit_journal: "PROTOTYPE_D16",
          engine_orchestrator: "NOT_CONNECTED",
          broker_adapters: "DEFERRED",
          market_data_feeds: "NOT_CONNECTED",
          risk_runtime: "FAIL_CLOSED_CONTRACT",
          service_entitlement: "DEFERRED",
        },
      },
      source: "SAMPLE_FALLBACK",
      trust: "UNKNOWN",
      asOf: new Date().toISOString(),
      isFallback: true,
    };
  }

  return {
    data: {
      adapterReachable: false,
      databaseConnected: false,
      schemaVersion: null,
      journalMode: "UNKNOWN",
      auditStoreOperational: false,
      auditEventCount: 0,
      subsystems: {},
    },
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

/**
 * Query Authoritative Server Time from Backend Authority.
 */
export async function queryServerTime(): Promise<IntegrationResult<{ as_of_utc: string }>> {
  const url = `${getApiBaseUrl()}/api/v1/system/time`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        return {
          data: json,
          source: "BACKEND",
          trust: (json.trust as IntegrationTrust) || "FRESH",
          asOf: json.as_of_utc || new Date().toISOString(),
          isFallback: false,
        };
      }
    } catch {}
  }
  if (isForceDemo()) {
    return {
      data: { as_of_utc: new Date().toISOString() },
      source: "SAMPLE_FALLBACK",
      trust: "UNKNOWN",
      asOf: new Date().toISOString(),
      isFallback: true,
    };
  }
  return {
    data: { as_of_utc: "" },
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

export interface AccessRecordProjection {
  id: string;
  sxId: string;
  accessId: string;
  activationCode: string | null;
  activationStatus: string;
  accountStatus: string;
  status: string;
  displayName: string;
  email: string;
  phone: string;
  emailMasked: string;
  phoneMasked: string;
  createdAt: string;
  expiresAt: string | null;
  redeemedAt: string | null;
  serviceTermType: string;
  serviceTermLabel: string;
  serviceStatus: string;
  serviceStartedAt: string | null;
  serviceExpiresAt: string | null;
  notes: string;
  role: string;
  plan: string;
  createdBy: string;
  history: Array<{ time: string; action: string; actor: string }>;
  activationHistory: Array<any>;
}

/**
 * Query Authoritative Access Records from backend authority.
 * FAIL-CLOSED: Does NOT silently fall back to sample fixtures when backend is unavailable.
 */
export async function queryAccessRecords(): Promise<IntegrationResult<AccessRecordProjection[]>> {
  const url = `${getApiBaseUrl()}/api/v1/integration/access/records`;

  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        if (json && Array.isArray(json.records)) {
          return {
            data: json.records,
            source: "BACKEND",
            trust: (json.trust as IntegrationTrust) || "FRESH",
            asOf: json.as_of_utc || new Date().toISOString(),
            isFallback: false,
          };
        }
      }
    } catch {
      // Backend offline / network unreachable -> fail closed
    }
  }

  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

/**
 * Create User Access Record on Backend Authority.
 * Plaintext activation code is returned ONCE in the response and never persisted or exposed in read projections.
 */
export async function createBackendUserAccess(payload: {
  displayName: string;
  email: string;
  phone?: string;
  role?: string;
  plan?: string;
  serviceTermType?: string;
  customTermValue?: number;
  customTermUnit?: string;
  isDraft?: boolean;
  notes?: string;
}): Promise<MutationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/access/users`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({
        display_name: payload.displayName,
        email: payload.email,
        phone: payload.phone || "",
        role: payload.role || "USER",
        plan: payload.plan || "Quant Professional",
        service_term_type: payload.serviceTermType || "3_MONTHS",
        custom_term_value: payload.customTermValue,
        custom_term_unit: payload.customTermUnit,
        is_draft: Boolean(payload.isDraft),
        notes: payload.notes || "Owner-created access record",
      }),
    });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json.record, activationCode: json.activation_code, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to create user access", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Reissue 24-Hour Activation Code on Backend Authority.
 */
export async function reissueBackendActivation(identifier: string, notes?: string): Promise<MutationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/access/users/${encodeURIComponent(identifier)}/reissue-activation`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ notes: notes || "Reissued 24h activation code" }),
    });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json.reissuance, activationCode: json.activation_code, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to reissue activation code", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Revoke Active Activation Code on Backend Authority.
 */
export async function revokeBackendActivation(identifier: string, notes?: string): Promise<MutationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/access/users/${encodeURIComponent(identifier)}/revoke-activation`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ notes: notes || "Activation invitation revoked" }),
    });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to revoke activation code", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Suspend User Account on Backend Authority.
 */
export async function suspendBackendAccount(identifier: string, notes?: string): Promise<MutationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/access/users/${encodeURIComponent(identifier)}/suspend`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ notes: notes || "Account suspended" }),
    });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to suspend account", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Restore Suspended User Account on Backend Authority.
 */
export async function restoreBackendAccount(identifier: string, notes?: string): Promise<MutationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/access/users/${encodeURIComponent(identifier)}/restore`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ notes: notes || "Account restored" }),
    });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to restore account", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Permanently Revoke User Account on Backend Authority.
 */
export async function revokeBackendAccount(identifier: string, notes?: string): Promise<MutationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/access/users/${encodeURIComponent(identifier)}/revoke`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ notes: notes || "Account permanently revoked" }),
    });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to revoke account", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Extend Service Entitlement on Backend Authority (appends to active expiry).
 */
export async function extendBackendService(
  identifier: string,
  payload: { serviceTermType: string; customTermValue?: number; customTermUnit?: string; notes?: string }
): Promise<MutationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/access/users/${encodeURIComponent(identifier)}/extend-service`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({
        service_term_type: payload.serviceTermType,
        custom_term_value: payload.customTermValue,
        custom_term_unit: payload.customTermUnit,
        notes: payload.notes || "Service entitlement extended",
      }),
    });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to extend service entitlement", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Renew Service Entitlement on Backend Authority (begins from current timestamp).
 */
export async function renewBackendService(
  identifier: string,
  payload: { serviceTermType: string; customTermValue?: number; customTermUnit?: string; notes?: string }
): Promise<MutationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/access/users/${encodeURIComponent(identifier)}/renew-service`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({
        service_term_type: payload.serviceTermType,
        custom_term_value: payload.customTermValue,
        custom_term_unit: payload.customTermUnit,
        notes: payload.notes || "Service entitlement renewed",
      }),
    });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to renew service entitlement", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Convert Service Entitlement to Lifetime on Backend Authority.
 */
export async function convertBackendLifetime(identifier: string, notes?: string): Promise<MutationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/access/users/${encodeURIComponent(identifier)}/convert-lifetime`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ notes: notes || "Converted to Lifetime" }),
    });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to convert to lifetime", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Delete Draft User Record on Backend Authority.
 */
export async function deleteBackendDraft(identifier: string): Promise<MutationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/access/users/${encodeURIComponent(identifier)}/draft`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, { method: "DELETE" });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to delete draft", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

// ─────────────────────────────────────────────────────────────
// Slice 3: Owner Security, Session & Device Authority Queries/Mutations
// ─────────────────────────────────────────────────────────────

export interface OwnerSecurityStatusPayload {
  password_authentication: string;
  webauthn: string;
  webauthn_enrollment: string;
  normal_mtls: string;
  break_glass: string;
  owner_authenticators_ready: boolean;
  normal_mtls_required: boolean;
}

/**
 * Query Security Status from Backend Authority.
 */
export async function querySecurityStatus(): Promise<IntegrationResult<OwnerSecurityStatusPayload>> {
  const url = `${getApiBaseUrl()}/api/v1/security/status`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        return {
          data: json,
          source: "BACKEND",
          trust: "FRESH",
          asOf: new Date().toISOString(),
          isFallback: false,
        };
      }
    } catch {
      // Backend offline -> fallback
    }
  }
  if (isForceDemo()) {
    return {
      data: {
        password_authentication: "FORBIDDEN",
        webauthn: "UNKNOWN",
        webauthn_enrollment: "UNKNOWN",
        normal_mtls: "UNKNOWN",
        break_glass: "UNKNOWN",
        owner_authenticators_ready: false,
        normal_mtls_required: true,
      },
      source: "SAMPLE_FALLBACK",
      trust: "UNKNOWN",
      asOf: new Date().toISOString(),
      isFallback: true,
    };
  }
  return {
    data: null as any,
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

/**
 * Query Active Sessions from Backend Authority.
 */
export async function queryOwnerSessions(): Promise<IntegrationResult<OwnerSessionRow[]>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/security/sessions`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        if (json && Array.isArray(json.sessions)) {
          return {
            data: json.sessions,
            source: "BACKEND",
            trust: (json.trust as IntegrationTrust) || "FRESH",
            asOf: new Date().toISOString(),
            isFallback: false,
          };
        }
      }
    } catch {
      // Backend offline -> proceed to fallback
    }
  }
  if (isForceDemo()) {
    const fallback = getStoredOwnerSessions();
    return {
      data: fallback,
      source: "SAMPLE_FALLBACK",
      trust: "UNKNOWN",
      asOf: new Date().toISOString(),
      isFallback: true,
    };
  }
  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

/**
 * Revoke Single Session on Backend Authority.
 */
export async function revokeBackendSession(sessionRef: string): Promise<MutationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/security/sessions/${encodeURIComponent(sessionRef)}/revoke`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, { method: "POST" });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to revoke session", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Revoke All Sessions for User on Backend Authority.
 */
export async function revokeAllBackendUserSessions(identifier: string): Promise<MutationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/security/users/${encodeURIComponent(identifier)}/sessions/revoke-all`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, { method: "POST" });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to revoke user sessions", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Revoke Current Session on Backend Authority.
 */
export async function revokeCurrentUserSession(): Promise<MutationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/security/sessions/revoke`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, { method: "POST" });
    const json = await res.json();
    if (res.ok && json.revoked) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to revoke session", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Query Registered Devices from Backend Authority.
 */
export async function queryOwnerDevices(): Promise<IntegrationResult<OwnerDeviceRow[]>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/security/devices`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        if (json && Array.isArray(json.devices)) {
          return {
            data: json.devices,
            source: "BACKEND",
            trust: (json.trust as IntegrationTrust) || "FRESH",
            asOf: new Date().toISOString(),
            isFallback: false,
          };
        }
      }
    } catch {
      // Backend offline -> fallback
    }
  }
  if (isForceDemo()) {
    const fallback = getStoredOwnerDevices();
    return {
      data: fallback,
      source: "SAMPLE_FALLBACK",
      trust: "UNKNOWN",
      asOf: new Date().toISOString(),
      isFallback: true,
    };
  }
  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

/**
 * Revoke Registered Device / Credential on Backend Authority.
 */
export async function revokeBackendDevice(credentialId: string): Promise<MutationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/security/devices/${encodeURIComponent(credentialId)}/revoke`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, { method: "POST" });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to revoke device", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Revoke All Registered Devices for User on Backend Authority.
 */
export async function revokeAllBackendUserDevices(identifier: string): Promise<MutationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/security/users/${encodeURIComponent(identifier)}/devices/revoke-all`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, { method: "POST" });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to revoke user devices", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

// ── Slice 4: Owner Strategy Governance ──

/**
 * Query Owner Strategies from Backend Authority.
 */
export async function queryOwnerStrategies(): Promise<IntegrationResult<StrategyRow[]>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/strategies`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        if (json && Array.isArray(json.strategies)) {
          return {
            data: json.strategies,
            source: "BACKEND",
            trust: (json.trust as IntegrationTrust) || "FRESH",
            asOf: json.as_of_utc || new Date().toISOString(),
            isFallback: false,
          };
        }
      }
    } catch {
      // Backend offline -> fallback
    }
  }
  if (isForceDemo()) {
    const fallback = getStoredOwnerStrategies();
    return {
      data: fallback,
      source: "SAMPLE_FALLBACK",
      trust: "UNKNOWN",
      asOf: new Date().toISOString(),
      isFallback: true,
    };
  }
  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

/**
 * Update Strategy Sandbox Allowance on Backend Authority.
 */
export async function updateBackendStrategyAllowance(
  strategyId: string,
  sandbox: "backtest" | "paper" | "live",
  allowance: "ALLOWED" | "HOLD",
  reason?: string
): Promise<MutationResult<{ strategy: StrategyRow; effective: string; message: string }>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/strategies/${encodeURIComponent(strategyId)}/allowance`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ sandbox, allowance, reason }),
    });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to update strategy allowance", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Publish (GLOBAL) / Unpublish (OWNER_PRIVATE) a Strategy on Backend Authority.
 * Backend confirms before UI reports success; user-private rows are rejected.
 */
export async function updateBackendStrategyVisibility(
  strategyId: string,
  visibility: "GLOBAL" | "OWNER_PRIVATE"
): Promise<MutationResult<{ strategy: StrategyRow }>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/strategies/${encodeURIComponent(strategyId)}/visibility`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ visibility }),
    });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to update strategy visibility", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Suspend Strategy Globally on Backend Authority.
 */
export async function suspendBackendStrategy(
  strategyId: string,
  reason?: string
): Promise<MutationResult<{ strategy: StrategyRow }>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/strategies/${encodeURIComponent(strategyId)}/suspend`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ reason }),
    });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to suspend strategy", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Restore Strategy to Active on Backend Authority.
 */
export async function restoreBackendStrategy(
  strategyId: string,
  notes?: string
): Promise<MutationResult<{ strategy: StrategyRow }>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/strategies/${encodeURIComponent(strategyId)}/restore`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ notes }),
    });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to restore strategy", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

export interface PromotionRequestReceipt {
  strategy_id: string;
  target_stage: string;
  status: "PENDING_OWNER_REVIEW";
  requested_at: string;
  run_id?: string | null;
}

export interface PendingPromotionRow {
  strategy_id: string;
  strategy_name: string;
  version: string;
  user_id: string;
  current_stage: string;
  target_stage: string;
  run_id?: string | null;
  notes?: string;
  status: string;
  requested_at_utc: string;
}

/** F-19: User requests promotion with completed backtest evidence (no stage change). Fail-closed, no fallback. */
export async function requestStrategyPromotion(
  strategyId: string,
  opts?: { target_stage?: string; run_id?: string; notes?: string }
): Promise<MutationResult<PromotionRequestReceipt>> {
  const url = `${getApiBaseUrl()}/api/v1/strategies/${encodeURIComponent(strategyId)}/request-promotion`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({
        target_stage: opts?.target_stage || "PAPER_ELIGIBLE",
        run_id: opts?.run_id,
        notes: opts?.notes || "",
      }),
    });
    const json = await res.json();
    if (res.ok && json.status === "PENDING_OWNER_REVIEW") {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Promotion request rejected", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/** F-19: Owner lists persisted pending promotion requests. */
export async function queryPendingPromotions(): Promise<MutationResult<PendingPromotionRow[]>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/promotions/pending`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url);
    const json = await res.json();
    if (res.ok && Array.isArray(json.requests)) {
      return { success: true, data: json.requests, isFallback: false };
    }
    return { success: false, error: json.detail || "Pending promotions unavailable", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/** F-19: Owner-only authoritative stage transition (validated, persisted, re-read). */
export async function approveStrategyPromotion(
  strategyId: string,
  opts: { target_stage: string; version?: string; source_sha256?: string; run_id?: string; notes?: string }
): Promise<MutationResult<{ strategy: StrategyRow }>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/strategies/${encodeURIComponent(strategyId)}/promote`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify(opts),
    });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Promotion rejected", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

export interface SettingProposalReceipt {
  accepted: boolean;
  diff?: string | null;
  current_value?: unknown;
  proposed_value?: unknown;
  proposal_id?: string | null;
  expires_at_utc?: string;
  persisted?: boolean;
}

/** F-18: propose a server setting (persisted only, no effective mutation). */
export async function proposeServerSetting(
  key: string,
  proposed_value: unknown
): Promise<MutationResult<SettingProposalReceipt>> {
  const url = `${getApiBaseUrl()}/api/v1/settings/propose`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ key, proposed_value }),
    });
    const json = await res.json();
    if (res.ok && json.accepted) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.reason || json.detail || "Proposal rejected", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/** F-18: confirm a staged proposal (atomic apply + re-read VERIFY). */
export async function confirmServerSetting(
  proposal_id: string
): Promise<MutationResult<{ key: string; effective_value: unknown; verification: string }>> {
  const url = `${getApiBaseUrl()}/api/v1/settings/confirm`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ proposal_id }),
    });
    const json = await res.json();
    if (res.ok && json.success && json.verification === "VERIFIED") {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Confirmation failed", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/** F-18: re-read effective server-authoritative settings. */
export async function queryServerSettings(): Promise<MutationResult<Record<string, unknown>>> {
  const url = `${getApiBaseUrl()}/api/v1/settings`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url);
    const json = await res.json();
    if (res.ok && json.settings) {
      return { success: true, data: json.settings, isFallback: false };
    }
    return { success: false, error: json.detail || "Settings unavailable", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Check Strategy Execution Hold on Backend Authority.
 */
export async function checkBackendStrategyExecutionHold(
  strategyId: string,
  sandbox: string = "live"
): Promise<{ held: boolean; reason: string | null }> {
  const url = `${getApiBaseUrl()}/api/v1/owner/strategies/${encodeURIComponent(strategyId)}/execution-hold?sandbox=${encodeURIComponent(sandbox)}`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        return { held: Boolean(json.held), reason: json.reason || null };
      }
    } catch {
      // Backend offline -> fallback
    }
  }
  if (isForceDemo()) {
    const strat = getStoredOwnerStrategies().find((s) => s.id === strategyId || s.strategyId === strategyId);
    if (!strat) return { held: false, reason: null };
    const isSuspended = strat.adminStatus === "SUSPENDED";
    const allowance = (strat as any).governance?.[sandbox]?.ownerAllowance;
    if (isSuspended) return { held: true, reason: "Strategy globally suspended" };
    if (allowance === "HOLD") return { held: true, reason: `Sandbox ${sandbox} on owner hold` };
    return { held: false, reason: null };
  }
  return { held: true, reason: "BACKEND_AUTHORITY_UNAVAILABLE" };
}

// ── Slice 4: Owner Connections Governance ──

/**
 * Query Owner Connections from Backend Authority.
 */
export async function queryOwnerConnections(): Promise<IntegrationResult<OwnerConnectionRow[]>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/connections`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        if (json && Array.isArray(json.connections)) {
          return {
            data: json.connections,
            source: "BACKEND",
            trust: (json.trust as IntegrationTrust) || "FRESH",
            asOf: json.as_of_utc || new Date().toISOString(),
            isFallback: false,
          };
        }
      }
    } catch {
      // Backend offline -> fallback
    }
  }
  if (isForceDemo()) {
    const fallback = getStoredOwnerConnections();
    return {
      data: fallback,
      source: "SAMPLE_FALLBACK",
      trust: "UNKNOWN",
      asOf: new Date().toISOString(),
      isFallback: true,
    };
  }
  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

/**
 * Update Connection Allowance on Backend Authority.
 */
export async function updateBackendConnectionAllowance(
  connectionId: string,
  allowance: "ALLOWED" | "HOLD",
  reason?: string
): Promise<MutationResult<{ connection: OwnerConnectionRow; message: string }>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/connections/${encodeURIComponent(connectionId)}/allowance`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ allowance, reason }),
    });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to update connection allowance", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Update Capability Allowance on Backend Authority.
 */
export async function updateBackendCapabilityAllowance(
  connectionId: string,
  capability: string,
  allowance: "ALLOWED" | "HOLD",
  reason?: string
): Promise<MutationResult<{ connection: OwnerConnectionRow; effective: string; message: string }>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/connections/${encodeURIComponent(connectionId)}/capabilities/${encodeURIComponent(capability)}/allowance`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ allowance, reason }),
    });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to update capability allowance", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

// ── Slice 4: Owner Datasets Governance ──

/**
 * Query Owner Datasets from Backend Authority.
 */
export async function queryOwnerDatasets(): Promise<IntegrationResult<OwnerDatasetRow[]>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/datasets`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        if (json && Array.isArray(json.datasets)) {
          return {
            data: json.datasets,
            source: "BACKEND",
            trust: (json.trust as IntegrationTrust) || "FRESH",
            asOf: json.as_of_utc || new Date().toISOString(),
            isFallback: false,
          };
        }
      }
    } catch {
      // Backend offline -> fallback
    }
  }
  if (isForceDemo()) {
    const fallback = getStoredOwnerDatasets();
    return {
      data: fallback,
      source: "SAMPLE_FALLBACK",
      trust: "UNKNOWN",
      asOf: new Date().toISOString(),
      isFallback: true,
    };
  }
  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

/**
 * Update Dataset Approval on Backend Authority.
 */
export async function updateBackendDatasetApproval(
  datasetId: string,
  approval: "APPROVED" | "HOLD" | "REJECTED",
  reason?: string
): Promise<MutationResult<{ dataset: OwnerDatasetRow; effective: string; message: string }>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/datasets/${encodeURIComponent(datasetId)}/approval`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ approval, reason }),
    });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to update dataset approval", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Check Backtest Gate on Backend Authority.
 */
export async function checkBackendBacktestGate(
  strategyId: string,
  datasetId: string
): Promise<{ permitted: boolean; reason: string; strategy_status: string; dataset_status: string }> {
  const url = `${getApiBaseUrl()}/api/v1/owner/backtest/gate`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url, {
        method: "POST",
        body: JSON.stringify({ strategy_id: strategyId, dataset_id: datasetId }),
      });
      if (res.ok) {
        return await res.json();
      }
    } catch {
      // Backend offline -> fallback
    }
  }
  return {
    permitted: false,
    reason: "Backend gate authority unavailable",
    strategy_status: "UNAVAILABLE",
    dataset_status: "UNAVAILABLE",
  };
}

/**
 * Trigger manual historical data sync on Backend Authority.
 */
export async function manualHistoricalSync(
  instrument: string,
  timeframe: string,
  startDate: string,
  endDate: string,
  providerId?: string,
  forceRefresh?: boolean
): Promise<MutationResult<{ success: boolean; job: any; dataset: any }>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/historical/sync/manual`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({
        instrument,
        timeframe,
        start_date: startDate,
        end_date: endDate,
        provider_id: providerId,
        force_refresh: !!forceRefresh,
      }),
    });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to trigger historical sync", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/**
 * Trigger historical gap repair on Backend Authority.
 */
export async function repairHistoricalGaps(
  datasetId?: string,
  instrument?: string,
  timeframe?: string,
  providerId?: string
): Promise<MutationResult<{ success: boolean; report: any }>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/historical/gaps/repair`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({
        dataset_id: datasetId,
        instrument,
        timeframe,
        provider_id: providerId,
      }),
    });
    const json = await res.json();
    if (res.ok && json.success) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || "Failed to repair gaps", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

// ─────────────────────────────────────────────────────────────
// User Workspace Integration Queries (Pre-Slice-5 Step 7)
// ─────────────────────────────────────────────────────────────

export interface UserProfileData {
  user_id: string;
  sx_id?: string;
  role: "OWNER" | "USER";
  lifecycle: string;
  account_status?: string;
  activation_status?: string;
  service_status?: string;
  service_started_at?: string | null;
  service_expires_at?: string | null;
  service_term_type?: string | null;
  custom_term_value?: number | null;
  display_name: string;
  namespace: string;
  workspace_eligibility?: {
    user: boolean;
    owner: boolean;
  };
  effective_access?: boolean;
}

export const DEFAULT_SAMPLE_USER_PROFILE: UserProfileData = {
  user_id: "00000000-0000-0000-0000-000000000001",
  sx_id: "SX-0009-ALPHA",
  role: "USER",
  lifecycle: "ACTIVE",
  account_status: "ACTIVE",
  activation_status: "REDEEMED",
  service_status: "ACTIVE",
  service_started_at: "2026-08-30T00:00:00Z",
  service_expires_at: "2026-11-30T00:00:00Z",
  service_term_type: "CALENDAR_MONTHS",
  custom_term_value: 3,
  display_name: "Alexander Vance",
  namespace: "user",
  workspace_eligibility: {
    user: true,
    owner: false,
  },
  effective_access: true,
};

export async function queryCurrentUserProfile(): Promise<IntegrationResult<UserProfileData>> {
  const url = `${getApiBaseUrl()}/api/v1/users/current`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        return {
          data: json,
          source: "BACKEND",
          trust: "FRESH",
          asOf: new Date().toISOString(),
          isFallback: false,
        };
      }
    } catch {
      // Honest fallback on offline/error
    }
  }
  if (isForceDemo()) {
    return {
      data: DEFAULT_SAMPLE_USER_PROFILE,
      source: "SAMPLE_FALLBACK",
      trust: "UNKNOWN",
      asOf: new Date().toISOString(),
      isFallback: true,
    };
  }
  return {
    data: null as any,
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

export interface UserStrategyEntry {
  strategy_id: string;
  version_id: string;
  stage: string;
  archived: boolean;
  source_sha256: string;
  protective_policy: string;
  admin_status?: string;
  visibility?: "PRIVATE" | "OWNER_PRIVATE" | "GLOBAL";
}

export async function queryUserStrategyRegistry(): Promise<IntegrationResult<UserStrategyEntry[]>> {
  const url = `${getApiBaseUrl()}/api/v1/strategies`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        if (json && Array.isArray(json.strategies)) {
          return {
            data: json.strategies,
            source: "BACKEND",
            trust: json.trust || "FRESH",
            asOf: new Date().toISOString(),
            isFallback: false,
          };
        }
      }
    } catch {
      // Honest fallback on offline/error
    }
  }
  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

/* ════════════════════════════════════════════════════════════
   BI-2 SLICE 5: AUTHORITATIVE BACKTEST CLIENT METHODS
   ════════════════════════════════════════════════════════════ */

export async function queryBacktestDatasets(): Promise<Array<{
  datasetId: string; instrument: string; timeframe: string; startDate: string; endDate: string;
  rowCount: number; hashSha256: string; effectiveBacktestReadiness: string; gapStatus: string; lastUpdated: string;
}>> {
  const res = await fetchWithTimeout(`${getApiBaseUrl()}/api/v1/backtests/datasets`);
  if (!res.ok) throw new Error("Dataset authority unavailable");
  return res.json();
}

export interface WalkForwardWindow {
  windowId: string; seq: number; kind: "IN_SAMPLE" | "OUT_OF_SAMPLE";
  startDate: string; endDate: string; backtestRunId: string | null;
  paperSessionId?: string | null;
  status: string; metrics: Record<string, number | string | null>; error: string | null;
}

export interface WalkForwardJob {
  jobId: string; userId: string; strategyId: string; strategyVersionId: string | null;
  sourceSha256: string | null; datasetId: string; instrument: string; timeframe: string;
  isDays: number; oosDays: number; initialCapital: number; policy: Record<string, unknown>;
  status: "PENDING" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";
  cancelRequested: boolean; overall: Record<string, unknown>; error: string | null;
  windows: WalkForwardWindow[]; progress: { done: number; total: number };
  createdAtUtc: string; updatedAtUtc: string;
}

export interface WalkForwardCreateRequest {
  strategy_id: string; version_id?: string; dataset_id?: string;
  instrument?: string; timeframe?: string; is_days?: number; oos_days?: number;
  max_windows?: number; initial_capital?: number; policy?: Record<string, unknown>;
}

/** Manually RUN a walk-forward/OOS job (single explicit action, no scheduling). */
export async function createWalkForwardJob(
  req: WalkForwardCreateRequest
): Promise<MutationResult<{ job_id: string; status: string; job: WalkForwardJob }>> {
  const url = `${getApiBaseUrl()}/api/v1/walkforward/jobs`;
  if (!isBackendEnabled()) return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  try {
    const res = await fetchWithTimeout(url, { method: "POST", body: JSON.stringify(req) });
    const json = await res.json().catch(() => ({}));
    if ((res.status === 202 || res.ok) && json.job_id) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || `Walk-forward run failed (${res.status})`, isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

export async function listWalkForwardJobs(): Promise<IntegrationResult<WalkForwardJob[]>> {
  const url = `${getApiBaseUrl()}/api/v1/walkforward/jobs`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        if (json && Array.isArray(json.jobs)) {
          return { data: json.jobs, source: "BACKEND", trust: "FRESH", asOf: new Date().toISOString(), isFallback: false };
        }
      }
    } catch { /* fail closed */ }
  }
  return { data: [], source: "UNAVAILABLE", trust: "UNKNOWN", asOf: new Date().toISOString(), isFallback: false, error: "BACKEND_AUTHORITY_UNAVAILABLE" };
}

export async function getWalkForwardJob(jobId: string): Promise<IntegrationResult<WalkForwardJob | null>> {
  const url = `${getApiBaseUrl()}/api/v1/walkforward/jobs/${encodeURIComponent(jobId)}`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        return { data: (json.job || null) as WalkForwardJob | null, source: "BACKEND", trust: "FRESH", asOf: new Date().toISOString(), isFallback: false };
      }
    } catch { /* fail closed */ }
  }
  return { data: null, source: "UNAVAILABLE", trust: "UNKNOWN", asOf: new Date().toISOString(), isFallback: false, error: "BACKEND_AUTHORITY_UNAVAILABLE" };
}

export async function cancelWalkForwardJob(jobId: string): Promise<MutationResult<{ job: WalkForwardJob }>> {
  const url = `${getApiBaseUrl()}/api/v1/walkforward/jobs/${encodeURIComponent(jobId)}/cancel`;
  if (!isBackendEnabled()) return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  try {
    const res = await fetchWithTimeout(url, { method: "POST" });
    const json = await res.json().catch(() => ({}));
    if (res.ok && json.job) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || `Cancel failed (${res.status})`, isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

export interface BacktestExecuteRequest {
  strategy_id: string;
  version_id?: string;
  instrument?: string;
  timeframe?: string;
  initial_capital?: number;
  policy?: { mode: string; distance: number };
  date_range?: string;
  dataset_id?: string;
}

export interface AuthoritativeBacktestRun {
  run_id: string;
  user_id: string;
  strategy_id: string;
  strategy_name: string;
  version: string;
  instrument: string;
  timeframe: string;
  date_range: string;
  initial_capital: number;
  net_profit: number;
  net_profit_pct: number;
  win_rate: number;
  profit_factor: number;
  sharpe_ratio: number;
  max_drawdown: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  avg_profit_trade: number;
  avg_win: number;
  avg_loss: number;
  status: "PENDING" | "COMPLETED" | "FAILED" | "RUNNING" | "CANCEL_REQUESTED" | "CANCELLED";
  quality_score: number;
  policy_snapshot: string;
  policy_details: { mode: string; distance: number; [key: string]: any };
  data_fingerprint: string;
  data_source_name: string;
  manifest_fingerprint?: string;
  execution_metadata?: { dataset_id?: string; [key: string]: unknown };
  equity_curve: { date: string; value: number; drawdown: number }[];
  trades?: any[];
  created_at_utc: string;
  completed_at_utc?: string;
  error_message?: string;
}

export async function executeBacktest(
  params: BacktestExecuteRequest
): Promise<{ ok: boolean; data?: AuthoritativeBacktestRun; error?: string; status?: number }> {
  const url = `${getApiBaseUrl()}/api/v1/backtests`;
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify(params),
    }, 15000); // Backtest may take up to a few seconds
    if (res.ok) {
      const data = await res.json();
      return { ok: true, data, status: res.status };
    }
    const errJson = await res.json().catch(() => ({}));
    return {
      ok: false,
      error: errJson.detail || `Backtest failed with status ${res.status}`,
      status: res.status,
    };
  } catch (err: any) {
    return { ok: false, error: err.message || "Network error executing backtest" };
  }
}

export async function queryBacktestRun(
  runId: string
): Promise<IntegrationResult<AuthoritativeBacktestRun | null>> {
  const url = `${getApiBaseUrl()}/api/v1/backtests/${encodeURIComponent(runId)}`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const data = await res.json();
        return {
          data,
          source: "BACKEND",
          trust: "FRESH",
          asOf: new Date().toISOString(),
          isFallback: false,
        };
      }
    } catch {
      // fallback
    }
  }
  return {
    data: null,
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

export async function queryBacktestTrades(
  runId: string
): Promise<IntegrationResult<any[]>> {
  const url = `${getApiBaseUrl()}/api/v1/backtests/${encodeURIComponent(runId)}/trades`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const data = await res.json();
        return {
          data: Array.isArray(data) ? data : [],
          source: "BACKEND",
          trust: "FRESH",
          asOf: new Date().toISOString(),
          isFallback: false,
        };
      }
    } catch {
      // fallback
    }
  }
  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

export async function queryBacktestRuns(
  limit: number = 50
): Promise<IntegrationResult<AuthoritativeBacktestRun[]>> {
  const url = `${getApiBaseUrl()}/api/v1/backtests?limit=${limit}`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const data = await res.json();
        return {
          data: Array.isArray(data) ? data : [],
          source: "BACKEND",
          trust: "FRESH",
          asOf: new Date().toISOString(),
          isFallback: false,
        };
      }
    } catch {
      // fallback
    }
  }
  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

export async function cancelBacktestRun(
  runId: string
): Promise<{ ok: boolean; error?: string }> {
  const url = `${getApiBaseUrl()}/api/v1/backtests/${encodeURIComponent(runId)}/cancel`;
  try {
    const res = await fetchWithTimeout(url, { method: "POST" });
    if (res.ok) return { ok: true };
    const errJson = await res.json().catch(() => ({}));
    return { ok: false, error: errJson.detail || `Cancellation failed: ${res.status}` };
  } catch (err: any) {
    return { ok: false, error: err.message || "Network error" };
  }
}

export async function queryOwnerBacktestRuns(
  limit: number = 100
): Promise<IntegrationResult<AuthoritativeBacktestRun[]>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/backtests?limit=${limit}`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const data = await res.json();
        return {
          data: Array.isArray(data) ? data : [],
          source: "BACKEND",
          trust: "FRESH",
          asOf: new Date().toISOString(),
          isFallback: false,
        };
      }
    } catch {
      // fallback
    }
  }
  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

/* ════════════════════════════════════════════════════════════
   BI-2 SLICE 5 STEP 2: AUTHORITATIVE PAPER TRADING CLIENT METHODS
   ════════════════════════════════════════════════════════════ */

export interface PaperSessionCreateRequest {
  strategy_id: string;
  instrument?: string;
  timeframe?: string;
  initial_capital?: number;
  policy?: { mode: string; distance: number };
  date_range?: string;
  dataset_id?: string;
  data_source_mode?: 'HISTORICAL_REPLAY' | 'LIVE_MARKET' | string;
}

export interface AuthoritativePaperSession {
  session_id: string;
  user_id: string;
  strategy_id: string;
  strategy_name: string;
  strategy_version: string;
  instrument: string;
  timeframe: string;
  initial_capital: number;
  current_equity: number;
  available_cash: number;
  used_capital: number;
  realized_pnl: number;
  unrealized_pnl: number;
  day_pnl: number;
  total_pnl: number;
  return_pct: number;
  trades_count: number;
  status: string;
  owner_allowance?: string;
  owner_hold_reason?: string | null;
  policy_snapshot?: string;
  policy_details?: Record<string, any>;
  data_source_name?: string;
  data_source_mode?: 'HISTORICAL_REPLAY' | 'LIVE_MARKET' | string;
  feed_status?: 'CONNECTED' | 'RECONNECTING' | 'STALE' | 'DISCONNECTED' | 'ERROR' | string;
  last_market_timestamp?: string | null;
  last_quote_received_at?: string | null;
  contract_identity?: string | null;
  live_quote_count?: number;
  reconciliation_state?: string;
  market_data_readiness?: string;
  persistence_health?: string;
  created_at_utc?: string;
  updated_at_utc?: string;
  stopped_at_utc?: string | null;
  error_message?: string | null;
}

export type PaperMutationResult = {
  ok: boolean;
  data?: AuthoritativePaperSession;
  error?: string;
  status?: number;
  isFallback?: boolean;
};

/**
 * Create an authoritative paper trading session (fail-closed governance
 * enforced by the backend: 403 on suspended/hold strategy, 422 on invalid config).
 */
export async function createPaperSession(
  params: PaperSessionCreateRequest
): Promise<PaperMutationResult> {
  const url = `${getApiBaseUrl()}/api/v1/paper/sessions`;
  if (!isBackendEnabled()) {
    return { ok: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify(params),
    });
    if (res.ok) {
      const data = await res.json();
      return { ok: true, data, status: res.status };
    }
    const errJson = await res.json().catch(() => ({}));
    return {
      ok: false,
      error: errJson.detail || `Paper session creation failed: ${res.status}`,
      status: res.status,
    };
  } catch (err: any) {
    return { ok: false, error: err.message || "Network error creating paper session" };
  }
}

/**
 * Start paper execution for an authoritative session (replays canonical
 * historical data through RiskGate + SimulatedPaperBroker; zero broker routing).
 */
export async function startPaperSession(
  sessionId: string
): Promise<PaperMutationResult> {
  const url = `${getApiBaseUrl()}/api/v1/paper/sessions/${encodeURIComponent(sessionId)}/start`;
  if (!isBackendEnabled()) {
    return { ok: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, { method: "POST" });
    if (res.ok) {
      const data = await res.json();
      return { ok: true, data, status: res.status };
    }
    const errJson = await res.json().catch(() => ({}));
    return {
      ok: false,
      error: errJson.detail || `Paper session start failed: ${res.status}`,
      status: res.status,
    };
  } catch (err: any) {
    return { ok: false, error: err.message || "Network error starting paper session" };
  }
}

/**
 * Stop an authoritative paper trading session (forward execution halted).
 */
export async function stopPaperSession(
  sessionId: string
): Promise<PaperMutationResult> {
  const url = `${getApiBaseUrl()}/api/v1/paper/sessions/${encodeURIComponent(sessionId)}/stop`;
  if (!isBackendEnabled()) {
    return { ok: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, { method: "POST" });
    if (res.ok) {
      const data = await res.json();
      return { ok: true, data, status: res.status };
    }
    const errJson = await res.json().catch(() => ({}));
    return {
      ok: false,
      error: errJson.detail || `Paper session stop failed: ${res.status}`,
      status: res.status,
    };
  } catch (err: any) {
    return { ok: false, error: err.message || "Network error stopping paper session" };
  }
}


/**
 * Query the authenticated user's authoritative paper sessions.
 */
export async function queryPaperSessions(
  limit: number = 50
): Promise<IntegrationResult<AuthoritativePaperSession[]>> {
  const url = `${getApiBaseUrl()}/api/v1/paper/sessions?limit=${limit}`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          return {
            data,
            source: "BACKEND",
            trust: "FRESH",
            asOf: new Date().toISOString(),
            isFallback: false,
          };
        }
      }
    } catch {
      // backend offline -> fallback
    }
  }
  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

/**
 * Query a single authoritative paper session (user-scoped).
 */
export async function queryPaperSession(
  sessionId: string
): Promise<IntegrationResult<AuthoritativePaperSession | null>> {
  const url = `${getApiBaseUrl()}/api/v1/paper/sessions/${encodeURIComponent(sessionId)}`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const data = await res.json();
        return {
          data,
          source: "BACKEND",
          trust: "FRESH",
          asOf: new Date().toISOString(),
          isFallback: false,
        };
      }
    } catch {
      // fallback
    }
  }
  return {
    data: null,
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

/**
 * Query authoritative positions for a paper session.
 */
export async function queryPaperPositions(
  sessionId: string
): Promise<IntegrationResult<any[]>> {
  const url = `${getApiBaseUrl()}/api/v1/paper/sessions/${encodeURIComponent(sessionId)}/positions`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const data = await res.json();
        return {
          data: Array.isArray(data) ? data : [],
          source: "BACKEND",
          trust: "FRESH",
          asOf: new Date().toISOString(),
          isFallback: false,
        };
      }
    } catch {
      // fallback
    }
  }
  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

/**
 * Query the authoritative order/fill blotter for a paper session.
 */
export async function queryPaperOrders(
  sessionId: string
): Promise<IntegrationResult<any[]>> {
  const url = `${getApiBaseUrl()}/api/v1/paper/sessions/${encodeURIComponent(sessionId)}/orders`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const data = await res.json();
        return {
          data: Array.isArray(data) ? data : [],
          source: "BACKEND",
          trust: "FRESH",
          asOf: new Date().toISOString(),
          isFallback: false,
        };
      }
    } catch {
      // fallback
    }
  }
  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

/**
 * Query the authoritative simulation/risk event stream for a paper session.
 */
export async function queryPaperEvents(
  sessionId: string,
  limit: number = 50
): Promise<IntegrationResult<any[]>> {
  const url = `${getApiBaseUrl()}/api/v1/paper/sessions/${encodeURIComponent(sessionId)}/events?limit=${limit}`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const data = await res.json();
        return {
          data: Array.isArray(data) ? data : [],
          source: "BACKEND",
          trust: "FRESH",
          asOf: new Date().toISOString(),
          isFallback: false,
        };
      }
    } catch {
      // fallback
    }
  }
  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

/**
 * Query ALL paper sessions system-wide for Owner oversight.
 */
export async function queryOwnerPaperSessions(
  limit: number = 100
): Promise<IntegrationResult<AuthoritativePaperSession[]>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/paper/sessions?limit=${limit}`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          return {
            data,
            source: "BACKEND",
            trust: "FRESH",
            asOf: new Date().toISOString(),
            isFallback: false,
          };
        }
      }
    } catch {
      // fallback
    }
  }
  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

/**
 * Set or release the Owner hold on a paper session (Owner authority; normal
 * users are blocked by backend HTTP 403 on this endpoint).
 */
export async function setOwnerPaperHold(
  sessionId: string,
  hold: boolean,
  reason?: string
): Promise<{ success: boolean; error?: string; isFallback?: boolean }> {
  const url = `${getApiBaseUrl()}/api/v1/owner/paper/sessions/${encodeURIComponent(sessionId)}/hold`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ hold, reason: reason || undefined }),
    });
    const json = await res.json().catch(() => ({}));
    if (res.ok) {
      return { success: true };
    }
    return { success: false, error: json.detail || `Owner hold failed: ${res.status}` };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error" };
  }
}

export interface LiveQuotePayload {
  event_id: string;
  market?: string;
  instrument: string;
  segment?: string;
  underlying?: string;
  strike?: number;
  option_type?: string;
  exchange_timestamp: string;
  last_price: number;
  bid_price?: number;
  ask_price?: number;
  bid_quantity?: number;
  ask_quantity?: number;
  source?: string;
}

/**
 * Inject an authorized live quote / tick event into an active LIVE_MARKET session.
 */
export async function injectPaperLiveQuote(
  sessionId: string,
  quote: LiveQuotePayload
): Promise<PaperMutationResult> {
  const url = `${getApiBaseUrl()}/api/v1/paper/sessions/${encodeURIComponent(sessionId)}/live-quote`;
  if (!isBackendEnabled()) {
    return { ok: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify(quote),
    });
    if (res.ok) {
      const data = await res.json();
      return { ok: true, data, status: res.status };
    }
    const errJson = await res.json().catch(() => ({}));
    return { ok: false, error: errJson.detail || `Live quote injection failed (${res.status})`, status: res.status };
  } catch (err: any) {
    return { ok: false, error: err.message || "Network error" };
  }
}

/**
 * Update feed connection state for a paper session.
 */
export async function setPaperFeedState(
  sessionId: string,
  state: string
): Promise<{ success: boolean; error?: string }> {
  const url = `${getApiBaseUrl()}/api/v1/paper/sessions/${encodeURIComponent(sessionId)}/feed-state`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE" };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ state }),
    });
    if (res.ok) {
      return { success: true };
    }
    const errJson = await res.json().catch(() => ({}));
    return { success: false, error: errJson.detail || `Feed state update failed (${res.status})` };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error" };
  }
}

export interface AuthoritativeReportItem {
  id: string;
  title: string;
  category: string;
  period: string;
  generatedAt: string;
  fileSize: string;
  format: string;
  status: string;
  summary: string;
  data?: any;
}

/**
 * Query Authoritative Reports for the active user.
 */
export async function queryReports(): Promise<IntegrationResult<AuthoritativeReportItem[]>> {
  const url = `${getApiBaseUrl()}/api/v1/reports`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const items = await res.json();
        return {
          data: Array.isArray(items) ? items : [],
          source: "BACKEND",
          trust: "FRESH",
          asOf: new Date().toISOString(),
          isFallback: false,
        };
      }
    } catch {}
  }
  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

/**
 * Query Authoritative Reports for Owner oversight.
 */
export async function queryOwnerReports(): Promise<IntegrationResult<AuthoritativeReportItem[]>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/reports`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const items = await res.json();
        return {
          data: Array.isArray(items) ? items : [],
          source: "BACKEND",
          trust: "FRESH",
          asOf: new Date().toISOString(),
          isFallback: false,
        };
      }
    } catch {}
  }
  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

// ── F-21: Historical Data Lifecycle Client Helpers ──

export interface MarketDataInventoryItem {
  instrument: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  row_count: number;
  file_sha256: string;
  relative_path: string;
  last_modified_utc: string;
}

export async function queryMarketInventory(): Promise<IntegrationResult<MarketDataInventoryItem[]>> {
  const url = `${getApiBaseUrl()}/api/v1/market/data/inventory`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        return {
          data: Array.isArray(json?.datasets) ? json.datasets : [],
          source: "BACKEND",
          trust: "FRESH",
          asOf: new Date().toISOString(),
          isFallback: false,
        };
      }
    } catch {}
  }
  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

export async function queryMarketCoverage(params: {
  instrument: string;
  timeframe: string;
  startDate: string;
  endDate: string;
}): Promise<any> {
  const query = new URLSearchParams({
    instrument: params.instrument,
    timeframe: params.timeframe,
    start_date: params.startDate,
    end_date: params.endDate,
  });
  const url = `${getApiBaseUrl()}/api/v1/market/data/coverage?${query.toString()}`;
  try {
    const res = await fetchWithTimeout(url);
    if (res.ok) return await res.json();
    return { error: `HTTP ${res.status}` };
  } catch (err: any) {
    return { error: err.message || "Network error" };
  }
}

export async function importMarketData(params: {
  instrument: string;
  timeframe: string;
  rows: any[];
}): Promise<MutationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/market/data/import`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify(params),
    });
    const json = await res.json();
    if (res.ok) return { success: true, data: json.imported, isFallback: false };
    return { success: false, error: json.detail || "Import failed", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

// ── F-10: Durable Strategy Assignment Client Helpers ──

export async function assignStrategyToUser(strategyId: string, userId: string): Promise<MutationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/strategies/${encodeURIComponent(strategyId)}/assign`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    });
    const json = await res.json();
    if (res.ok && json.success) return { success: true, data: json.assignment, isFallback: false };
    return { success: false, error: json.detail || "Assignment failed", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

export async function revokeStrategyAssignment(strategyId: string, userId: string): Promise<MutationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/strategies/${encodeURIComponent(strategyId)}/revoke-assignment`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    });
    const json = await res.json();
    if (res.ok && json.success) return { success: true, isFallback: false };
    return { success: false, error: json.detail || "Revocation failed", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

export async function listStrategyAssignments(strategyId: string): Promise<IntegrationResult<any[]>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/strategies/${encodeURIComponent(strategyId)}/assignments`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        return {
          data: Array.isArray(json?.assignments) ? json.assignments : [],
          source: "BACKEND",
          trust: "FRESH",
          asOf: new Date().toISOString(),
          isFallback: false,
        };
      }
    } catch {}
  }
  return {
    data: [],
    source: "UNAVAILABLE",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: false,
    error: "BACKEND_AUTHORITY_UNAVAILABLE",
  };
}

// ── F-11: Live Paper Reattach Client Helpers ──

export async function reattachPaperSession(sessionId: string): Promise<MutationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/paper/sessions/${encodeURIComponent(sessionId)}/reattach`;
  if (!isBackendEnabled()) {
    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  }
  try {
    const res = await fetchWithTimeout(url, { method: "POST" });
    const json = await res.json();
    if (res.ok) return { success: true, data: json, isFallback: false };
    return { success: false, error: json.detail || "Reattach failed", isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

export async function queryPaperSessionRecoveryStatus(sessionId: string): Promise<any> {
  const url = `${getApiBaseUrl()}/api/v1/paper/sessions/${encodeURIComponent(sessionId)}/recovery-status`;
  try {
    const res = await fetchWithTimeout(url);
    if (res.ok) return await res.json();
    return { error: `HTTP ${res.status}` };
  } catch (err: any) {
    return { error: err.message || "Network error" };
  }
}

// ─────────────────────────────────────────────────────────────
// P1-A: Strategy Readiness + Per-User Connections + Deployments
// Backend-authoritative only. No SAMPLE fallback, no fabricated states.
// ─────────────────────────────────────────────────────────────

export interface ReadinessGate {
  ready: boolean;
  code: string;
  reason: string;
}

export interface StrategyReadiness {
  strategyId: string;
  backtest: ReadinessGate;
  paper: ReadinessGate;
  livePaper: ReadinessGate;
  live: ReadinessGate;
}

/** Backend-authoritative readiness for backtest / paper / live-paper / live. */
export async function queryStrategyReadiness(strategyId: string): Promise<StrategyReadiness | null> {
  if (!isBackendEnabled()) return null;
  try {
    const res = await fetchWithTimeout(
      `${getApiBaseUrl()}/api/v1/strategies/${encodeURIComponent(strategyId)}/readiness`
    );
    if (!res.ok) return null;
    const json = await res.json();
    return json as StrategyReadiness;
  } catch {
    return null;
  }
}

export interface UserConnection {
  connectionId: string;
  userId: string;
  provider: string;
  accountRef: string;
  hasCredentialRef: boolean;
  status: string;
  marketDataCapability: string;
  executionCapability: string;
  healthState: string;
  suspended: boolean;
  suspendReason: string | null;
  lastVerifiedAtUtc?: string | null;
  createdAtUtc?: string;
  updatedAtUtc?: string;
}

async function parseConnectionList(res: Response): Promise<UserConnection[]> {
  const json = await res.json();
  if (Array.isArray(json)) return json as UserConnection[];
  if (Array.isArray(json?.connections)) return json.connections as UserConnection[];
  return [];
}

/** List own per-user connections (authoritative, never includes secrets). */
export async function listUserConnections(): Promise<IntegrationResult<UserConnection[]>> {
  const url = `${getApiBaseUrl()}/api/v1/user/connections`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const data = await parseConnectionList(res);
        return { data, source: "BACKEND", trust: "FRESH", asOf: new Date().toISOString(), isFallback: false };
      }
    } catch { /* fail closed below */ }
  }
  return { data: [], source: "UNAVAILABLE", trust: "UNKNOWN", asOf: new Date().toISOString(), isFallback: false, error: "BACKEND_AUTHORITY_UNAVAILABLE" };
}

export async function createUserConnection(params: {
  provider: string; accountRef: string; credentialRef?: string;
}): Promise<MutationResult<UserConnection>> {
  const url = `${getApiBaseUrl()}/api/v1/user/connections`;
  if (!isBackendEnabled()) return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ provider: params.provider, account_ref: params.accountRef, credential_ref: params.credentialRef }),
    });
    const json = await res.json().catch(() => ({}));
    if (res.ok && (json.success || json.connection)) {
      return { success: true, data: (json.connection || json) as UserConnection, isFallback: false };
    }
    return { success: false, error: json.detail || `Create connection failed (${res.status})`, isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

export async function getUserConnection(connectionId: string): Promise<IntegrationResult<UserConnection | null>> {
  const url = `${getApiBaseUrl()}/api/v1/user/connections/${encodeURIComponent(connectionId)}`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        return { data: (json.connection || json) as UserConnection, source: "BACKEND", trust: "FRESH", asOf: new Date().toISOString(), isFallback: false };
      }
    } catch { /* fail closed */ }
  }
  return { data: null, source: "UNAVAILABLE", trust: "UNKNOWN", asOf: new Date().toISOString(), isFallback: false, error: "BACKEND_AUTHORITY_UNAVAILABLE" };
}

export async function updateUserConnection(
  connectionId: string,
  params: { accountRef?: string; credentialRef?: string; clearCredentialRef?: boolean; status?: string }
): Promise<MutationResult<UserConnection>> {
  const url = `${getApiBaseUrl()}/api/v1/user/connections/${encodeURIComponent(connectionId)}`;
  if (!isBackendEnabled()) return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  try {
    const body: Record<string, unknown> = {};
    if (params.accountRef !== undefined) body.account_ref = params.accountRef;
    if (params.credentialRef !== undefined) body.credential_ref = params.credentialRef;
    if (params.clearCredentialRef !== undefined) body.clear_credential_ref = params.clearCredentialRef;
    if (params.status !== undefined) body.status = params.status;
    const res = await fetchWithTimeout(url, { method: "PATCH", body: JSON.stringify(body) });
    const json = await res.json().catch(() => ({}));
    if (res.ok && (json.success || json.connection)) {
      return { success: true, data: (json.connection || json) as UserConnection, isFallback: false };
    }
    return { success: false, error: json.detail || `Update connection failed (${res.status})`, isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

export interface StrategyConnectionMapping {
  strategy_id: string;
  connection_id: string;
  execution_mode: string;
  strategy_version_id?: string | null;
  [key: string]: unknown;
}

export async function mapStrategyConnection(
  strategyId: string,
  params: { connection_id: string; execution_mode: string; strategy_version_id?: string }
): Promise<MutationResult<StrategyConnectionMapping>> {
  const url = `${getApiBaseUrl()}/api/v1/user/strategies/${encodeURIComponent(strategyId)}/connection`;
  if (!isBackendEnabled()) return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  try {
    const res = await fetchWithTimeout(url, { method: "POST", body: JSON.stringify(params) });
    const json = await res.json().catch(() => ({}));
    if (res.ok && (json.success || json.mapping)) {
      return { success: true, data: (json.mapping || json) as StrategyConnectionMapping, isFallback: false };
    }
    return { success: false, error: json.detail || `Map strategy connection failed (${res.status})`, isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/** Backwards-compatible alias required by P1-A task wiring. */
export const mapUserStrategyConnection = mapStrategyConnection;

export async function retireUserConnection(
  connectionId: string
): Promise<MutationResult<UserConnection>> {
  const url = `${getApiBaseUrl()}/api/v1/user/connections/${encodeURIComponent(connectionId)}/retire`;
  if (!isBackendEnabled()) return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  try {
    const res = await fetchWithTimeout(url, { method: "POST" });
    const json = await res.json().catch(() => ({}));
    if (res.ok && (json.success || json.connection)) {
      return { success: true, data: (json.connection || json) as UserConnection, isFallback: false };
    }
    return { success: false, error: json.detail || `Retire connection failed (${res.status})`, isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

export async function getStrategyMapping(
  strategyId: string,
  executionMode: string = "LIVE_PAPER"
): Promise<IntegrationResult<StrategyConnectionMapping | null>> {
  const url = `${getApiBaseUrl()}/api/v1/user/strategies/${encodeURIComponent(strategyId)}/connection?execution_mode=${encodeURIComponent(executionMode)}`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        return { data: (json.mapping || json) as StrategyConnectionMapping, source: "BACKEND", trust: "FRESH", asOf: new Date().toISOString(), isFallback: false };
      }
      if (res.status === 404) {
        return { data: null, source: "BACKEND", trust: "FRESH", asOf: new Date().toISOString(), isFallback: false };
      }
    } catch { /* fail closed */ }
  }
  return { data: null, source: "UNAVAILABLE", trust: "UNKNOWN", asOf: new Date().toISOString(), isFallback: false, error: "BACKEND_AUTHORITY_UNAVAILABLE" };
}

/** Backwards-compatible alias required by P1-A task wiring. */
export const getStrategyConnectionMapping = getStrategyMapping;

export interface UserDeployment {
  deploymentId: string;
  userId?: string;
  strategyId: string;
  strategyVersionId?: string | null;
  connectionId?: string | null;
  instrument?: string;
  timeframe?: string;
  executionMode?: string;
  execution_mode?: string;
  status: string;
  blockReason?: string | null;
  blockAuthority?: "NONE" | "POLICY" | "OWNER" | "SYSTEM" | "LEGACY";
  runtimeSessionId?: string | null;
  createdAtUtc?: string;
  updatedAtUtc?: string;
  [key: string]: unknown;
}

function normalizeDeploymentList(json: any): UserDeployment[] {
  if (Array.isArray(json)) return json as UserDeployment[];
  if (Array.isArray(json?.deployments)) return json.deployments as UserDeployment[];
  return [];
}

export async function listUserDeployments(status?: string): Promise<IntegrationResult<UserDeployment[]>> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  const url = `${getApiBaseUrl()}/api/v1/user/deployments${q}`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        return { data: normalizeDeploymentList(json), source: "BACKEND", trust: "FRESH", asOf: new Date().toISOString(), isFallback: false };
      }
    } catch { /* fail closed */ }
  }
  return { data: [], source: "UNAVAILABLE", trust: "UNKNOWN", asOf: new Date().toISOString(), isFallback: false, error: "BACKEND_AUTHORITY_UNAVAILABLE" };
}

export async function createUserDeployment(params: {
  strategy_id: string; strategy_version_id?: string; connection_id?: string;
  instrument: string; timeframe?: string; execution_mode?: string; risk_ref?: string;
}): Promise<MutationResult<UserDeployment>> {
  const url = `${getApiBaseUrl()}/api/v1/user/deployments`;
  if (!isBackendEnabled()) return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  try {
    const res = await fetchWithTimeout(url, { method: "POST", body: JSON.stringify(params) });
    const json = await res.json().catch(() => ({}));
    if (res.ok && (json.success || json.deployment)) {
      return { success: true, data: (json.deployment || json) as UserDeployment, isFallback: false };
    }
    return { success: false, error: json.detail || `Create deployment failed (${res.status})`, isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

export async function getUserDeployment(deploymentId: string): Promise<IntegrationResult<UserDeployment | null>> {
  const url = `${getApiBaseUrl()}/api/v1/user/deployments/${encodeURIComponent(deploymentId)}`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        return { data: (json.deployment || json) as UserDeployment, source: "BACKEND", trust: "FRESH", asOf: new Date().toISOString(), isFallback: false };
      }
    } catch { /* fail closed */ }
  }
  return { data: null, source: "UNAVAILABLE", trust: "UNKNOWN", asOf: new Date().toISOString(), isFallback: false, error: "BACKEND_AUTHORITY_UNAVAILABLE" };
}

async function mutateDeployment(
  deploymentId: string,
  action: "pause" | "resume" | "stop",
  method: "POST" = "POST"
): Promise<MutationResult<UserDeployment>> {
  const url = `${getApiBaseUrl()}/api/v1/user/deployments/${encodeURIComponent(deploymentId)}/${action}`;
  if (!isBackendEnabled()) return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  try {
    const res = await fetchWithTimeout(url, { method, body: JSON.stringify({}) });
    const json = await res.json().catch(() => ({}));
    if (res.ok && (json.success || json.deployment)) {
      return { success: true, data: (json.deployment || json) as UserDeployment, isFallback: false };
    }
    return { success: false, error: json.detail || `${action} failed (${res.status})`, isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

export const pauseUserDeployment = (id: string) => mutateDeployment(id, "pause");
export const resumeUserDeployment = (id: string) => mutateDeployment(id, "resume");
export const stopUserDeployment = (id: string) => mutateDeployment(id, "stop");

/** Backwards-compatible aliases required by P1-A task wiring. */
export const pauseDeployment = pauseUserDeployment;
export const resumeDeployment = resumeUserDeployment;
export const stopDeployment = stopUserDeployment;

export async function linkDeploymentRuntime(
  deploymentId: string,
  runtimeSessionId?: string
): Promise<MutationResult<UserDeployment>> {
  const url = `${getApiBaseUrl()}/api/v1/user/deployments/${encodeURIComponent(deploymentId)}/runtime`;
  if (!isBackendEnabled()) return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  try {
    const res = await fetchWithTimeout(url, { method: "POST", body: JSON.stringify({ runtime_session_id: runtimeSessionId ?? null }) });
    const json = await res.json().catch(() => ({}));
    if (res.ok && (json.success || json.deployment)) {
      return { success: true, data: (json.deployment || json) as UserDeployment, isFallback: false };
    }
    return { success: false, error: json.detail || `Link runtime failed (${res.status})`, isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

export async function getUserDeploymentsRecovery(): Promise<IntegrationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/user/deployments-recovery`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        return { data: await res.json(), source: "BACKEND", trust: "FRESH", asOf: new Date().toISOString(), isFallback: false };
      }
    } catch { /* fail closed */ }
  }
  return { data: null as any, source: "UNAVAILABLE", trust: "UNKNOWN", asOf: new Date().toISOString(), isFallback: false, error: "BACKEND_AUTHORITY_UNAVAILABLE" };
}

/** Backwards-compatible alias required by P1-A task wiring. */
export const queryUserDeploymentsRecovery = getUserDeploymentsRecovery;

export async function listAllUserConnections(): Promise<IntegrationResult<UserConnection[]>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/user-connections`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const data = await parseConnectionList(res);
        return { data, source: "BACKEND", trust: "FRESH", asOf: new Date().toISOString(), isFallback: false };
      }
    } catch { /* fail closed */ }
  }
  return { data: [], source: "UNAVAILABLE", trust: "UNKNOWN", asOf: new Date().toISOString(), isFallback: false, error: "BACKEND_AUTHORITY_UNAVAILABLE" };
}

/** Backwards-compatible alias required by P1-A task wiring. */
export const queryAllUserConnections = listAllUserConnections;

export async function setUserConnectionStatus(
  connectionId: string,
  params: { status: string; reason?: string }
): Promise<MutationResult<UserConnection>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/user-connections/${encodeURIComponent(connectionId)}/status`;
  if (!isBackendEnabled()) return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  try {
    const res = await fetchWithTimeout(url, { method: "POST", body: JSON.stringify(params) });
    const json = await res.json().catch(() => ({}));
    if (res.ok && (json.success || json.connection)) {
      return { success: true, data: (json.connection || json) as UserConnection, isFallback: false };
    }
    return { success: false, error: json.detail || `Set status failed (${res.status})`, isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

export async function listAllDeployments(status?: string): Promise<IntegrationResult<UserDeployment[]>> {
  const q = status ? `?status=${encodeURIComponent(status)}` : "";
  const url = `${getApiBaseUrl()}/api/v1/owner/deployments${q}`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        const json = await res.json();
        return { data: normalizeDeploymentList(json), source: "BACKEND", trust: "FRESH", asOf: new Date().toISOString(), isFallback: false };
      }
    } catch { /* fail closed */ }
  }
  return { data: [], source: "UNAVAILABLE", trust: "UNKNOWN", asOf: new Date().toISOString(), isFallback: false, error: "BACKEND_AUTHORITY_UNAVAILABLE" };
}

/** Backwards-compatible alias required by P1-A task wiring. */
export const queryAllDeployments = listAllDeployments;

export async function blockDeployment(deploymentId: string, reason?: string): Promise<MutationResult<UserDeployment>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/deployments/${encodeURIComponent(deploymentId)}/block`;
  if (!isBackendEnabled()) return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  try {
    const res = await fetchWithTimeout(url, { method: "POST", body: JSON.stringify({ reason: reason ?? null }) });
    const json = await res.json().catch(() => ({}));
    if (res.ok && (json.success || json.deployment)) {
      return { success: true, data: (json.deployment || json) as UserDeployment, isFallback: false };
    }
    return { success: false, error: json.detail || `Block failed (${res.status})`, isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}

/** Backwards-compatible alias required by P1-A task wiring. */
export const blockOwnerDeployment = blockDeployment;

export async function getOwnerDeploymentsRecovery(): Promise<IntegrationResult<any>> {
  const url = `${getApiBaseUrl()}/api/v1/owner/deployments-recovery`;
  if (isBackendEnabled()) {
    try {
      const res = await fetchWithTimeout(url);
      if (res.ok) {
        return { data: await res.json(), source: "BACKEND", trust: "FRESH", asOf: new Date().toISOString(), isFallback: false };
      }
    } catch { /* fail closed */ }
  }
  return { data: null as any, source: "UNAVAILABLE", trust: "UNKNOWN", asOf: new Date().toISOString(), isFallback: false, error: "BACKEND_AUTHORITY_UNAVAILABLE" };
}

/** Backwards-compatible alias required by P1-A task wiring. */
export const queryOwnerDeploymentsRecovery = getOwnerDeploymentsRecovery;

export async function promoteStrategy(
  strategyId: string,
  targetStage: string = "LIVE"
): Promise<MutationResult<{ strategy_id: string; stage: string; readiness: string }>> {
  const url = `${getApiBaseUrl()}/api/v1/user/strategies/${encodeURIComponent(strategyId)}/promote`;
  if (!isBackendEnabled()) return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };
  try {
    const res = await fetchWithTimeout(url, {
      method: "POST",
      body: JSON.stringify({ target_stage: targetStage }),
    });
    const json = await res.json().catch(() => ({}));
    if (res.ok && (json.success || json.strategy)) {
      return { success: true, data: json, isFallback: false };
    }
    return { success: false, error: json.detail || `Promotion failed (${res.status})`, isFallback: false };
  } catch (err: any) {
    return { success: false, error: err.message || "Network error", isFallback: false };
  }
}
