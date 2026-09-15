/**
 * SentinelX Dashboard V3 — Shared Cross-Workspace Domain Types & Fixtures
 */

export type Truth = "REAL" | "SAMPLE" | "DISABLED";
export type ConnectorStatus = "CONNECTED" | "NEEDS_ATTENTION" | "OFFLINE" | "DISCONNECTED" | "UNVERIFIED";
export type DataFeed = "LIVE" | "DELAYED" | "NONE";
export type DataFreshnessState = "FRESH" | "STALE" | "UNKNOWN";

export interface Connector {
  id: string;
  name: string;
  short: string;
  provider: "Angel One" | "Zerodha" | "Dhan" | "Upstox" | "Other";
  apiSpec: string;
  status: ConnectorStatus;
  data: DataFeed;
  dataStatus: DataFreshnessState;
  asOf: string;
  latencyMs?: number;
  tradingPermission: "PAPER ENABLED" | "STANDBY" | "DISABLED" | "LIVE_LOCKED";
  accountAlias: string;
  environment: string;
  lastVerified: string;
  credentialsState: "SEALED" | "SECURELY_STORED";
  secretRef: string;
  issueNotice?: string;
  permissions: string[];
  uptimePct: number;
  feedDetails: {
    wsActive: boolean;
    tickFrequency: string;
    packetLoss: string;
  };
  events: { time: string; text: string; tone?: "ok" | "warn" | "neg" | "dim" }[];
}

export const USER_CONNECTORS: Connector[] = [];

export interface Portfolio { nav: number; dayPnl: number; dayPnlPct: number; weekPnlPct: number; curve: number[]; }
export const PORTFOLIO: Portfolio = {
  nav: 0, dayPnl: 0, dayPnlPct: 0, weekPnlPct: 0,
  curve: [0, 0, 0, 0, 0],
};


export type OptionMoneyness = "ITM" | "ATM" | "OTM";
export type GreeksAuthority = "DEV_SAMPLE_ESTIMATED" | "UNKNOWN_UNAVAILABLE" | "DEV_SAMPLE" | "ENGINE_DETERMINISTIC" | "MODEL_ESTIMATE";

export interface UnderlyingConfig {
  symbol: string;
  name: string;
  exchange: string;
  spot: number;
  change: number;
  changePct: number;
  step: number;
  expiries: string[];
  lotSize: number;
}

export const UNDERLYINGS: Record<string, UnderlyingConfig> = {
  NIFTY: {
    symbol: "NIFTY",
    name: "NIFTY 50",
    exchange: "NSE",
    spot: 22514.80,
    change: 124.60,
    changePct: 0.56,
    step: 50,
    expiries: ["03 SEP 2026", "10 SEP 2026", "24 SEP 2026", "29 OCT 2026"],
    lotSize: 25,
  },
  BANKNIFTY: {
    symbol: "BANKNIFTY",
    name: "NIFTY BANK",
    exchange: "NSE",
    spot: 51820.00,
    change: -182.30,
    changePct: -0.37,
    step: 100,
    expiries: ["03 SEP 2026", "10 SEP 2026", "24 SEP 2026", "29 OCT 2026"],
    lotSize: 15,
  },
  FINNIFTY: {
    symbol: "FINNIFTY",
    name: "NIFTY FIN SERVICE",
    exchange: "NSE",
    spot: 23140.10,
    change: 68.40,
    changePct: 0.30,
    step: 50,
    expiries: ["03 SEP 2026", "10 SEP 2026", "24 SEP 2026"],
    lotSize: 25,
  },
};

