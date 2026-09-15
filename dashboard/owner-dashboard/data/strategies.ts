/**
 * SentinelX Dashboard V3 — Strategy Domain State & Governance
 */
import type { Truth } from "../../shared/data/sharedTypes";
import { STORAGE_KEYS, prototypeFixtureStorage, safeGetJson, safeSetJson } from "../../shared/data/storage";

const localStorage = prototypeFixtureStorage;

export type StrategyStage = "LIVE" | "PAPER" | "BACKTEST_ELIGIBLE" | "BACKTEST";
export type StrategyConformance = "CONFORMANT" | "NON_CONFORMANT" | "PENDING_SCAN";
export type StrategyEligibility = "ELIGIBLE" | "BLOCKED";
export type StrategyAdminStatus = "ACTIVE" | "SUSPENDED" | "DEPRECATED";
export type StrategyValidationStage = "LIVE_PROMOTED" | "PAPER_VERIFIED" | "BACKTEST_VERIFIED" | "UNTESTED" | "FAILED_VALIDATION";

export type SystemReadinessStatus = "READY" | "BLOCKED";
export type OwnerAllowanceStatus = "ALLOWED" | "HOLD";
export type EffectiveEligibilityStatus = "ELIGIBLE" | "BLOCKED";

export interface SandboxGovernanceState {
  systemReadiness: SystemReadinessStatus;
  systemBlockerReason?: string;
  ownerAllowance: OwnerAllowanceStatus;
  ownerHoldReason?: string;
  effectiveEligibility: EffectiveEligibilityStatus;
}

export function computeEffectiveEligibility(
  systemReadiness: SystemReadinessStatus,
  ownerAllowance: OwnerAllowanceStatus,
  isSuspended: boolean
): {
  status: EffectiveEligibilityStatus;
  label: string;
  tone: "ok" | "warn" | "neg" | "dim";
  reason: string;
} {
  if (isSuspended) {
    return {
      status: "BLOCKED",
      label: "BLOCKED (SUSPENDED)",
      tone: "neg",
      reason: "Global strategy suspension is active (Owner administrative hold).",
    };
  }
  if (systemReadiness !== "READY") {
    return {
      status: "BLOCKED",
      label: "BLOCKED (SYSTEM GATE)",
      tone: "dim",
      reason: "System readiness gate unsatisfied. Owner allowance cannot override engine/validation prerequisites.",
    };
  }
  if (ownerAllowance !== "ALLOWED") {
    return {
      status: "BLOCKED",
      label: "BLOCKED (OWNER HOLD)",
      tone: "warn",
      reason: "Placed on administrative hold by Owner.",
    };
  }
  return {
    status: "ELIGIBLE",
    label: "ELIGIBLE",
    tone: "ok",
    reason: "System readiness verified and Owner allowance granted.",
  };
}

export function getStrategyGovernance(s: StrategyRow): {
  backtest: SandboxGovernanceState;
  paper: SandboxGovernanceState;
  live: SandboxGovernanceState;
} {
  const isConformant = s.conformanceStatus === "CONFORMANT" || s.conformanceCheck === "CONFORMANT";
  const defaultBacktest: SandboxGovernanceState = {
    systemReadiness: isConformant ? "READY" : "BLOCKED",
    systemBlockerReason: isConformant ? undefined : "Strategy fails AST static analysis.",
    ownerAllowance: s.backtestEligibility === "BLOCKED" ? "HOLD" : "ALLOWED",
    effectiveEligibility: isConformant && s.backtestEligibility !== "BLOCKED" ? "ELIGIBLE" : "BLOCKED",
  };
  const defaultPaper: SandboxGovernanceState = {
    systemReadiness: isConformant && s.evidenceAttached ? "READY" : "BLOCKED",
    systemBlockerReason: isConformant && s.evidenceAttached ? undefined : "Backtest validation evidence unattached.",
    ownerAllowance: s.paperEligibility === "ELIGIBLE" ? "ALLOWED" : "HOLD",
    effectiveEligibility: isConformant && s.evidenceAttached && s.paperEligibility === "ELIGIBLE" ? "ELIGIBLE" : "BLOCKED",
  };
  const defaultLive: SandboxGovernanceState = {
    systemReadiness: isConformant && s.stage === "LIVE" ? "READY" : "BLOCKED",
    systemBlockerReason: isConformant && s.stage === "LIVE" ? undefined : "Paper forward evaluation tracking report incomplete.",
    ownerAllowance: s.liveEligibility === "ELIGIBLE" ? "ALLOWED" : "HOLD",
    effectiveEligibility: isConformant && s.stage === "LIVE" && s.liveEligibility === "ELIGIBLE" ? "ELIGIBLE" : "BLOCKED",
  };

  return {
    backtest: s.backtestGovernance || defaultBacktest,
    paper: s.paperGovernance || defaultPaper,
    live: s.liveGovernance || defaultLive,
  };
}

