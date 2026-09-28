import { describe, expect, it } from "vitest";
import {
  loadAccountSurface,
  loadStrategiesSurface,
  loadTestingSurface,
  loadTradingSurface,
} from "./userSurfaceData";

const unavailable = <T,>(data: T) => ({
  data,
  source: "UNAVAILABLE" as const,
  trust: "UNKNOWN" as const,
  asOf: "2026-09-28T00:00:00Z",
  isFallback: false,
});

const backend = <T,>(data: T) => ({
  data,
  source: "BACKEND" as const,
  trust: "FRESH" as const,
  asOf: "2026-09-28T00:00:00Z",
  isFallback: false,
});

describe("userSurfaceData", () => {
  it("never exposes a sample-fallback strategy registry as authoritative", async () => {
    const registry = async () => ({
      ...backend([{ strategy_id: "s1", version_id: "v1", stage: "PAPER", archived: false, source_sha256: "abc", protective_policy: "LOCKED" }]),
      source: "SAMPLE_FALLBACK" as const,
      isFallback: true,
    });
    const result = await loadStrategiesSurface(registry as any, async () => backend([]) as any, async () => null);
    expect(result.state).toBe("UNAVAILABLE");
    expect(result.strategies).toEqual([]);
  });

  it("joins backend strategy readiness and deployment state without inventing eligibility", async () => {
    const result = await loadStrategiesSurface(
      async () => backend([{ strategy_id: "s1", version_id: "v1", stage: "PAPER", archived: false, source_sha256: "abc", protective_policy: "LOCKED" }]) as any,
      async () => backend([{ deploymentId: "d1", strategyId: "s1", status: "PAUSED" }]) as any,
      async () => ({
        strategyId: "s1",
        backtest: { ready: true, code: "READY", reason: "Verified" },
        paper: { ready: true, code: "READY", reason: "Verified" },
        livePaper: { ready: false, code: "BLOCKED", reason: "Not promoted" },
        live: { ready: false, code: "DISARMED", reason: "Live disabled" },
      }),
    );
    expect(result.state).toBe("AVAILABLE");
    expect(result.strategies[0].readiness?.live.ready).toBe(false);
    expect(result.strategies[0].deployments[0].status).toBe("PAUSED");
  });

  it("keeps paper and live runtime authorities separate", async () => {
    const query = async (_owner: boolean, mode: "PAPER" | "BACKTEST" | "LIVE" | "SHADOW") => {
      if (mode === "LIVE") throw new Error("offline");
      return {
        execution_mode: mode,
        availability: "AVAILABLE" as const,
        source: "runtime",
        accounts: [], positions: [], orders: [], events: [], aggregate_exposure: null, limitations: [],
      };
    };
    const result = await loadTradingSurface(query as any);
    expect(result.PAPER.state).toBe("AVAILABLE");
    expect(result.LIVE.state).toBe("UNAVAILABLE");
  });

  it("accepts only backend testing authorities", async () => {
    const result = await loadTestingSurface(
      async () => backend([{ run_id: "r1" }]) as any,
      async () => unavailable([{ jobId: "wf1" }]) as any,
      async () => backend([{ id: "report1" }]) as any,
    );
    expect(result.backtests.state).toBe("AVAILABLE");
    expect(result.walkForward.state).toBe("UNAVAILABLE");
    expect(result.reports.state).toBe("AVAILABLE");
  });

  it("rejects sample profile data on Account", async () => {
    const profile = async () => ({
      data: { user_id: "sample", role: "USER", lifecycle: "ACTIVE", display_name: "Sample", namespace: "user" },
      source: "SAMPLE_FALLBACK" as const,
      trust: "UNKNOWN" as const,
      asOf: "2026-09-28T00:00:00Z",
      isFallback: true,
    });
    const result = await loadAccountSurface(profile as any, async () => unavailable([]) as any);
    expect(result.profile.state).toBe("UNAVAILABLE");
    expect(result.profile.data).toBeNull();
    expect(result.connections.state).toBe("UNAVAILABLE");
  });
});
