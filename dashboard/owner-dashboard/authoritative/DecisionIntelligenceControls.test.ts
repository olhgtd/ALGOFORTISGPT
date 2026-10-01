import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const source = readFileSync(
  fileURLToPath(new URL("./DecisionIntelligenceControls.tsx", import.meta.url)),
  "utf8",
);
const aiControl = readFileSync(
  fileURLToPath(new URL("./AIControlCenter.tsx", import.meta.url)),
  "utf8",
);

describe("Owner Decision Intelligence controls", () => {
  it("keeps all global configuration under the Owner/Admin namespace", () => {
    expect(source).toContain("/api/v1/owner/admin/ai/intelligence");
    expect(source).not.toContain("/api/v1/user/ai/");
  });

  it("exposes the locked control families in the existing AI Control Center", () => {
    expect(aiControl).toContain("DecisionIntelligenceControls");
    expect(source).toContain("MarketWatchPolicy");
    expect(source).toContain("Strategy Hunting");
    expect(source).toContain("Provider Queue / Budget");
    expect(source).toContain("User Intelligence Entitlements");
    expect(source).toContain("Scope Expansion Requests");
  });

  it("keeps the safety authorities visible", () => {
    expect(source).toContain("RiskGateV2");
    expect(source).toContain("READ_ONLY/DISARMED");
    expect(source).toContain("OD-V2-16");
  });
});
