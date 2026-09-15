/**
 * SentinelX Owner Dashboard — Portfolios, Positions, Live Orders & Reconciliation Oversight
 */
import type { Truth } from "../../shared/data/sharedTypes";
import type { OwnerAllowanceStatus } from "./strategies";
import { STORAGE_KEYS, prototypeFixtureStorage, safeGetJson, safeSetJson } from "../../shared/data/storage";

const localStorage = prototypeFixtureStorage;

export type PortfolioEnvironment = "LIVE / SAMPLE" | "PAPER";
export type PositionReconciliationStatus = "MATCH_HEALTHY" | "MISMATCH_DETECTED";

export interface OwnerPortfolioRow {
  id: string;
  portfolioId: string;
  accountRef: string;
  environment: PortfolioEnvironment;
  brokerConnection: string;
  currency: "INR";
  cash: number;
  reservedCapital: number;
  exposure: number;
  unrealizedPnl: string;
  realizedPnl: string;
  marginUtilizationPct: number;
  openPositionsCount: number;
  openOrdersCount: number;
  reconciliationState: "MATCH_HEALTHY" | "MISMATCH_DETECTED" | "RECONCILING";
  reconciliationDetails?: string;
  lastReconciliationAt: string;
  ownerAllowance: OwnerAllowanceStatus;
  ownerHoldReason?: string;
  effectiveOrderPermission: "OPERATIONAL" | "BLOCKED (OWNER HOLD)" | "BLOCKED (RECONCILIATION MISMATCH)";
  auditEvents: { time: string; text: string; actor: string; tone?: "ok" | "warn" | "neg" | "dim" }[];
}

export interface OwnerPositionRow {
  id: string;
  positionId: string;
  portfolioId: string;
  environment: PortfolioEnvironment;
  strategyId: string;
  strategyName: string;
  instrument: string;
  underlying: "NIFTY" | "BANKNIFTY" | "FINNIFTY" | "SENSEX";
  side: "LONG";
  quantity: number;
  avgEntryPrice: number;
  markPrice: number;
  unrealizedPnl: string;
  unrealizedPnlPct: number;
  protectivePolicyId: string;
  stopLossPrice: number;
  targetPrice?: number;
  trailState: string;
  positionState: "OPEN" | "CLOSING" | "CLOSED";
  reconciliationState: PositionReconciliationStatus;
  openedAt: string;
  updatedAt: string;
}

export type OrderIntentSide = "BUY" | "SELL TO CLOSE";
export type OrderIntentType = "LIMIT" | "MARKET" | "SL-M";
export type OrderRiskDecisionOutcome = "APPROVED" | "REJECTED" | "THROTTLED";
export type OrderRoutingState = "ACKNOWLEDGED" | "PENDING_BROKER" | "SUBMITTED" | "REJECTED_BY_BROKER";
export type OrderExecutionLifecycleState = "FILLED" | "PARTIALLY_FILLED" | "QUEUED" | "CANCELLED" | "REJECTED" | "EXPIRED";

export interface OwnerFillEvidence {
  fillId: string;
  orderId: string;
  quantity: number;
  price: number;
  timestamp: string;
  executionVenue: string;
  brokerRef: string;
  feesEstimated: string;
  reconciliationState: "MATCH_HEALTHY" | "MISMATCH_DETECTED";
}

export interface OwnerOrderRow {
  id: string;
  orderId: string;
  clientOrderId: string;
  portfolioId: string;
  environment: PortfolioEnvironment;
  strategyId: string;
  strategyName: string;
  strategyVersion: string;
  instrument: string;
  side: OrderIntentSide;
  orderType: OrderIntentType;
  requestedQty: number;
  requestedPrice: number;
  triggerPrice?: number;
  timeInForce: "DAY" | "IOC";
  riskOutcome: OrderRiskDecisionOutcome;
  riskReason?: string;
  riskCapitalAllocated: number;
  routingState: OrderRoutingState;
  brokerOrderId?: string;
  executionState: OrderExecutionLifecycleState;
  filledQty: number;
  avgFillPrice?: number;
  remainingQty: number;
  protectivePolicyId: string;
  ocoGroupId?: string;
  stopLossRef?: number;
  targetRef?: number;
  reconciliationState: "MATCH_HEALTHY" | "MISMATCH_DETECTED";
  createdAt: string;
  updatedAt: string;
  cancelRequested?: boolean;
  cancelRequestTimestamp?: string;
  fills: OwnerFillEvidence[];
  auditEvents: { time: string; text: string; actor: string; tone?: "ok" | "warn" | "neg" | "dim" }[];
}

