/**
 * AlgoFortis Dashboard V3 — Portfolio, Positions, Orders & Live Oversight Domain
 */
import type { Truth } from "../../shared/data/sharedTypes";
import { STORAGE_KEYS, safeGetJson, safeSetJson } from "../../shared/data/storage";

export interface OrderRow {
  id: string;
  instrument: string;
  side: "BUY" | "SELL TO CLOSE";
  qty: number;
  price: string;
  status: string;
  time: string;
  mode: string;
  pnl?: string;
  isProfit?: boolean;
  orderType?: "LIMIT" | "MARKET" | "SL-M";
  source?: string;
  triggerPrice?: string;
}

export const ORDERS: OrderRow[] = [];




export type LiveOrderStatus =
  | "PENDING" | "ACCEPTED" | "OPEN" | "PARTIALLY FILLED"
  | "FILLED" | "CANCELLED" | "REJECTED" | "EXPIRED";

export type LiveOrderSide = "BUY" | "SELL TO CLOSE";

export interface LiveLifecycleEvent {
  time: string;
  label: string;
  tone: "ok" | "warn" | "neg" | "dim";
}

export interface LiveOrderRow {
  id: string;
  instrument: string;
  underlying: "NIFTY" | "BANKNIFTY";
  optionType: "CE" | "PE";
  side: LiveOrderSide;
  qty: number;
  price: string;                    // requested price
  fillPrice?: string;               // actual fill price (FILLED / partial)
  filledQty?: number;
  status: LiveOrderStatus;
  orderType: "LIMIT" | "MARKET" | "SL-M";
  createdAt: string;
  updatedAt: string;
  source: string;                   // governed strategy / risk / protective context
  strategyName?: string;
  strategyVersion?: string;
  avgEntryPrice?: string;           // position entry context (closing orders only)
  rejectReason?: string;
  cancelReason?: string;
  riskDecision: string;
  contractContext: string;
  lifecycle: LiveLifecycleEvent[];
}

/** Realized P&L is only meaningful for a FILLED SELL TO CLOSE round trip:
    (Exit Price − Average Entry Price) × Closed Qty. Returns null otherwise ("—"). */
export const liveOrderRealizedPnl = (o: LiveOrderRow): number | null => {
  if (o.side !== "SELL TO CLOSE" || o.status !== "FILLED") return null;
  if (!o.avgEntryPrice || !o.fillPrice) return null;
  const entry = parseFloat(o.avgEntryPrice);
  const exit = parseFloat(o.fillPrice);
  const qty = o.filledQty ?? o.qty;
  if (Number.isNaN(entry) || Number.isNaN(exit) || !qty) return null;
  return Number(((exit - entry) * qty).toFixed(2));
};

const LC = {
  filled: (t0: string): LiveLifecycleEvent[] => [
    { time: t0, label: "Signal Generated", tone: "dim" as const },
    { time: t0, label: "Risk Gate Passed", tone: "ok" as const },
    { time: t0, label: "Contract Resolved", tone: "dim" as const },
    { time: t0, label: "Order Created", tone: "dim" as const },
    { time: t0, label: "Accepted", tone: "ok" as const },
    { time: t0, label: "Filled", tone: "ok" as const },
    { time: t0, label: "Position Updated", tone: "dim" as const },
  ],
  working: (t0: string, tail: LiveLifecycleEvent): LiveLifecycleEvent[] => [
    { time: t0, label: "Signal Generated", tone: "dim" as const },
    { time: t0, label: "Risk Gate Passed", tone: "ok" as const },
    { time: t0, label: "Contract Resolved", tone: "dim" as const },
    { time: t0, label: "Order Created", tone: "dim" as const },
    tail,
  ],
  rejected: (t0: string): LiveLifecycleEvent[] => [
    { time: t0, label: "Signal Generated", tone: "dim" as const },
    { time: t0, label: "Risk Gate REJECTED", tone: "neg" as const },
    { time: t0, label: "Order Creation BLOCKED", tone: "neg" as const },
  ],
};

export const LIVE_ORDERS: LiveOrderRow[] = [];

export interface LivePosition {
  id: string;
  contract: string;
  underlying: "NIFTY" | "BANKNIFTY";
  optionType: "CE" | "PE";
  qty: number;
  avgEntry: number;
  ltp: number;
  currentValue: number;
  unrealizedPnl: number;
  returnPct: number;
  strategy: string;
  entryTime: string;
  status: "MONITORING" | "TRAILING" | "EXIT_PENDING";
  stopLoss: number;
  target: number;
  trailStop: number;
  entrySpot: number;
  entryAtm: number;
  strikeInterval: number;
}

export interface LiveClosedPosition {
  id: string;
  contract: string;
  underlying: "NIFTY" | "BANKNIFTY";
  optionType: "CE" | "PE";
  strategy: string;
  entryPrice: number;
  exitPrice: number;
  qty: number;
  realizedPnl: number;
  returnPct: number;
  openedAt: string;
  closedAt: string;
  exitReason: "TARGET_REACHED" | "STOP_LOSS_TRIGGERED" | "TRAIL_STOP_EXIT" | "SQUAREOFF_TIME_LIMIT";
}

export interface StrategyAttributionRow {
  strategyName: string;
  version: string;
  activePositionsCount: number;
  capitalCommitted: number;
  unrealizedPnl: number;
  realizedPnl: number;
  totalPnl: number;
  winRatePct: number;
  status: "LIVE_READINESS" | "PAPER";
}

export const LIVE_POSITIONS: LivePosition[] = [];

export const LIVE_CLOSED_POSITIONS: LiveClosedPosition[] = [];

export interface PortfolioHolding {
  id: string;
  symbol: string;
  name: string;
  category: "OPTIONS";
  qty: number;
  avgCost: number;
  ltp: number;
  curValue: number;
  pnl: number;
  pnlPct: number;
  allocationPct: number;
}

export const PORTFOLIO_HOLDINGS: PortfolioHolding[] = [];
