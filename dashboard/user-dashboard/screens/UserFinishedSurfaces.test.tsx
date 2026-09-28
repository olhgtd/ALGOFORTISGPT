import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { UserStrategies } from "./UserStrategies";
import { UserTesting } from "./UserTesting";
import { UserTrades } from "./UserTrades";
import { UserPortfolio } from "./UserPortfolio";
import { UserAccount } from "./UserAccount";

let root: Root | null = null;
let container: HTMLDivElement | null = null;

afterEach(async () => {
  if (root) await act(async () => root?.unmount());
  container?.remove();
  root = null;
  container = null;
});

const mount = async (node: React.ReactNode) => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(node);
    await Promise.resolve();
    await Promise.resolve();
  });
  return container;
};

const unavailableStrategies = async () => ({ state: "UNAVAILABLE" as const, strategies: [], deploymentsState: "UNAVAILABLE" as const, asOf: null });
const unavailableTesting = async () => ({
  backtests: { state: "UNAVAILABLE" as const, data: [], asOf: null },
  walkForward: { state: "UNAVAILABLE" as const, data: [], asOf: null },
  reports: { state: "UNAVAILABLE" as const, data: [], asOf: null },
});
const unavailableTrading = async () => ({
  PAPER: { state: "UNAVAILABLE" as const, snapshot: null },
  LIVE: { state: "UNAVAILABLE" as const, snapshot: null },
});
const unavailableAccount = async () => ({
  profile: { state: "UNAVAILABLE" as const, data: null, asOf: null },
  connections: { state: "UNAVAILABLE" as const, data: [], asOf: null },
});

describe("finished normal-user surfaces", () => {
  it("renders Strategies as an explicit authority-safe surface", async () => {
    const node = await mount(<UserStrategies loadData={unavailableStrategies} />);
    expect(node.querySelector("[data-testid='strategies-surface']")).not.toBeNull();
    expect(node.textContent).toContain("Strategies");
    expect(node.textContent).toContain("UNAVAILABLE");
    expect(node.textContent).toContain("READ_ONLY / DISARMED");
    expect(node.textContent).not.toContain("pending-user-surface");
  });

  it("does not turn missing Testing authority into PASS or zero metrics", async () => {
    const node = await mount(<UserTesting loadData={unavailableTesting} />);
    expect(node.querySelector("[data-testid='testing-surface']")).not.toBeNull();
    expect(node.textContent).toContain("Testing & Validation");
    expect(node.textContent).toContain("UNAVAILABLE");
    expect(node.textContent).not.toContain("PASS");
    expect(node.textContent).not.toContain("0 runs");
  });

  it("keeps Trades unavailable rather than fabricating orders or positions", async () => {
    const node = await mount(<UserTrades loadData={unavailableTrading} />);
    expect(node.querySelector("[data-testid='trades-surface']")).not.toBeNull();
    expect(node.textContent).toContain("Trades");
    expect(node.textContent).toContain("READ_ONLY / DISARMED");
    expect(node.textContent).toContain("UNAVAILABLE");
  });

  it("keeps Portfolio capital pools separated by execution mode", async () => {
    const node = await mount(<UserPortfolio loadData={unavailableTrading} />);
    expect(node.querySelector("[data-testid='portfolio-surface']")).not.toBeNull();
    expect(node.textContent).toContain("Paper Capital");
    expect(node.textContent).toContain("Live Capital");
    expect(node.textContent).toContain("not combined");
  });

  it("renders Account without sample identity or credentials", async () => {
    const node = await mount(<UserAccount loadData={unavailableAccount} />);
    expect(node.querySelector("[data-testid='account-surface']")).not.toBeNull();
    expect(node.textContent).toContain("Account");
    expect(node.textContent).toContain("UNAVAILABLE");
    expect(node.textContent).not.toContain("Alexander Vance");
    expect(node.textContent).not.toContain("credentialRef");
  });
});
