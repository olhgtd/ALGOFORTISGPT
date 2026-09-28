import { queryMarketChart } from "../../shared/services/integrationClient";
import { deriveMarketSnapshot, MARKET_INSTRUMENTS, type MarketInstrumentId, type MarketSnapshotModel } from "./marketsModel";

type MarketQuery = typeof queryMarketChart;

export type MarketsOverview = Record<MarketInstrumentId, MarketSnapshotModel>;

export async function loadMarketsOverview(query: MarketQuery = queryMarketChart): Promise<MarketsOverview> {
  const entries = await Promise.all(MARKET_INSTRUMENTS.map(async ({ id }) => {
    try {
      const result = await query({ instrument: id, timeframe: "5m", mode: "LIVE", limit: 2 });
      return [id, deriveMarketSnapshot(result.state, result.candles)] as const;
    } catch {
      return [id, deriveMarketSnapshot("BACKEND_UNAVAILABLE", [])] as const;
    }
  }));

  return Object.fromEntries(entries) as MarketsOverview;
}
