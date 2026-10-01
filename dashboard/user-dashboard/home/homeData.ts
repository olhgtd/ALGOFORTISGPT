import {
  queryCurrentUserProfile,
  queryOrdersPortfolio,
  queryPersistenceHealth,
} from "../../shared/services/integrationClient";
import { queryUserMarketChart } from "../data/userMarketAuthority";
import { loadStrategiesSurface, loadTestingSurface, type StrategiesSurfaceData, type TestingSurfaceData } from "../data/userSurfaceData";
import type { AuthorityState } from "../shellState";
import {
  buildHomeCommandCenterModel,
  type HomeCommandCenterModel,
  type HomeMarketInput,
  type HomePortfolioInput,
  type HomeStrategySummaryInput,
  type HomeTestingSummaryInput,
} from "./homeModel";

type MarketChartResult = Awaited<ReturnType<typeof queryUserMarketChart>>;
type PersistenceResult = Awaited<ReturnType<typeof queryPersistenceHealth>>;

export const marketResultToInput = (result: MarketChartResult): HomeMarketInput => {
  const carriesCanonicalCandles = result.state === "AVAILABLE" || result.state === "STALE";
  if (!carriesCanonicalCandles || result.candles.length === 0) {
    return { state: "UNAVAILABLE", price: null, asOf: null, source: result.state };
  }
  const last = result.candles[result.candles.length - 1];
  if (typeof last.close !== "number" || !Number.isFinite(last.close)) {
    return { state: "UNAVAILABLE", price: null, asOf: null, source: "INVALID_AVAILABLE_PAYLOAD" };
  }
  return {
    state: result.state === "STALE" ? "STALE" : "AVAILABLE",
    price: last.close,
    asOf: last.time ?? null,
    source: "CANONICAL_MARKET_SERVICE",
  };
};

export const persistenceResultToEngineState = (result: PersistenceResult): AuthorityState => {
  if (result.source !== "BACKEND") return "UNAVAILABLE";
  if (result.trust === "FRESH") return "AVAILABLE";
  if (result.trust === "STALE") return "STALE";
  return "UNKNOWN";
};

export const marketFreshness = (markets: HomeMarketInput[]): AuthorityState => {
  if (markets.length === 0) return "UNKNOWN";
  if (markets.every((item) => item.state === "AVAILABLE")) return "AVAILABLE";
  if (markets.some((item) => item.state === "STALE")) return "STALE";
  if (markets.every((item) => item.state === "UNAVAILABLE")) return "UNAVAILABLE";
  if (markets.some((item) => item.state === "UNKNOWN")) return "UNKNOWN";
  return "UNKNOWN";
};

export const strategiesToHomeSummary = (surface: StrategiesSurfaceData): HomeStrategySummaryInput => {
  if (surface.state !== "AVAILABLE") {
    return { state: surface.state, total: null, deployments: null, paperReady: null, liveReady: null };
  }
  const readinessComplete = surface.strategies.every((item) => item.readiness !== null);
  return {
    state: "AVAILABLE",
    total: surface.strategies.length,
    deployments: surface.deploymentsState === "AVAILABLE"
      ? surface.strategies.reduce((count, item) => count + item.deployments.length, 0)
      : null,
    paperReady: readinessComplete
      ? surface.strategies.filter((item) => item.readiness?.paper.ready === true).length
      : null,
    liveReady: readinessComplete
      ? surface.strategies.filter((item) => item.readiness?.live.ready === true).length
      : null,
  };
};

export const testingToHomeSummary = (surface: TestingSurfaceData): HomeTestingSummaryInput => {
  const states = [surface.backtests.state, surface.walkForward.state, surface.reports.state];
  const state: AuthorityState = states.every((value) => value === "AVAILABLE")
    ? "AVAILABLE"
    : states.some((value) => value === "STALE")
      ? "STALE"
      : states.some((value) => value === "UNKNOWN")
        ? "UNKNOWN"
        : states.every((value) => value === "UNAVAILABLE")
          ? "UNAVAILABLE"
          : "UNKNOWN";
  return {
    state,
    backtests: surface.backtests.state === "AVAILABLE" ? surface.backtests.data.length : null,
    walkForward: surface.walkForward.state === "AVAILABLE" ? surface.walkForward.data.length : null,
    reports: surface.reports.state === "AVAILABLE" ? surface.reports.data.length : null,
    activeJobs: surface.walkForward.state === "AVAILABLE"
      ? surface.walkForward.data.filter((job) => job.status === "PENDING" || job.status === "RUNNING").length
      : null,
  };
};

export const loadHomeCommandCenterModel = async (): Promise<HomeCommandCenterModel> => {
  const [profileResult, portfolioResult, niftyResult, bankNiftyResult, strategiesResult, testingResult] = await Promise.allSettled([
    queryCurrentUserProfile(),
    queryOrdersPortfolio(false, "PAPER"),
    queryUserMarketChart({ instrument: "NIFTY", timeframe: "5m", mode: "LIVE", limit: 2 }),
    queryUserMarketChart({ instrument: "BANKNIFTY", timeframe: "5m", mode: "LIVE", limit: 2 }),
    loadStrategiesSurface(),
    loadTestingSurface(),
  ] as const);

  const profileState: AuthorityState = profileResult.status !== "fulfilled" || profileResult.value.source !== "BACKEND"
    ? "UNAVAILABLE"
    : profileResult.value.trust === "FRESH"
      ? "AVAILABLE"
      : profileResult.value.trust === "STALE"
        ? "STALE"
        : "UNKNOWN";
  const profile = profileState === "AVAILABLE" && profileResult.status === "fulfilled"
    ? {
        state: "AVAILABLE" as const,
        displayName: profileResult.value.data.display_name ?? null,
        sxId: profileResult.value.data.sx_id ?? null,
      }
    : { state: profileState, displayName: null, sxId: null };

  const portfolio: HomePortfolioInput = portfolioResult.status === "fulfilled" && portfolioResult.value.availability === "AVAILABLE"
    ? {
        state: "AVAILABLE",
        source: portfolioResult.value.source,
        accounts: portfolioResult.value.accounts,
        positions: portfolioResult.value.positions,
        events: portfolioResult.value.events,
      }
    : { state: "UNAVAILABLE", source: null, accounts: null, positions: null, events: null };

  const nifty = niftyResult.status === "fulfilled"
    ? marketResultToInput(niftyResult.value)
    : { state: "UNAVAILABLE" as const, price: null, asOf: null, source: "REQUEST_FAILED" };
  const bankNifty = bankNiftyResult.status === "fulfilled"
    ? marketResultToInput(bankNiftyResult.value)
    : { state: "UNAVAILABLE" as const, price: null, asOf: null, source: "REQUEST_FAILED" };

  const strategies = strategiesResult.status === "fulfilled"
    ? strategiesToHomeSummary(strategiesResult.value)
    : { state: "UNAVAILABLE" as const, total: null, deployments: null, paperReady: null, liveReady: null };
  const testing = testingResult.status === "fulfilled"
    ? testingToHomeSummary(testingResult.value)
    : { state: "UNAVAILABLE" as const, backtests: null, walkForward: null, reports: null, activeJobs: null };

  return buildHomeCommandCenterModel({
    profile,
    strategies,
    testing,
    portfolio,
    markets: { NIFTY: nifty, BANKNIFTY: bankNifty },
  });
};