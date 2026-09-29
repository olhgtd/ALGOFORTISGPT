import { describe, expect, it } from "vitest";
import { parseUserMarketChartPayload } from "./userMarketAuthority";

describe("user market canonical authority parser", () => {
  it("preserves STALE canonical candles rather than promoting or dropping them", () => {
    const result = parseUserMarketChartPayload({
      instrument: "NIFTY",
      timeframe: "5m",
      candles: {
        state: "STALE",
        value: [{ time: "09:20", open: 22000, high: 22100, low: 21950, close: 22080 }],
      },
    }, { instrument: "NIFTY", timeframe: "5m", mode: "LIVE" });

    expect(result.state).toBe("STALE");
    expect(result.candles).toHaveLength(1);
    expect(result.candles[0].close).toBe(22080);
  });

  it("fails closed on missing or invalid candle authority", () => {
    expect(parseUserMarketChartPayload({ candles: { state: "DATA_INVALID", value: [] } }, {
      instrument: "NIFTY", timeframe: "5m", mode: "LIVE",
    }).state).toBe("NO_DATA");
  });

  it("does not turn an unknown backend state into AVAILABLE", () => {
    const result = parseUserMarketChartPayload({ candles: { state: "MYSTERY", value: [{ close: 1 }] } }, {
      instrument: "NIFTY", timeframe: "5m", mode: "LIVE",
    });
    expect(result.state).toBe("ERROR");
    expect(result.candles).toEqual([]);
  });
});
