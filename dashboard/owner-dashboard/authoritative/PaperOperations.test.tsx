import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const client = readFileSync(resolve(here, "paperOps.ts"), "utf8");
const screen = readFileSync(resolve(here, "PaperOperations.tsx"), "utf8");
const shell = readFileSync(resolve(here, "..", "OwnerDashboardApp.tsx"), "utf8");

describe("Owner Paper operations", () => {
  it("splits safety-increasing HOLD from protected release", () => {
    expect(client).toContain('/hold`');
    expect(client).toContain('/release-hold`');
    expect(client).toContain('actionFamily: "PAPER_HOLD_RELEASE"');
  });

  it("shows create/start/stop/detail and fail-closed authority UX", () => {
    for (const label of ["Create Paper Session", "Start", "Stop", "HOLD", "Release HOLD", "Positions", "Orders", "Events", "UNAVAILABLE"]) {
      expect(screen).toContain(label);
    }
  });

  it("is canonical and contains no broker/live mutation", () => {
    expect(shell).toContain('case "paper": return <PaperOperations />;');
    for (const forbidden of ["/api/v1/live/arm", "/api/v1/broker/orders", "/api/v1/orders/place", "/api/v1/orders/modify", "/api/v1/orders/cancel"]) {
      expect(client).not.toContain(forbidden);
      expect(screen).not.toContain(forbidden);
    }
  });
});
