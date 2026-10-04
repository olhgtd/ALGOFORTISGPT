/**
 * AlgoFortis Owner Dashboard — Backtests Oversight & Paper Sessions Governance
 */
import type { Truth, BacktestRun, PaperPosition } from "../../shared/data/sharedTypes";
import type { EffectiveEligibilityStatus, OwnerAllowanceStatus } from "./strategies";
import type { DatasetEffectiveReadiness } from "./datasets";
import { getStoredOwnerStrategies, getStrategyGovernance, computeEffectiveEligibility } from "./strategies";
import { getStoredOwnerDatasets } from "./datasets";
import { STORAGE_KEYS, prototypeFixtureStorage, safeGetJson, safeSetJson } from "../../shared/data/storage";

const localStorage = prototypeFixtureStorage;

export type BacktestRunExecutionStatus = "PENDING" | "COMPLETED" | "RUNNING" | "FAILED" | "CANCEL_REQUESTED" | "CANCELLED";
export type BacktestEvidenceQuality = "EVIDENCE_ACCEPTED" | "VALIDATION_FAILED" | "PENDING_AUDIT";
export type BacktestPromotionRelevance = "PAPER_CANDIDATE" | "REVISE_PARAMETERS" | "FAILED_VALIDATION";

export interface OwnerBacktestRunRow {
  id: string;
  runId: string;
  strategyId: string;
  strategyName: string;
  strategyVersion: string;
  engineInterfaceVersion: string;
  datasetId: string;
  datasetCoverage: string;
  datasetTimeframe: string;
  executionStatus: BacktestRunExecutionStatus;
  executionFailureReason?: string;
  validationQuality: BacktestEvidenceQuality;
  validationDetails: string;
  startedAt: string;
  completedAt: string;
  durationSeconds: number;
  replayFingerprint: string;
  initialCapital: number;
  netProfit: number;
  netProfitPct: number;
  winRatePct: number;
  profitFactor: number;
  sharpeRatio: number;
  maxDrawdownPct: number;
  totalTrades: number;
  avgProfitTrade: number;
  promotionRelevance: BacktestPromotionRelevance;
  auditEvents: { time: string; text: string; actor: string; tone?: "ok" | "warn" | "neg" | "dim" }[];
}

export const INITIAL_OWNER_BACKTESTS: OwnerBacktestRunRow[] = [];

export function computeEffectiveBacktestSubmission(
  strategyId: string,
  selectedDatasetId?: string
): {
  status: EffectiveEligibilityStatus;
  label: string;
  tone: "ok" | "warn" | "neg" | "dim";
  reason: string;
  strategyEligibility: EffectiveEligibilityStatus;
  datasetReadiness?: DatasetEffectiveReadiness;
} {
  const strats = getStoredOwnerStrategies();
  const strat = strats.find((s) => s.strategyId === strategyId || s.id === strategyId);
  if (!strat) {
    return {
      status: "BLOCKED",
      label: "BLOCKED (STRATEGY NOT FOUND)",
      tone: "neg",
      reason: "Strategy not registered in Step 4 governance store",
      strategyEligibility: "BLOCKED",
    };
  }

  const gov = getStrategyGovernance(strat);
  const stratEff = computeEffectiveEligibility(gov.backtest.systemReadiness, gov.backtest.ownerAllowance, strat.adminStatus === "SUSPENDED");
  if (stratEff.status === "BLOCKED") {
    return {
      status: "BLOCKED",
      label: stratEff.label === "BLOCKED (OWNER HOLD)" ? "BLOCKED (STRATEGY OWNER HOLD)" : stratEff.label === "BLOCKED (SYSTEM GATE)" ? "BLOCKED (STRATEGY SYSTEM GATE)" : stratEff.label,
      tone: stratEff.tone,
      reason: `Step 4 Governance: ${stratEff.reason}`,
      strategyEligibility: "BLOCKED",
    };
  }

  if (selectedDatasetId) {
    const datasets = getStoredOwnerDatasets();
    const ds = datasets.find((d) => d.datasetId === selectedDatasetId || d.id === selectedDatasetId);
    if (!ds || ds.effectiveBacktestReadiness !== "READY_FOR_BACKTEST") {
      return {
        status: "BLOCKED",
        label: "BLOCKED (DATASET NOT READY)",
        tone: "warn",
        reason: "Selected dataset is not approved and ready under Step 5 governance.",
        strategyEligibility: "ELIGIBLE",
        datasetReadiness: ds ? ds.effectiveBacktestReadiness : undefined,
      };
    }
  }

  return {
    status: "ELIGIBLE",
    label: "ELIGIBLE FOR SUBMISSION",
    tone: "ok",
    reason: "Strategy backtest eligibility verified (Step 4) and dataset approved (Step 5).",
    strategyEligibility: "ELIGIBLE",
    datasetReadiness: "READY_FOR_BACKTEST",
  };
}

