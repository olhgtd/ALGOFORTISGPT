import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const client = readFileSync(resolve(here, "deploymentOps.ts"), "utf8");
const screen = readFileSync(resolve(here, "DeploymentOperations.tsx"), "utf8");

describe("Owner deployment operations", () => {
  it("limits create to LIVE_PAPER and uses protected resume/stop", () => {
    expect(client).toContain('execution_mode: "LIVE_PAPER"');
    expect(client).not.toContain('execution_mode: "LIVE"');
    expect(client).toContain('actionFamily: "DEPLOYMENT_CONTROL"');
  });
  it("shows pause/resume/stop/recovery and unavailable states", () => {
    for (const label of ["Pause", "Resume", "Stop", "Recovery", "UNAVAILABLE"]) expect(screen).toContain(label);
  });
});
