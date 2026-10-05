import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const client = readFileSync(resolve(here, "safetyOps.ts"), "utf8");
const screen = readFileSync(resolve(here, "RiskSafetyScreen.tsx"), "utf8");

describe("Owner Risk & Safety", () => {
  it("renders explicit disarmed/unavailable truth", () => {
    expect(screen).toContain("READ_ONLY/DISARMED");
    expect(screen).toContain("NOT_CONNECTED");
    expect(screen).toContain("UNAVAILABLE");
    expect(screen).not.toContain("ARMED & READY");
  });
  it("offers safety increasing controls and protected hold release only", () => {
    expect(client).toContain("engageSafeMode");
    expect(client).toContain("engageGlobalHold");
    expect(client).toContain('actionFamily: "SAFETY_RELEASE"');
    expect(client).not.toContain("disableKillSwitch");
  });
});