export type PaperSessionState = "ACTIVE" | "PAUSED" | "TERMINATED" | "FAILED";
export type PaperMarketDataReadiness = "READY" | "DEGRADED" | "OFFLINE" | "UNKNOWN";
export type PaperPersistenceHealth = "SEALED" | "DIRTY" | "REPLAY_VERIFIED" | "CORRUPT" | "UNKNOWN";
export type PaperReconciliationStatus = "MATCH_HEALTHY" | "MISMATCH_DETECTED" | "RECONCILING" | "UNKNOWN";
export type PaperPromotionEvidenceState = "TRACKING_ACTIVE" | "CRITERIA_MET" | "BLOCKED_EVIDENCE" | "NOT_PROMOTED" | "UNKNOWN";
export type PaperRiskEnvelopeState = "NOMINAL" | "THROTTLED" | "TRIPPED" | "UNKNOWN";

export interface OwnerPaperSessionRow {
  id: string;
  sessionId: string;
  strategyId: string;
  strategyName: string;
  strategyVersion: string;
  environment: "Paper / Sandbox";
  startedAt: string;
  lastHeartbeat: string;
  sessionState: PaperSessionState;
  connectionRef: string;
  marketDataReadiness: PaperMarketDataReadiness;
  persistenceHealth: PaperPersistenceHealth;
  reconciliationState: PaperReconciliationStatus;
  reconciliationFinding?: string;
  promotionEvidenceState: PaperPromotionEvidenceState;
  promotionEvidenceNotes: string;
  protectivePolicyId: string;
  riskEnvelopeState: PaperRiskEnvelopeState;
  simulatedCapital: number;
  unrealizedPnl: string;
  realizedPnl: string;
  ordersCount: number;
  positionsCount: number;
  ownerAllowance: OwnerAllowanceStatus;
  ownerHoldReason?: string;
  dataSourceMode?: string;
  feedStatus?: string;
  lastMarketTimestamp?: string | null;
  auditEvents: { time: string; text: string; actor: string; tone?: "ok" | "warn" | "neg" | "dim" }[];
}