export interface StrategyGovernanceEvent {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  note: string;
  tone?: "ok" | "warn" | "neg" | "dim";
}

export interface StrategyRow {
  id: string;
  strategyId?: string;
  name: string;
  version: string;
  interfaceVersion?: string;
  language: "Python";
  stage: StrategyStage;
  category?: string;
  instruments?: string[];
  timeframes?: string[];
  quality: number;
  evidenceAttached: boolean;
  pnl: string;
  isProfit: boolean;
  note: string;
  description: string;
  author: string;
  authorSxId?: string;
  visibility?: "PRIVATE" | "OWNER_PRIVATE" | "GLOBAL";
  lastUpdated: string;
  scanStatus: "PASSED" | "WARNING" | "PENDING" | "FAILED";
  conformanceCheck: "CONFORMANT" | "NON_CONFORMANT";
  conformanceStatus?: StrategyConformance;

  // Independent Sandbox Governance States (Optional for backward compatibility with component constructors)
  backtestGovernance?: SandboxGovernanceState;
  paperGovernance?: SandboxGovernanceState;
  liveGovernance?: SandboxGovernanceState;

  // Legacy compat fields
  backtestEligibility?: StrategyEligibility;
  paperEligibility?: StrategyEligibility;
  liveEligibility?: StrategyEligibility;

  adminStatus?: StrategyAdminStatus;
  validationStage?: StrategyValidationStage;
  stateSchemaDeclared?: boolean;
  dataAccessWrapper?: boolean;
  riskEnvelope?: string;
  astScanDetails?: string;
  governanceHistory?: StrategyGovernanceEvent[];
  winRate?: number;
  maxDrawdown?: number;
  profitFactor?: number;
  sharpeRatio?: number;
  totalTrades?: number;
  activePositions?: number;
}

export const INITIAL_OWNER_STRATEGIES: StrategyRow[] = [];

export const STRATEGIES: StrategyRow[] = INITIAL_OWNER_STRATEGIES;

const OWNER_STRATEGIES_STORAGE_KEY = STORAGE_KEYS.OWNER_STRATEGIES;

export function getStoredOwnerStrategies(): StrategyRow[] {
  try {
    const raw = localStorage.getItem(OWNER_STRATEGIES_STORAGE_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed;
    }
    return [];
  } catch {
    return [];
  }
}

export function saveOwnerStrategies(strategies: StrategyRow[]): void {
  try {
    localStorage.setItem(OWNER_STRATEGIES_STORAGE_KEY, JSON.stringify(strategies));
  } catch (err) {
    console.error("Failed to save owner strategies", err);
  }
}

export function updateOwnerSandboxAllowance(
  strategyId: string,
  sandbox: "backtest" | "paper" | "live",
  allowance: OwnerAllowanceStatus,
  reason?: string,
  actor: string = "OWNER-001"
): { success: boolean; effective: EffectiveEligibilityStatus; message: string } {
  const current = getStoredOwnerStrategies();
  const index = current.findIndex((s) => s.id === strategyId || s.strategyId === strategyId);
  if (index === -1) return { success: false, effective: "BLOCKED", message: "Strategy not found" };

  const strat = { ...current[index] };
  const isSuspended = strat.adminStatus === "SUSPENDED";
  const allGov = getStrategyGovernance(strat);
  const gov = { ...allGov[sandbox] };

  gov.ownerAllowance = allowance;
  if (allowance === "HOLD") {
    gov.ownerHoldReason = reason || `Placed on hold by ${actor}`;
  } else {
    delete gov.ownerHoldReason;
  }

  const computed = computeEffectiveEligibility(gov.systemReadiness, gov.ownerAllowance, isSuspended);
  gov.effectiveEligibility = computed.status;

  if (sandbox === "backtest") {
    strat.backtestGovernance = gov;
    strat.backtestEligibility = computed.status;
  } else if (sandbox === "paper") {
    strat.paperGovernance = gov;
    strat.paperEligibility = computed.status;
  } else {
    strat.liveGovernance = gov;
    strat.liveEligibility = computed.status;
  }

  const event: StrategyGovernanceEvent = {
    id: `gov-${Date.now()}`,
    timestamp: new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC",
    actor,
    action: `OWNER_ALLOWANCE_${sandbox.toUpperCase()}_${allowance}`,
    note: `Owner set ${sandbox.toUpperCase()} allowance to ${allowance} (Effective: ${computed.label})`,
    tone: computed.status === "ELIGIBLE" ? "ok" : "warn",
  };

  strat.governanceHistory = [event, ...(strat.governanceHistory || [])];
  current[index] = strat;
  saveOwnerStrategies(current);

  let msg = `Owner ${sandbox.toUpperCase()} allowance set to ${allowance}.`;
  if (allowance === "ALLOWED" && gov.systemReadiness !== "READY") {
    msg += ` Effective eligibility remains BLOCKED by system readiness gate.`;
  }
  return { success: true, effective: computed.status, message: msg };
}

