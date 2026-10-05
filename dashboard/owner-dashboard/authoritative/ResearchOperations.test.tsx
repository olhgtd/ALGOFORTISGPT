import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const client = readFileSync(resolve(here, "researchOps.ts"), "utf8");
const screen = readFileSync(resolve(here, "ResearchOperations.tsx"), "utf8");
const shell = readFileSync(resolve(here, "..", "OwnerDashboardApp.tsx"), "utf8");

describe("Owner research operations", () => {
  it("uses Owner-wide reads and protected admin cancellation", () => {
    expect(client).toContain('/api/v1/owner/backtests?limit=200');
    expect(client).toContain('/api/v1/owner/walkforward/jobs?limit=200');
    expect(client).toContain('actionFamily: "BACKTEST_ADMIN"');
    expect(client).toContain('actionFamily: "WALKFORWARD_ADMIN"');
  });

  it("provides create, cancel, rejection and unavailable UX", () => {
    expect(screen).toContain("Run Backtest");
    expect(screen).toContain("Run Walk-Forward");
    expect(screen).toContain("Cancel");
    expect(screen).toContain("UNAVAILABLE");
    expect(screen).toContain("Action rejected");
  });

  it("is reachable from canonical Owner navigation", () => {
    expect(shell).toContain('{ id: "research", label: "Backtests / Walk-Forward"');
    expect(shell).toContain('case "research": return <ResearchOperations />;');
  });

  it("never exposes Live arm or broker-order mutation", () => {
    for (const forbidden of ["/api/v1/live/arm", "/api/v1/broker/orders", "/api/v1/orders/place", "/api/v1/orders/modify", "/api/v1/orders/cancel"]) {
      expect(client).not.toContain(forbidden);
      expect(screen).not.toContain(forbidden);
    }
  });
});