export function computePaperEffectiveStatus(
  sessionState: PaperSessionState,
  marketDataReadiness: PaperMarketDataReadiness,
  persistenceHealth: PaperPersistenceHealth,
  reconciliationState: PaperReconciliationStatus,
  ownerAllowance: OwnerAllowanceStatus
): {
  status: "OPERATIONAL" | "DEGRADED" | "BLOCKED";
  label: string;
  tone: "ok" | "warn" | "neg";
  blocker?: string;
} {
  if (ownerAllowance === "HOLD") {
    return {
      status: "BLOCKED",
      label: "BLOCKED (OWNER HOLD)",
      tone: "warn",
      blocker: "Owner administrative hold active on paper activity",
    };
  }
  if (sessionState === "FAILED" || sessionState === "TERMINATED" || persistenceHealth === "CORRUPT") {
    return {
      status: "BLOCKED",
      label: `BLOCKED (${sessionState === "TERMINATED" ? "TERMINATED" : "SYSTEM ERROR"})`,
      tone: "neg",
      blocker: persistenceHealth === "CORRUPT" ? "Persistence state store corrupt" : `Session is ${sessionState.toLowerCase()}`,
    };
  }
  if (sessionState === "PAUSED") {
    return {
      status: "BLOCKED",
      label: "PAUSED (ENGINE LOOP)",
      tone: "warn",
      blocker: "Session engine loop paused",
    };
  }
  if (marketDataReadiness !== "READY" || persistenceHealth !== "SEALED" || reconciliationState === "MISMATCH_DETECTED") {
    const reasons: string[] = [];
    if (marketDataReadiness !== "READY") reasons.push(`Feed ${marketDataReadiness.toLowerCase()}`);
    if (persistenceHealth !== "SEALED") reasons.push(`Store ${persistenceHealth.toLowerCase()}`);
    if (reconciliationState === "MISMATCH_DETECTED") reasons.push("Reconciliation mismatch");
    return {
      status: "DEGRADED",
      label: "DEGRADED",
      tone: "warn",
      blocker: reasons.join(" · "),
    };
  }
  return {
    status: "OPERATIONAL",
    label: "OPERATIONAL",
    tone: "ok",
  };
}

export const INITIAL_OWNER_PAPER_SESSIONS: OwnerPaperSessionRow[] = [];

const OWNER_BACKTESTS_KEY = STORAGE_KEYS.OWNER_BACKTESTS;
const OWNER_PAPER_SESSIONS_KEY = STORAGE_KEYS.OWNER_PAPER_SESSIONS;

export function getStoredOwnerBacktests(): OwnerBacktestRunRow[] {
  try {
    const raw = localStorage.getItem(OWNER_BACKTESTS_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed;
    return [];
  } catch {
    return [];
  }
}

export function saveOwnerBacktests(runs: OwnerBacktestRunRow[]): void {
  try {
    localStorage.setItem(OWNER_BACKTESTS_KEY, JSON.stringify(runs));
  } catch (err) {
    console.error("Failed to save backtests", err);
  }
}

export function getStoredOwnerPaperSessions(): OwnerPaperSessionRow[] {
  try {
    const raw = localStorage.getItem(OWNER_PAPER_SESSIONS_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed;
    return [];
  } catch {
    return [];
  }
}

export function saveOwnerPaperSessions(sessions: OwnerPaperSessionRow[]): void {
  try {
    localStorage.setItem(OWNER_PAPER_SESSIONS_KEY, JSON.stringify(sessions));
  } catch (err) {
    console.error("Failed to save paper sessions", err);
  }
}

export function updatePaperSessionHold(
  sessionId: string,
  allowance: OwnerAllowanceStatus,
  reason?: string,
  actor: string = "OWNER-001"
): { success: boolean; message: string } {
  const current = getStoredOwnerPaperSessions();
  const index = current.findIndex((s) => s.id === sessionId || s.sessionId === sessionId);
  if (index === -1) return { success: false, message: "Paper session not found" };

  const ses = { ...current[index] };
  ses.ownerAllowance = allowance;
  if (allowance === "HOLD") {
    ses.ownerHoldReason = reason || `Placed on hold by ${actor}`;
  } else {
    delete ses.ownerHoldReason;
  }

  const effective = computePaperEffectiveStatus(
    ses.sessionState,
    ses.marketDataReadiness,
    ses.persistenceHealth,
    ses.reconciliationState,
    ses.ownerAllowance
  );

  ses.auditEvents = [
    {
      time: new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC",
      text: `Owner set allowance to ${allowance} by ${actor} (Session State preserved as ${ses.sessionState}; Effective Status: ${effective.label})`,
      actor,
      tone: allowance === "HOLD" ? "warn" : "ok",
    },
    ...ses.auditEvents,
  ];

  current[index] = ses;
  saveOwnerPaperSessions(current);
  return { success: true, message: `Paper session "${ses.sessionId}" Owner Allowance set to ${allowance}. (Effective Status: ${effective.label})` };
}
