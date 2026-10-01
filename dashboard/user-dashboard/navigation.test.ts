import { describe, expect, it } from "vitest";
import { USER_NAV_ITEMS } from "./navigation";

describe("final normal-user navigation", () => {
  it("renders exactly the approved seven destinations in order", () => {
    expect(USER_NAV_ITEMS.map(({ id, label }) => [id, label])).toEqual([
      ["home", "Home"],
      ["markets", "Markets"],
      ["strategies", "Strategies"],
      ["testing", "Testing & Validation"],
      ["trades", "Trades"],
      ["portfolio", "Portfolio"],
      ["account", "Account"],
    ]);
  });

  it("keeps old and internal destinations out of normal user navigation", () => {
    const ids = new Set(USER_NAV_ITEMS.map((item) => item.id));
    for (const forbidden of [
      "connections",
      "trading",
      "backtest",
      "paper",
      "orders",
      "reports",
      "security",
      "help",
      "agents",
      "control",
      "users",
    ]) {
      expect(ids.has(forbidden as never)).toBe(false);
    }
  });
});
