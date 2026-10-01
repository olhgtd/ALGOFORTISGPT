import { describe, expect, it } from "vitest";
import { DESKTOP_OWNER_NAV_GROUPS, MOBILE_OWNER_NAV } from "./OwnerDashboardApp";


describe("owner Product Operations navigation", () => {
  it("adds Product Operations to owner desktop navigation without crowding the mobile primary dock", () => {
    const desktop = DESKTOP_OWNER_NAV_GROUPS.flatMap((group) => group.items);
    expect(desktop.some((item) => item.id === "product-operations" && item.label === "Product Operations")).toBe(true);
    expect(MOBILE_OWNER_NAV.some((item) => item.id === "product-operations")).toBe(false);
  });
});
