import { describe, expect, it } from "vitest";
import {
  marketResultToInput,
  persistenceResultToEngineState,
  strategiesToHomeSummary,
  testingToHomeSummary,
} from "./homeData";

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
    } as never)).toMatchObject({ state: "STALE", price: 22080, asOf: "09:20", source: "CANONICAL_MARKET_SERVICE" });
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

  it("summarizes strategy readiness only when every strategy has authoritative readiness", () => {
    expect(strategiesToHomeSummary({
      state: "AVAILABLE",
      deploymentsState: "AVAILABLE",
      asOf: "2026-09-29T06:00:00Z",
      strategies: [
        {
          entry: { strategy_id: "s1" } as never,
          readiness: { paper: { ready: true }, live: { ready: false } } as never,
          deployments: [{ deploymentId: "d1" } as never],
        },
        {
          entry: { strategy_id: "s2" } as never,
          readiness: null,
          deployments: [],
        },
      ],
    })).toEqual({ state: "AVAILABLE", total: 2, deployments: 1, paperReady: null, liveReady: null });
  });

  it("preserves stale strategy authority on Home without exposing stale counts", () => {
    expect(strategiesToHomeSummary({
      state: "STALE",
      deploymentsState: "UNKNOWN",
      asOf: "2026-09-29T06:00:00Z",
      strategies: [],
    })).toEqual({ state: "STALE", total: null, deployments: null, paperReady: null, liveReady: null });
  });

  it("keeps partially unavailable testing authority UNKNOWN instead of inventing PASS", () => {
    expect(testingToHomeSummary({
      backtests: { state: "AVAILABLE", data: [{ run_id: "r1" } as never], asOf: null },
      walkForward: { state: "UNAVAILABLE", data: [], asOf: null },
      reports: { state: "AVAILABLE", data: [{ id: "report1" } as never], asOf: null },
    })).toEqual({ state: "UNKNOWN", backtests: 1, walkForward: null, reports: 1, activeJobs: null });
  });

  it("preserves STALE testing authority instead of collapsing it to unavailable", () => {
    expect(testingToHomeSummary({
      backtests: { state: "STALE", data: [], asOf: null },
      walkForward: { state: "AVAILABLE", data: [], asOf: null },
      reports: { state: "AVAILABLE", data: [], asOf: null },
    })).toEqual({ state: "STALE", backtests: null, walkForward: 0, reports: 0, activeJobs: 0 });
  });
});
