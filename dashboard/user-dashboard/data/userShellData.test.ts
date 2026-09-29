import { describe, expect, it } from "vitest";
import {
  deriveBrokerState,
  deriveDeploymentShell,
  loadUserShellAuthority,
} from "./userShellData";

describe("shared user shell authority", () => {
  it("does not guess a mode when active deployments disagree", () => {
    const result = deriveDeploymentShell([
      { deploymentId: "d1", strategyId: "s1", executionMode: "PAPER", status: "RUNNING" },
      { deploymentId: "d2", strategyId: "s2", executionMode: "LIVE", status: "RUNNING" },
    ] as any);

    expect(result.mode).toBe("UNKNOWN");
    expect(result.automationState).toBe("RUNNING");
  });

  it("prioritizes HALTED and keeps manual recovery truth ahead of RUNNING", () => {
    const result = deriveDeploymentShell([
      { deploymentId: "d1", strategyId: "s1", executionMode: "PAPER", status: "RUNNING" },
      { deploymentId: "d2", strategyId: "s2", executionMode: "PAPER", status: "HALTED" },
    ] as any);

    expect(result.mode).toBe("PAPER");
    expect(result.automationState).toBe("HALTED");
  });

  it("maps broker evidence without treating configuration as connectivity", () => {
    expect(deriveBrokerState("AVAILABLE", [] as any)).toBe("DISCONNECTED");
    expect(deriveBrokerState("UNAVAILABLE", [] as any)).toBe("UNAVAILABLE");
    expect(deriveBrokerState("AVAILABLE", [
      { status: "CONNECTED", healthState: "HEALTHY", suspended: false },
    ] as any)).toBe("CONNECTED");
    expect(deriveBrokerState("AVAILABLE", [
      { status: "CONNECTED", healthState: "DEGRADED", suspended: true },
    ] as any)).toBe("NEEDS_ATTENTION");
  });

  it("derives attention notices only from authoritative failures/states", async () => {
    const backend = <T,>(data: T) => ({ data, source: "BACKEND" as const, trust: "FRESH" as const, asOf: "2026-09-29T06:00:00Z", isFallback: false });
    const result = await loadUserShellAuthority({
      persistenceQuery: async () => ({ ...backend({}), trust: "STALE" as const }) as any,
      marketQuery: async ({ instrument }: any) => ({
        state: instrument === "NIFTY" ? "STALE" : "AVAILABLE",
        instrument,
        timeframe: "5m",
        mode: "LIVE",
        candles: [{ time: "09:20", open: 1, high: 2, low: 1, close: 2 }],
      }) as any,
      connectionsQuery: async () => backend([{ status: "CONNECTED", healthState: "DEGRADED", suspended: false }]) as any,
      deploymentsQuery: async () => backend([{ deploymentId: "d1", strategyId: "s1", executionMode: "PAPER", status: "READY_FOR_RESUME" }]) as any,
      liveReadinessQuery: async () => ({
        risk_state: "BLOCKED",
        connection_state: "CONNECTED",
        execution_policy: { arming_state: "READ_ONLY", mutation_allowed: false, global_hold: true, safe_mode: true },
        reconciliation: { state: "CLEAN", differences: [] },
      }) as any,
    });

    expect(result.status.mode).toBe("PAPER");
    expect(result.status.automationState).toBe("READY_FOR_RESUME");
    expect(result.status.manualResumeRequired).toBe(true);
    expect(result.status.engineState).toBe("STALE");
    expect(result.status.dataFreshness).toBe("STALE");
    expect(result.status.brokerState).toBe("NEEDS_ATTENTION");
    expect(result.notifications.some((item) => item.priority === "Action Required" && item.title.includes("resume"))).toBe(true);
    expect(result.notifications.some((item) => item.title.includes("Market data"))).toBe(true);
    expect(result.risk.level).toBe("BLOCKED");
  });
});
