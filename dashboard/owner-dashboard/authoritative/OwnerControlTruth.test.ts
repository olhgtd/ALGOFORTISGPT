import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const ownerApi = readFileSync(resolve(here, "api.ts"), "utf8");
const ownerShell = readFileSync(resolve(here, "..", "OwnerDashboardApp.tsx"), "utf8");
const userShell = readFileSync(resolve(here, "..", "..", "user-dashboard", "UserDashboardApp.tsx"), "utf8");

describe("canonical Owner control-plane truth", () => {
  it("uses installation-wide Owner reads for backtests and paper sessions", () => {
    expect(ownerApi).toContain('ownerFetch<any>("/api/v1/owner/backtests?limit=200")');
    expect(ownerApi).toContain('ownerFetch<any>("/api/v1/owner/paper/sessions?limit=200")');
    expect(ownerApi).not.toContain('ownerFetch<any>("/api/v1/backtests?limit=200&offset=0")');
    expect(ownerApi).not.toContain('ownerFetch<any>("/api/v1/paper/sessions?limit=200&offset=0")');
  });

  it("keeps the hardcoded legacy kill-switch claim unreachable from the canonical User app", () => {
    expect(userShell).not.toContain("UserScreens");
    expect(userShell).not.toContain('from "./screens/UserScreens"');
  });

  it("keeps lifecycle governance on the reachable Users & Access surface", () => {
    const screens = readFileSync(resolve(here, "screens.tsx"), "utf8");
    for (const token of ["Suspend", "Restore", "Revoke", "Reissue", "Renew 3 months", "Lifetime"]) expect(screens).toContain(token);
  });

  it("keeps connection allowance governance on the reachable Connections & Data surface", () => {
    const dataOps = readFileSync(resolve(here, "DataOperations.tsx"), "utf8");
    for (const token of ["ownerConnectionAllowance", "ownerCapabilityAllowance", "ALLOWED", "HOLD", "REVOKED"]) expect(dataOps).toContain(token);
  });

  it("keeps canonical Owner navigation on authoritative modules", () => {
    expect(ownerShell).toContain('from "./authoritative/screens"');
    expect(ownerShell).not.toContain('/screens/');
    expect(ownerShell).not.toContain("sample" + "Data");
  });

  it("does not expose real Live or broker order mutation API paths", () => {
    for (const token of [
      "/api/v1/live/arm",
      "/api/v1/live/orders",
      "/api/v1/broker/orders",
      "/api/v1/orders/place",
      "/api/v1/orders/modify",
      "/api/v1/orders/cancel",
    ]) {
      expect(ownerApi).not.toContain(token);
    }
  });
});