// Backward-compatible alias for existing test runners
export function updateStrategySandboxEligibility(
  strategyId: string,
  sandbox: "backtest" | "paper" | "live",
  eligible: boolean,
  actor: string = "OWNER-001"
): { success: boolean; error?: string } {
  const allowance: OwnerAllowanceStatus = eligible ? "ALLOWED" : "HOLD";
  const res = updateOwnerSandboxAllowance(strategyId, sandbox, allowance, undefined, actor);
  return { success: res.success, error: res.message };
}

export function suspendStrategy(
  strategyId: string,
  reason: string = "Owner administrative hold",
  actor: string = "OWNER-001"
): void {
  const current = getStoredOwnerStrategies();
  const index = current.findIndex((s) => s.id === strategyId || s.strategyId === strategyId);
  if (index === -1) return;

  const strat = { ...current[index] };
  strat.adminStatus = "SUSPENDED";
  const gov = getStrategyGovernance(strat);

  strat.backtestGovernance = { ...gov.backtest, effectiveEligibility: "BLOCKED" };
  strat.paperGovernance = { ...gov.paper, effectiveEligibility: "BLOCKED" };
  strat.liveGovernance = { ...gov.live, effectiveEligibility: "BLOCKED" };

  strat.backtestEligibility = "BLOCKED";
  strat.paperEligibility = "BLOCKED";
  strat.liveEligibility = "BLOCKED";

  const event: StrategyGovernanceEvent = {
    id: `gov-${Date.now()}`,
    timestamp: new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC",
    actor,
    action: "ADMIN_SUSPENDED",
    note: `Owner suspended strategy: ${reason}`,
    tone: "neg",
  };

  strat.governanceHistory = [event, ...(strat.governanceHistory || [])];
  current[index] = strat;
  saveOwnerStrategies(current);
}

export function restoreStrategy(
  strategyId: string,
  actor: string = "OWNER-001"
): void {
  const current = getStoredOwnerStrategies();
  const index = current.findIndex((s) => s.id === strategyId || s.strategyId === strategyId);
  if (index === -1) return;

  const strat = { ...current[index] };
  strat.adminStatus = "ACTIVE";
  const gov = getStrategyGovernance(strat);

  const bEff = computeEffectiveEligibility(gov.backtest.systemReadiness, gov.backtest.ownerAllowance, false);
  strat.backtestGovernance = { ...gov.backtest, effectiveEligibility: bEff.status };
  strat.backtestEligibility = bEff.status;

  const pEff = computeEffectiveEligibility(gov.paper.systemReadiness, gov.paper.ownerAllowance, false);
  strat.paperGovernance = { ...gov.paper, effectiveEligibility: pEff.status };
  strat.paperEligibility = pEff.status;

  const lEff = computeEffectiveEligibility(gov.live.systemReadiness, gov.live.ownerAllowance, false);
  strat.liveGovernance = { ...gov.live, effectiveEligibility: lEff.status };
  strat.liveEligibility = lEff.status;

  const event: StrategyGovernanceEvent = {
    id: `gov-${Date.now()}`,
    timestamp: new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC",
    actor,
    action: "ADMIN_RESTORED",
    note: "Owner restored strategy to ACTIVE governance status (Effective eligibilities restored to system/allowance permits)",
    tone: "ok",
  };

  strat.governanceHistory = [event, ...(strat.governanceHistory || [])];
  current[index] = strat;
  saveOwnerStrategies(current);
}
