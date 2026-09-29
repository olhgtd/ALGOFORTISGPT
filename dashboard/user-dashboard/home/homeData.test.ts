import { describe, expect, it } from "vitest";
import { marketResultToInput, persistenceResultToEngineState } from "./homeData";

describe("Home data fail-closed mappings", () => {
  it("does not invent a market price when canonical market data is missing", () => {
    expect(marketResultToInput({
      state: "NO_DATA",
      instrument: "NIFTY",
      timeframe: "5m",
      mode: "LIVE",
      candles: [],
    })).toMatchObject({ state: "UNAVAILABLE", price: null, source: "NO_DATA" });
  });

  it("uses the last canonical close only when chart authority reports AVAILABLE", () => {
    expect(marketResultToInput({
      state: "AVAILABLE",
      instrument: "BANKNIFTY",
      timeframe: "5m",
      mode: "LIVE",
      candles: [
        { time: "09:15", open: 50000, high: 50100, low: 49950, close: 50050 },
        { time: "09:20", open: 50050, high: 50200, low: 50020, close: 50180 },
      ],
    })).toMatchObject({ state: "AVAILABLE", price: 50180, asOf: "09:20" });
  });

  it("preserves STALE canonical market truth instead of collapsing it to unavailable", () => {
    expect(marketResultToInput({
      state: "STALE",
      instrument: "NIFTY",
      timeframe: "5m",
      mode: "LIVE",
      candles: [
        { time: "09:20", open: 22000, high: 22100, low: 21950, close: 22080 },
      ],
    })).toMatchObject({ state: "STALE", price: 22080, asOf: "09:20", source: "CANONICAL_MARKET_SERVICE" });
  });

  it("fails closed when an AVAILABLE chart payload has an invalid last close", () => {
    expect(marketResultToInput({
      state: "AVAILABLE",
      instrument: "NIFTY",
      timeframe: "5m",
      mode: "LIVE",
      candles: [
        { time: "09:20", open: 22000, high: 22100, low: 21950, close: Number.NaN },
      ],
    })).toMatchObject({ state: "UNAVAILABLE", price: null, source: "INVALID_AVAILABLE_PAYLOAD" });
  });

  it("rejects sample fallback health as authoritative engine health", () => {
    expect(persistenceResultToEngineState({ source: "SAMPLE_FALLBACK", trust: "UNKNOWN" } as never)).toBe("UNAVAILABLE");
    expect(persistenceResultToEngineState({ source: "BACKEND", trust: "STALE" } as never)).toBe("STALE");
    expect(persistenceResultToEngineState({ source: "BACKEND", trust: "FRESH" } as never)).toBe("AVAILABLE");
  });
});
