import { deriveUserShellStatus, type AuthorityState, type AutomationState, type BrokerState, type TradingMode, type UserShellStatus } from "../shellState";

export interface HomeMarketInput {
  state: AuthorityState;
  price: number | null;
  asOf?: string | null;
  source?: string | null;
}

export interface HomePortfolioInput {
  state: AuthorityState;
  source?: string | null;
  accounts: Record<string, unknown>[] | null;
  positions: Record<string, unknown>[] | null;
  events: Record<string, unknown>[] | null;
}

export interface HomeStrategySummaryInput {
  state: AuthorityState;
  total: number | null;
  deployments: number | null;
  paperReady: number | null;
  liveReady: number | null;
}

export interface HomeTestingSummaryInput {
  state: AuthorityState;
  backtests: number | null;
  walkForward: number | null;
  reports: number | null;
  activeJobs: number | null;
}

export interface HomeRiskInput {
  state: AuthorityState;
  level: string | null;
  reasons: string[];
}

export interface HomeModelSources {
  profile?: { state: AuthorityState; displayName?: string | null; sxId?: string | null };
  shell?: { mode?: TradingMode; automationState?: AutomationState; brokerState?: BrokerState; engineState?: AuthorityState; dataFreshness?: AuthorityState };
  portfolio?: HomePortfolioInput;
  markets?: Partial<Record<"NIFTY" | "BANKNIFTY", HomeMarketInput>>;
  strategies?: HomeStrategySummaryInput;
  testing?: HomeTestingSummaryInput;
  risk?: HomeRiskInput;
}

export interface CapitalPoolSummary {
  id: string;
  strategy: string | null;
  executionMode: string | null;
  equity: number | null;
  availableFunds: number | null;
  usedCapital: number | null;
  realizedPnl: number | null;
  unrealizedPnl: number | null;
  source: string | null;
}

export interface PositionSummaryRow {
  id: string;
  sessionId: string | null;
  strategy: string | null;
  instrument: string | null;
  quantity: number | null;
  lots: number | null;
  pnl: number | null;
  status: string | null;
}

export interface HomeCommandCenterModel {
  profile: { state: AuthorityState; displayName: string | null; sxId: string | null };
  shell: UserShellStatus;
  markets: Array<{ symbol: "NIFTY" | "BANKNIFTY"; state: AuthorityState; price: number | null; asOf: string | null; source: string | null }>;
  capital: { state: AuthorityState; pools: CapitalPoolSummary[] | null; aggregate: null };
  positions: { state: AuthorityState; items: PositionSummaryRow[] | null };
  strategies: HomeStrategySummaryInput;
  risk: HomeRiskInput;
  testing: HomeTestingSummaryInput;
  recentActivity: { state: AuthorityState; items: Record<string, unknown>[] | null };
}

const numberOrNull = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;
const stringOrNull = (value: unknown): string | null =>
  typeof value === "string" && value.trim() ? value : null;

const mapPool = (row: Record<string, unknown>, source: string | null, index: number): CapitalPoolSummary => ({
  id: stringOrNull(row.session_id) ?? `pool-${index + 1}`,
  strategy: stringOrNull(row.strategy_name),
  executionMode: stringOrNull(row.execution_mode),
  equity: numberOrNull(row.current_equity),
  availableFunds: numberOrNull(row.available_cash),
  usedCapital: numberOrNull(row.used_capital),
  realizedPnl: numberOrNull(row.realized_pnl),
  unrealizedPnl: numberOrNull(row.unrealized_pnl),
  source,
});

const mapPosition = (row: Record<string, unknown>, index: number): PositionSummaryRow => ({
  id: stringOrNull(row.position_id) ?? stringOrNull(row.id) ?? `position-${index + 1}`,
  sessionId: stringOrNull(row.session_id),
  strategy: stringOrNull(row.strategy_name),
  instrument: stringOrNull(row.resolved_contract) ?? stringOrNull(row.instrument),
  quantity: numberOrNull(row.qty),
  lots: null,
  pnl: numberOrNull(row.unrealized_pnl) ?? numberOrNull(row.realized_pnl),
  status: stringOrNull(row.status),
});

const defaultStrategies = (): HomeStrategySummaryInput => ({
  state: "UNAVAILABLE",
  total: null,
  deployments: null,
  paperReady: null,
  liveReady: null,
});

const defaultTesting = (): HomeTestingSummaryInput => ({
  state: "UNAVAILABLE",
  backtests: null,
  walkForward: null,
  reports: null,
  activeJobs: null,
});

export const buildHomeCommandCenterModel = (sources: HomeModelSources): HomeCommandCenterModel => {
  const portfolio = sources.portfolio;
  const portfolioAvailable = portfolio?.state === "AVAILABLE";
  const markets = (["NIFTY", "BANKNIFTY"] as const).map((symbol) => {
    const input = sources.markets?.[symbol];
    if (!input) return { symbol, state: "UNAVAILABLE" as const, price: null, asOf: null, source: null };
    const carriesCanonicalValue = input.state === "AVAILABLE" || input.state === "STALE";
    return {
      symbol,
      state: input.state,
      price: carriesCanonicalValue ? input.price : null,
      asOf: input.asOf ?? null,
      source: input.source ?? null,
    };
  });

  return {
    profile: {
      state: sources.profile?.state ?? "UNAVAILABLE",
      displayName: sources.profile?.state === "AVAILABLE" ? sources.profile.displayName ?? null : null,
      sxId: sources.profile?.state === "AVAILABLE" ? sources.profile.sxId ?? null : null,
    },
    shell: deriveUserShellStatus({
      mode: sources.shell?.mode ?? "UNKNOWN",
      automationState: sources.shell?.automationState ?? "UNKNOWN",
      brokerState: sources.shell?.brokerState ?? "UNKNOWN",
      engineState: sources.shell?.engineState ?? "UNAVAILABLE",
      dataFreshness: sources.shell?.dataFreshness ?? "UNKNOWN",
    }),
    markets,
    capital: {
      state: portfolio?.state ?? "UNAVAILABLE",
      pools: portfolioAvailable && portfolio.accounts ? portfolio.accounts.map((row, index) => mapPool(row, portfolio.source ?? null, index)) : null,
      aggregate: null,
    },
    positions: {
      state: portfolio?.state ?? "UNAVAILABLE",
      items: portfolioAvailable && portfolio.positions ? portfolio.positions.map(mapPosition) : null,
    },
    strategies: sources.strategies ?? defaultStrategies(),
    risk: sources.risk ?? { state: "UNKNOWN", level: null, reasons: [] },
    testing: sources.testing ?? defaultTesting(),
    recentActivity: {
      state: portfolio?.state ?? "UNAVAILABLE",
      items: portfolioAvailable && portfolio.events ? portfolio.events : null,
    },
  };
};
