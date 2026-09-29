import { describe, expect, it } from "vitest";
import { buildHomeCommandCenterModel } from "./homeModel";

describe("HomeCommandCenterModel truthfulness", () => {
  it("keeps unavailable portfolio and market authority null instead of inventing zero values", () => {
    const model = buildHomeCommandCenterModel({});
    expect(model.capital.state).toBe("UNAVAILABLE");
    expect(model.capital.pools).toBeNull();
    expect(model.positions.items).toBeNull();
    expect(model.markets.map((market) => market.price)).toEqual([null, null]);
    expect(model.risk).toEqual({ state: "UNKNOWN", level: null, reasons: [] });
    expect(model.strategies).toEqual({ state: "UNAVAILABLE", total: null, deployments: null, paperReady: null, liveReady: null });
    expect(model.testing).toEqual({ state: "UNAVAILABLE", backtests: null, walkForward: null, reports: null, activeJobs: null });
  });

  it("keeps separate account rows separate and never invents cross-pool aggregate capital", () => {
    const model = buildHomeCommandCenterModel({
      portfolio: {
        state: "AVAILABLE",
        source: "PERSISTED_PAPER_RUNTIME",
        accounts: [
          { session_id: "paper-a", strategy_name: "ORB A", current_equity: 1000, available_cash: 700 },
          { session_id: "paper-b", strategy_name: "ORB B", current_equity: 2000, available_cash: 1200 },
        ],
        positions: [],
        events: [],
      },
    });

    expect(model.capital.pools).toHaveLength(2);
    expect(model.capital.aggregate).toBeNull();
    expect(model.positions.state).toBe("AVAILABLE");
    expect(model.positions.items).toEqual([]);
  });

  it("does not let a connected broker imply that Live is armed", () => {
    const model = buildHomeCommandCenterModel({
      shell: { mode: "LIVE", automationState: "RECOVERY", brokerState: "CONNECTED" },
    });
    expect(model.shell.brokerState).toBe("CONNECTED");
    expect(model.shell.liveStateLabel).toBe("READ_ONLY / DISARMED");
    expect(model.shell.manualResumeRequired).toBe(true);
  });

  it("preserves stale canonical market values as stale rather than hiding or promoting them", () => {
    const model = buildHomeCommandCenterModel({
      markets: {
        NIFTY: { state: "STALE", price: 22080, asOf: "09:20", source: "CANONICAL_MARKET_SERVICE" },
      },
    });
    expect(model.markets[0]).toMatchObject({ state: "STALE", price: 22080, asOf: "09:20" });
  });

  it("carries authoritative strategy, testing, and risk summaries without deriving a PASS verdict", () => {
    const model = buildHomeCommandCenterModel({
      strategies: { state: "AVAILABLE", total: 3, deployments: 2, paperReady: 2, liveReady: 0 },
      testing: { state: "AVAILABLE", backtests: 7, walkForward: 2, reports: 4, activeJobs: 1 },
      risk: { state: "AVAILABLE", level: "BLOCKED", reasons: ["Global execution hold is active."] },
    });

    expect(model.strategies).toEqual({ state: "AVAILABLE", total: 3, deployments: 2, paperReady: 2, liveReady: 0 });
    expect(model.testing).toEqual({ state: "AVAILABLE", backtests: 7, walkForward: 2, reports: 4, activeJobs: 1 });
    expect(model.risk.level).toBe("BLOCKED");
  });
});