export const INITIAL_OWNER_PORTFOLIOS: OwnerPortfolioRow[] = [];

export const INITIAL_OWNER_POSITIONS: OwnerPositionRow[] = [];

export const INITIAL_OWNER_ORDERS: OwnerOrderRow[] = [];

const OWNER_PORTFOLIOS_KEY = STORAGE_KEYS.OWNER_PORTFOLIOS;
const OWNER_POSITIONS_KEY = STORAGE_KEYS.OWNER_POSITIONS;
const OWNER_ORDERS_KEY = STORAGE_KEYS.OWNER_ORDERS;

export function getStoredOwnerPortfolios(): OwnerPortfolioRow[] {
  try {
    const raw = localStorage.getItem(OWNER_PORTFOLIOS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveOwnerPortfolios(ports: OwnerPortfolioRow[]): void {
  try {
    localStorage.setItem(OWNER_PORTFOLIOS_KEY, JSON.stringify(ports));
  } catch (err) {
    console.error("Failed to save portfolios", err);
  }
}

export function updatePortfolioHold(
  portfolioId: string,
  allowance: OwnerAllowanceStatus,
  reason?: string,
  actor: string = "OWNER-001"
): { success: boolean; message: string } {
  const current = getStoredOwnerPortfolios();
  const index = current.findIndex((p) => p.id === portfolioId || p.portfolioId === portfolioId);
  if (index === -1) return { success: false, message: "Portfolio not found" };

  const port = { ...current[index] };
  port.ownerAllowance = allowance;
  if (allowance === "HOLD") {
    port.ownerHoldReason = reason || `Placed on hold by ${actor}`;
    port.effectiveOrderPermission = "BLOCKED (OWNER HOLD)";
  } else {
    delete port.ownerHoldReason;
    port.effectiveOrderPermission = port.reconciliationState === "MISMATCH_DETECTED"
      ? "BLOCKED (RECONCILIATION MISMATCH)"
      : "OPERATIONAL";
  }

  port.auditEvents = [
    {
      time: new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC",
      text: `Owner set portfolio allowance to ${allowance} by ${actor} (Effective: ${port.effectiveOrderPermission})`,
      actor,
      tone: allowance === "HOLD" ? "warn" : "ok",
    },
    ...port.auditEvents,
  ];

  current[index] = port;
  saveOwnerPortfolios(current);
  return { success: true, message: `Portfolio "${port.portfolioId}" allowance set to ${allowance}. (Effective: ${port.effectiveOrderPermission})` };
}

export function getStoredOwnerPositions(): OwnerPositionRow[] {
  try {
    const raw = localStorage.getItem(OWNER_POSITIONS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveOwnerPositions(positions: OwnerPositionRow[]): void {
  try {
    localStorage.setItem(OWNER_POSITIONS_KEY, JSON.stringify(positions));
  } catch (err) {
    console.error("Failed to save positions", err);
  }
}

export function getStoredOwnerOrders(): OwnerOrderRow[] {
  try {
    const raw = localStorage.getItem(OWNER_ORDERS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveOwnerOrders(orders: OwnerOrderRow[]): void {
  try {
    localStorage.setItem(OWNER_ORDERS_KEY, JSON.stringify(orders));
  } catch (err) {
    console.error("Failed to save orders", err);
  }
}

export function requestOrderCancelSimulated(
  orderId: string,
  actor: string = "OWNER-001"
): { success: boolean; message: string } {
  const current = getStoredOwnerOrders();
  const index = current.findIndex((o) => o.id === orderId || o.orderId === orderId);
  if (index === -1) return { success: false, message: "Order not found" };

  const ord = { ...current[index] };
  if (ord.executionState === "FILLED" || ord.executionState === "CANCELLED" || ord.executionState === "REJECTED") {
    return { success: false, message: `Cannot request cancel on order in terminal state (${ord.executionState})` };
  }

  ord.cancelRequested = true;
  ord.cancelRequestTimestamp = new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC";
  ord.auditEvents = [
    {
      time: ord.cancelRequestTimestamp,
      text: `SIMULATED CANCEL REQUEST registered by ${actor} · DEV PREVIEW (Awaiting broker execution authority; order state remains ${ord.executionState})`,
      actor,
      tone: "warn",
    },
    ...ord.auditEvents,
  ];

  current[index] = ord;
  saveOwnerOrders(current);
  return {
    success: true,
    message: `SIMULATED CANCEL REQUEST queued for "${ord.orderId}". (Order execution state remains ${ord.executionState} until authoritative broker acknowledgment)`,
  };
}
