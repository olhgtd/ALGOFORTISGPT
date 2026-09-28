import {
  queryCurrentUserProfile,
  queryMarketChart,
  queryOrdersPortfolio,
  queryPersistenceHealth,
} from "../../shared/services/integrationClient";
import type { AuthorityState } from "../shellState";
import { buildHomeCommandCenterModel, type HomeCommandCenterModel, type HomeMarketInput, type HomePortfolioInput } from "./homeModel";

type MarketChartResult = Awaited<ReturnType<typeof queryMarketChart>>;
type PersistenceResult = Awaited<ReturnType<typeof queryPersistenceHealth>>;

export const marketResultToInput = (result: MarketChartResult): HomeMarketInput => {
  if (result.state !== "AVAILABLE" || result.candles.length === 0) {
    return { state: "UNAVAILABLE", price: null, asOf: null, source: result.state };
  }
  const last = result.candles[result.candles.length - 1];
  return {
    state: "AVAILABLE",
    price: typeof last.close === "number" && Number.isFinite(last.close) ? last.close : null,
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

const marketFreshness = (markets: HomeMarketInput[]): AuthorityState => {
  const available = markets.filter((item) => item.state === "AVAILABLE").length;
  if (available === markets.length) return "AVAILABLE";
  if (available === 0) return "UNAVAILABLE";
  return "UNKNOWN";
};

export const loadHomeCommandCenterModel = async (): Promise<HomeCommandCenterModel> => {
  const [profileResult, persistenceResult, portfolioResult, niftyResult, bankNiftyResult] = await Promise.allSettled([
    queryCurrentUserProfile(),
    queryPersistenceHealth(),
    queryOrdersPortfolio(false, "PAPER"),
    queryMarketChart({ instrument: "NIFTY", timeframe: "5m", mode: "LIVE", limit: 2 }),
    queryMarketChart({ instrument: "BANKNIFTY", timeframe: "5m", mode: "LIVE", limit: 2 }),
  ] as const);

  const profile = profileResult.status === "fulfilled" && profileResult.value.source === "BACKEND"
    ? {
        state: "AVAILABLE" as const,
        displayName: profileResult.value.data.display_name ?? null,
        sxId: profileResult.value.data.sx_id ?? null,
      }
    : { state: "UNAVAILABLE" as const, displayName: null, sxId: null };

  const engineState = persistenceResult.status === "fulfilled"
    ? persistenceResultToEngineState(persistenceResult.value)
    : "UNAVAILABLE" as const;

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

  return buildHomeCommandCenterModel({
    profile,
    shell: {
      mode: "UNKNOWN",
      automationState: "UNKNOWN",
      brokerState: "UNKNOWN",
      engineState,
      dataFreshness: marketFreshness([nifty, bankNifty]),
    },
    portfolio,
    markets: { NIFTY: nifty, BANKNIFTY: bankNifty },
  });
};
