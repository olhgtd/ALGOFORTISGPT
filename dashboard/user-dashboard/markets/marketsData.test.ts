import { describe, expect, it } from "vitest";
import { loadMarketsOverview } from "./marketsData";

const candle = (time: string, close: number) => ({
  time,
  open: close - 10,
  high: close + 20,
  low: close - 30,
  close,
  volume: 1000,
});

describe("marketsData", () => {
  it("loads only canonical NIFTY and BANKNIFTY market reads", async () => {
    const calls: string[] = [];
    const query = async (params: { instrument: string; timeframe: string; mode: "LIVE" | "FROZEN_HISTORICAL" | "BACKTEST"; limit?: number }) => {
      calls.push(`${params.instrument}:${params.timeframe}:${params.mode}:${params.limit}`);
      if (params.instrument === "NIFTY") {
        return {
          state: "AVAILABLE" as const,
          instrument: "NIFTY",
          timeframe: "5m",
          mode: "LIVE" as const,
          candles: [candle("09:20", 22000), candle("09:25", 22040)],
        };
      }
      return {
        state: "BACKEND_UNAVAILABLE" as const,
        instrument: "BANKNIFTY",
        timeframe: "5m",
        mode: "LIVE" as const,
        candles: [],
      };
    };

    const result = await loadMarketsOverview(query);

    expect(calls).toEqual([
      "NIFTY:5m:LIVE:2",
      "BANKNIFTY:5m:LIVE:2",
    ]);
    expect(result.NIFTY.price).toBe(22040);
    expect(result.NIFTY.change).toBe(40);
    expect(result.BANKNIFTY.state).toBe("BACKEND_UNAVAILABLE");
    expect(result.BANKNIFTY.price).toBeNull();
  });

  it("fails closed per instrument when a request rejects", async () => {
    const query = async (params: { instrument: string; timeframe: string; mode: "LIVE" | "FROZEN_HISTORICAL" | "BACKTEST"; limit?: number }) => {
      if (params.instrument === "BANKNIFTY") throw new Error("offline");
      return {
        state: "NO_DATA" as const,
        instrument: params.instrument,
        timeframe: params.timeframe,
        mode: params.mode,
        candles: [],
      };
    };

    const result = await loadMarketsOverview(query);
    expect(result.NIFTY.state).toBe("NO_DATA");
    expect(result.BANKNIFTY.state).toBe("BACKEND_UNAVAILABLE");
  });
});
