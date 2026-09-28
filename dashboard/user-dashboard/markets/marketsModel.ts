export type MarketsAuthorityState =
  | "LOADING"
  | "AVAILABLE"
  | "NO_DATA"
  | "DATA_PROVIDER_NOT_CONFIGURED"
  | "BACKEND_UNAVAILABLE"
  | "ERROR";

export interface MarketCandleLike {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface MarketSnapshotModel {
  state: MarketsAuthorityState;
  price: number | null;
  change: number | null;
  changePct: number | null;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
  asOf: string | null;
}

const emptySnapshot = (state: MarketsAuthorityState): MarketSnapshotModel => ({
  state,
  price: null,
  change: null,
  changePct: null,
  open: null,
  high: null,
  low: null,
  volume: null,
  asOf: null,
});

const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

export function deriveMarketSnapshot(
  state: MarketsAuthorityState,
  candles: readonly MarketCandleLike[],
): MarketSnapshotModel {
  if (state !== "AVAILABLE" || candles.length === 0) return emptySnapshot(state);

  const latest = candles[candles.length - 1];
  if (![latest.open, latest.high, latest.low, latest.close].every(finite)) {
    return emptySnapshot("ERROR");
  }

  const previous = candles.length > 1 ? candles[candles.length - 2] : null;
  const previousClose = previous && finite(previous.close) ? previous.close : null;
  const change = previousClose === null ? null : latest.close - previousClose;
  const changePct = previousClose === null || previousClose === 0
    ? null
    : (change! / previousClose) * 100;

  return {
    state: "AVAILABLE",
    price: latest.close,
    change,
    changePct,
    open: latest.open,
    high: latest.high,
    low: latest.low,
    volume: finite(latest.volume) ? latest.volume : null,
    asOf: latest.time || null,
  };
}

export const MARKET_INSTRUMENTS = [
  { id: "NIFTY", label: "NIFTY 50", exchange: "NSE" },
  { id: "BANKNIFTY", label: "NIFTY BANK", exchange: "NSE" },
] as const;

export type MarketInstrumentId = (typeof MARKET_INSTRUMENTS)[number]["id"];

export const optionChainAuthority = {
  state: "UNAVAILABLE" as const,
  sampleFallbackAllowed: false as const,
  orderAuthority: false as const,
  detail: "Canonical option-chain authority is not attached. Generated or sample strikes are intentionally hidden.",
};

export function marketStateLabel(state: MarketsAuthorityState): string {
  switch (state) {
    case "AVAILABLE": return "AVAILABLE";
    case "LOADING": return "LOADING";
    case "NO_DATA": return "NO DATA";
    case "DATA_PROVIDER_NOT_CONFIGURED": return "PROVIDER NOT CONFIGURED";
    case "BACKEND_UNAVAILABLE": return "BACKEND UNAVAILABLE";
    case "ERROR": return "ERROR";
  }
}
