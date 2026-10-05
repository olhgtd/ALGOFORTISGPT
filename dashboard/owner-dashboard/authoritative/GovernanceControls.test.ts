import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const screens = readFileSync(resolve(here, "screens.tsx"), "utf8");
const mutations = readFileSync(resolve(here, "mutations.ts"), "utf8");

describe("Owner governance controls", () => {
  it("exposes strategy assignment through step-up wrappers", () => {
    expect(mutations).toContain("ownerStrategyAssignment");
    expect(mutations).toContain("revoke-assignment");
    expect(screens).toContain("Assign user");
    expect(screens).toContain("Revoke assignment");
  });

  it("exposes safe strategy visibility and paper-stage governance", () => {
    expect(screens).toContain("Publish");
    expect(screens).toContain("Owner private");
    expect(screens).toContain("Promote Paper");
    expect(screens).not.toContain("Arm Live");
  });

  it("exposes connection capability and full dataset governance", () => {
    expect(screens).toContain("Capability HOLD");
    expect(screens).toContain("Reject");
    expect(screens).toContain("Retire");
    expect(screens).toContain("Replace");
    expect(mutations).toContain("ownerDatasetRetire");
    expect(mutations).toContain("ownerDatasetReplace");
  });

  it("exposes supported service entitlement controls", () => {
    expect(screens).toContain("Renew 3 months");
    expect(screens).toContain("Lifetime");
  });
});