export interface ProCandle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export function generateCandles(
  basePrice: number,
  timeframe: string = "5m",
  count: number = 60,
  volatility: number = 0.004
): ProCandle[] {
  const candles: ProCandle[] = [];
  const now = new Date();
  let currentPrice = basePrice * (1 - count * 0.0008);

  const stepMinutes = timeframe === "1m" ? 1 : timeframe === "5m" ? 5 : timeframe === "15m" ? 15 : timeframe === "1h" ? 60 : 1440;

  for (let i = count - 1; i >= 0; i--) {
    const d = new Date(now.getTime() - i * stepMinutes * 60 * 1000);
    const timeStr = `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")} UTC`;

    const delta = (Math.sin(i * 0.3) * 0.6 + (Math.random() - 0.48)) * (basePrice * volatility);
    const open = Number(currentPrice.toFixed(2));
    const close = Number((open + delta).toFixed(2));
    const high = Number((Math.max(open, close) + Math.random() * (basePrice * volatility * 0.7)).toFixed(2));
    const low = Number((Math.min(open, close) - Math.random() * (basePrice * volatility * 0.7)).toFixed(2));
    const volume = Math.floor(25000 + Math.random() * 85000);

    candles.push({ time: timeStr, open, high, low, close, volume });
    currentPrice = close;
  }

  candles[candles.length - 1].close = basePrice;
  return candles;
}

export interface ActivityItem {
  id: string;
  time: string;
  text: string;
  actor?: string;
  tone?: "ok" | "warn" | "neg" | "dim";
  pnl?: string;
  isProfit?: boolean;
}

export const ACTIVITY: ActivityItem[] = [
  { id: "act-1", time: "14:02:18", text: "Order ord-live-0982 filled for NIFTY 22550 CE at ₹184.20", actor: "Alexander Vance", tone: "ok", pnl: "+₹1,450.00", isProfit: true },
  { id: "act-2", time: "14:01:45", text: "Closed position cpos-01 hit take-profit (+₹2,775.00)", actor: "Alexander Vance", tone: "ok", pnl: "+₹2,775.00", isProfit: true },
  { id: "act-3", time: "13:58:12", text: "Pre-trade risk blocked order ord-live-0980 (Capital limit reached)", actor: "Risk Engine", tone: "neg" },
  { id: "act-4", time: "13:45:00", text: "Angel One WebSocket Level-2 feed nominal (14ms latency)", actor: "Market Data Gateway", tone: "dim" },
  { id: "act-5", time: "11:30:10", text: "Strategy 'NIFTY Momentum v2.3' signaled wing buy", actor: "Alexander Vance", tone: "ok", pnl: "+₹1,120.00", isProfit: true },
];

export interface BacktestRun {
  id: string;
  name?: string;
  strategyName: string;
  underlying: string;
  range?: string;
  dateRange: string;
  trades: number;
  winRate: number;
  sharpe?: number;
  sharpeRatio: number;
  returnPct?: number;
  netProfitPct: number;
  maxDrawdown: string | number;
  profitFactor: number;
  status: "COMPLETED" | "RUNNING" | "FAILED";
  runDate?: string;
}

export const BACKTEST_RUNS: BacktestRun[] = [];

export const EQUITY_CURVE_SAMPLE: number[] = [];

export interface PaperPosition {
  id: string;
  symbol: string;
  type: "CE" | "PE" | string;
  qty: number;
  avgPrice: number;
  resolvedContract: string;
  strategySource: string;
  entrySpot: number;
  entryAtm: number;
  strikeInterval: number;
  policyMode: string;
  policyDistance: number;
  stopLoss?: number | null;
  target?: number | null;
  trailStop?: number | null;
  entryReason: string;
  pnl: number;
  isProfit?: boolean;
  contract?: string;
  underlying?: string;
  avgEntry?: number;
  ltp: number;
  currentValue?: number;
  unrealizedPnl?: number;
  returnPct?: number;
  entryTime?: string;
  strategy?: string;
}

export const PAPER_POSITIONS: PaperPosition[] = [];

export interface ReportItem {
  id: string;
  title: string;
  category: string;
  format: string;
  fileSize: string;
  evidenceScope: string;
  dataSourceScope: string;
  status: "GENERATED" | "PENDING" | "READY" | "PROCESSING" | "FAILED";
  name?: string;
  type?: string;
  period?: string;
  generatedAt?: string;
  size?: string;
  truth?: Truth;
}

export const REPORTS_LIST: ReportItem[] = [];
