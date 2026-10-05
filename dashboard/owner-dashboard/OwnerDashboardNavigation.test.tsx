import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(resolve(here, "OwnerDashboardApp.tsx"), "utf8");

describe("canonical Owner control-center navigation", () => {
  it("uses the approved four navigation groups and canonical labels", () => {
    for (const group of ["CONTROL", "RESEARCH & OPERATIONS", "SAFETY & INTELLIGENCE", "SYSTEM"]) expect(source).toContain(`label: "${group}"`);
    for (const label of ["Overview", "Users & Access", "Strategies", "Connections & Data", "Backtests / Walk-Forward", "Paper Trading", "Deployments", "Portfolio & Orders", "Reports & Audit", "Risk & Safety", "AI Control Center", "Product Operations", "System Health", "Security Authority", "Security Incidents", "Settings"]) expect(source).toContain(`label: "${label}"`);
  });

  it("keeps one canonical Users & Access nav item while preserving legacy access-registry alias", () => {
    expect(source.match(/label: "Users & Access"/g)?.length).toBe(2); // desktop + mobile
    expect(source).toContain('"access-registry": "users"');
    expect(source).not.toContain('label: "Access Registry"');
    expect(source).not.toContain('label: "Users Oversight"');
  });

  it("keeps mobile More drawer parity with desktop routes", () => {
    expect(source).toContain("const moreItems = DESKTOP_OWNER_NAV_GROUPS");
    expect(source).toContain('aria-label="More Owner screens"');
    expect(source).toContain("ALL_SCREEN_IDS.includes");
  });
});
