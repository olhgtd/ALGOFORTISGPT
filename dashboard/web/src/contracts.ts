/**
 * Governed TypeScript contracts for the AlgoFortis control center.
 * These types mirror the authoritative backend DTOs; the frontend
 * never fabricates evidence, candles, volume, signals, or protective state.
 */

export type Trust = "FRESH" | "STALE" | "UNKNOWN";
export type SecurityStatus = "CONFIGURED" | "NOT_CONFIGURED" | "UNKNOWN" | "NEEDS_ROTATION";
export type ChartMode = "LIVE" | "FROZEN_HISTORICAL" | "BACKTEST";

export interface PasswordActivationRequest {
  identifier: string;
  activation_code: string;
  email: string;
  password: string;
  confirm_password: string;
}

export interface PasswordActivationResponse {
  activated: true;
  authentication_required: true;
}

export interface PasswordLoginRequest {
  identifier: string;
  password: string;
}

export interface PasswordSessionResponse {
  access_token: string;
  expires_at_utc: string;
  subject: string;
  role: "OWNER" | "USER";
  sx_id: string | null;
  workspace_eligibility: {
    owner: boolean;
    user: boolean;
  };
}

export interface Trusted<T> {
  value: T | null;
  trust: Trust;
  as_of_utc: string | null;
  source_identity?: string | null;
  state_fingerprint?: string | null;
}

export interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface ChartMarker {
  time: string;
  kind: "SIGNAL" | "ENTRY" | "EXIT";
  price: number;
  label: string;
}

export interface Overlay {
  kind: "STOP" | "TARGET" | "TRAILING";
  price: number;
  time?: string;
  label?: string;
}

export interface ChartPayload {
  mode: ChartMode;
  instrument: string;
  timeframe: string;
  candles: Trusted<Candle[]>;
  markers: Trusted<ChartMarker[]>;
  overlays: Trusted<Overlay[]>;
}

export interface OverviewPayload {
  owner_id: string;
  role: string;
  session_risk: string;
  safe_mode: boolean;
  live_state: Trusted<unknown>;
}

export interface HealthPayload {
  service: string;
  status: string;
  safe_mode: boolean;
}

export interface SecurityStatusPayload {
  password_authentication: string;
  owner_initialized?: boolean;
  webauthn: SecurityStatus;
  webauthn_enrollment: SecurityStatus;
  normal_mtls: SecurityStatus;
  break_glass: SecurityStatus;
  owner_authenticators_ready: boolean;
  normal_mtls_required: boolean;
}

/** Portfolio / data / audit read-only payloads */
export interface PortfolioSummary {
  trust: Trust;
  as_of_utc: string | null;
  positions: Trusted<PositionItem[]>;
  daily_pnl: Trusted<number>;
  capital: Trusted<{ starting: number; current: number; free_margin: number; currency: string }>;
}

export interface PositionItem {
  instrument: string;
  direction: "LONG" | "SHORT";
  quantity: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  stop_loss?: number;
  target_price?: number;
  as_of_utc: string;
}

export interface OrderItem {
  order_id: string;
  strategy_id: string;
  instrument: string;
  side: "BUY" | "SELL";
  order_type: "MARKET" | "LIMIT" | "STOP_LIMIT";
  quantity: number;
  filled_quantity: number;
  price: number;
  status: "FILLED" | "PENDING" | "REJECTED" | "CANCELLED";
  submitted_at_utc: string;
  execution_hash: string;
}

export interface StrategyRecord {
  strategy_id: string;
  version: string;
  name: string;
  lifecycle_state: "ADDED" | "VALIDATED" | "BACKTEST_ELIGIBLE" | "PAPER_ELIGIBLE" | "LIVE_ELIGIBLE";
  quality_score: number | null;
  safety_check_passed: boolean;
  last_validated_utc: string;
  protective_policy: string;
}

export interface AuditEntry {
  actor_id: string;
  action: string;
  payload: Record<string, unknown>;
  recorded_at_utc: string;
  record_hash: string;
}

export interface SettingsProposal {
  key: string;
  current_value: unknown;
  proposed_value: unknown;
  dry_run_result: string | null;
  diff: string | null;
}

export interface BacktestRunSummary {
  run_id: string;
  strategy_id: string;
  period: string;
  total_trades: number;
  win_rate_pct: number;
  profit_factor: number;
  sharpe_ratio: number;
  max_drawdown_pct: number;
  engine_hash: string;
}

/* ─── Strategy governance registry (authoritative backend projections) ─── */

export interface StrategyRegistryEntry {
  strategy_id: string;
  version_id: string;
  stage: string;
  archived: boolean;
  source_sha256: string;
  protective_policy: string;
}

export interface StrategyRegistryResponse {
  strategies: StrategyRegistryEntry[];
  trust: Trust;
}

export interface StrategySubmitResult {
  strategy_id: string;
  version_id: string;
  stage: string;
  source_sha256: string;
}

/** Informational evidence only — never grants eligibility by itself. */
export interface StrategyQualityResult {
  score?: number;
  grade?: string;
  components?: Record<string, unknown>;
  eligibility_changed: boolean;
  trust?: Trust;
}

export interface StrategyArchiveResult {
  version_id: string;
  stage: string;
  archived: boolean;
}
