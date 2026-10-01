import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const ownerAuthoritativeDir = resolve(
  process.cwd(),
  "..",
  "owner-dashboard",
  "authoritative",
);

const source = readFileSync(
  resolve(ownerAuthoritativeDir, "DecisionIntelligenceControls.tsx"),
  "utf8",
);
const aiControl = readFileSync(
  resolve(ownerAuthoritativeDir, "AIControlCenter.tsx"),
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
