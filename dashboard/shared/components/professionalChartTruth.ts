import type { MarketChartState, MarketCandle } from "../services/integrationClient";

export interface ProfessionalChartQuote {
  price: number | null;
  change: number | null;
  changePct: number | null;
}

const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

export function deriveProfessionalChartQuote(
  state: MarketChartState | "STALE",
  candles: readonly MarketCandle[],
): ProfessionalChartQuote {
  if ((state !== "AVAILABLE" && state !== "STALE") || candles.length === 0) {
    return { price: null, change: null, changePct: null };
  }

  const latest = candles[candles.length - 1];
  if (!finite(latest.close)) {
    return { price: null, change: null, changePct: null };
  }

  const previous = candles.length > 1 ? candles[candles.length - 2] : null;
  const previousClose = previous && finite(previous.close) ? previous.close : null;
  if (previousClose === null || previousClose === 0) {
    return { price: latest.close, change: null, changePct: null };
  }

  const change = latest.close - previousClose;
  return {
    price: latest.close,
    change,
    changePct: (change / previousClose) * 100,
  };
}
