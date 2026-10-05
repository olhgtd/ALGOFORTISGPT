import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const client = readFileSync(resolve(here, "dataOps.ts"), "utf8");
const screen = readFileSync(resolve(here, "DataOperations.tsx"), "utf8");

describe("Owner data operations", () => {
  it("keeps provider credentials write-only", () => {
    expect(screen).toContain('type="password"');
    expect(screen).toContain("write-only");
    expect(screen).not.toContain("provider.api_key");
    expect(screen).not.toContain("provider.apiKey");
  });
  it("covers providers sync schedule jobs repair and datasets", () => {
    for (const label of ["Providers", "Manual Sync", "Schedule", "Sync Jobs", "Gap Repair", "Datasets", "Retire", "Replace", "UNAVAILABLE"]) expect(screen).toContain(label);
  });
  it("uses step-up for trust-changing provider/data policy", () => {
    expect(client).toContain('actionFamily: "HISTORICAL_PROVIDER_CONFIG"');
    expect(client).toContain('actionFamily: "HISTORICAL_SYNC_POLICY"');
    expect(client).toContain('actionFamily: "HISTORICAL_DATA_REPAIR"');
  });
});
