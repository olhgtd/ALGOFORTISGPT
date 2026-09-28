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
    expect(model.testing).toEqual({ state: "UNAVAILABLE", items: null });
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
});
