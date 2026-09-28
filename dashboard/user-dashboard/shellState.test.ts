import { describe, expect, it } from "vitest";
import { deriveUserShellStatus } from "./shellState";

describe("user shell safety-state presentation", () => {
  it("keeps Live READ_ONLY / DISARMED even when the broker is connected", () => {
    const status = deriveUserShellStatus({
      mode: "LIVE",
      automationState: "RUNNING",
      brokerState: "CONNECTED",
      engineState: "AVAILABLE",
      dataFreshness: "AVAILABLE",
    });

    expect(status.brokerState).toBe("CONNECTED");
    expect(status.liveStateLabel).toBe("READ_ONLY / DISARMED");
  });

  it.each(["RECOVERY", "READY_FOR_RESUME"] as const)("requires manual resume for %s", (automationState) => {
    const status = deriveUserShellStatus({
      mode: "PAPER",
      automationState,
      brokerState: "UNAVAILABLE",
      engineState: "UNAVAILABLE",
      dataFreshness: "UNKNOWN",
    });

    expect(status.manualResumeRequired).toBe(true);
    expect(status.automationState).not.toBe("RUNNING");
    expect(status.brokerState).toBe("UNAVAILABLE");
    expect(status.engineState).toBe("UNAVAILABLE");
    expect(status.dataFreshness).toBe("UNKNOWN");
  });

  it("preserves critical notification priority and count", () => {
    const status = deriveUserShellStatus({
      mode: "BACKTEST",
      automationState: "STOPPED",
      notifications: { critical: 3, actionRequired: 2, important: 1, info: 9 },
    });

    expect(status.criticalNotifications).toBe(3);
    expect(status.actionRequiredNotifications).toBe(2);
  });
});
