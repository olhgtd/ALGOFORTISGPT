import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UserTesting } from "./UserTesting";

let root: Root | null = null;
let container: HTMLDivElement | null = null;

afterEach(async () => {
  if (root) await act(async () => root?.unmount());
  container?.remove();
  root = null;
  container = null;
});

const available = (overrides: any = {}) => ({
  backtests: { state: "AVAILABLE" as const, data: [], asOf: "2026-10-05T18:00:00Z" },
  walkForward: { state: "AVAILABLE" as const, data: [], asOf: "2026-10-05T18:00:00Z" },
  reports: { state: "AVAILABLE" as const, data: [], asOf: "2026-10-05T18:00:00Z" },
  ...overrides,
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

const setInput = async (el: HTMLInputElement, value: string) => {
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  });
};

const click = async (el: Element) => {
  await act(async () => {
    (el as HTMLElement).click();
    await Promise.resolve();
    await Promise.resolve();
  });
};

describe("canonical Testing & Validation actions", () => {
  it("runs a backtest with exact canonical payload and refreshes authority", async () => {
    const loadData = vi.fn().mockResolvedValue(available());
    const executeBacktestAction = vi.fn().mockResolvedValue({ ok: true, data: { run_id: "bt-new", status: "PENDING" } });
    const node = await mount(<UserTesting
      loadData={loadData}
      executeBacktestAction={executeBacktestAction as any}
    />);

    await setInput(node.querySelector("input[aria-label='Backtest strategy ID']") as HTMLInputElement, "strat-1");
    await setInput(node.querySelector("input[aria-label='Backtest dataset ID']") as HTMLInputElement, "ds-1");
    await setInput(node.querySelector("input[aria-label='Backtest instrument']") as HTMLInputElement, "NIFTY");
    await setInput(node.querySelector("input[aria-label='Backtest timeframe']") as HTMLInputElement, "5m");
    await setInput(node.querySelector("input[aria-label='Backtest initial capital']") as HTMLInputElement, "500000");
    await setInput(node.querySelector("input[aria-label='Backtest date range']") as HTMLInputElement, "2026-01-05");

    const run = [...node.querySelectorAll("button")].find((button) => button.textContent === "Run Backtest");
    expect(run).toBeTruthy();
    await click(run!);

    expect(executeBacktestAction).toHaveBeenCalledTimes(1);
    expect(executeBacktestAction).toHaveBeenCalledWith({
      strategy_id: "strat-1",
      dataset_id: "ds-1",
      instrument: "NIFTY",
      timeframe: "5m",
      initial_capital: 500000,
      date_range: "2026-01-05",
    });
    expect(loadData.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(node.textContent).toContain("Backtest accepted");
  });

  it("keeps existing run evidence visible when backend rejects a backtest", async () => {
    const row = {
      run_id: "bt-existing", strategy_id: "strat-1", strategy_name: "ORB", version: "v1",
      instrument: "NIFTY", timeframe: "5m", status: "COMPLETED", total_trades: 12,
      net_profit: 5000, max_drawdown: 2.1,
    };
    const loadData = vi.fn().mockResolvedValue(available({
      backtests: { state: "AVAILABLE" as const, data: [row], asOf: "2026-10-05T18:00:00Z" },
    }));
    const executeBacktestAction = vi.fn().mockResolvedValue({ ok: false, error: "dataset not approved" });
    const node = await mount(<UserTesting loadData={loadData} executeBacktestAction={executeBacktestAction as any} />);

    await setInput(node.querySelector("input[aria-label='Backtest strategy ID']") as HTMLInputElement, "strat-1");
    await setInput(node.querySelector("input[aria-label='Backtest dataset ID']") as HTMLInputElement, "blocked-ds");
    const run = [...node.querySelectorAll("button")].find((button) => button.textContent === "Run Backtest");
    await click(run!);

    expect(node.textContent).toContain("dataset not approved");
    expect(node.textContent).toContain("ORB");
    expect(node.textContent).toContain("bt-existing");
  });

  it("runs and cancels walk-forward jobs through canonical clients", async () => {
    const wfJob = {
      jobId: "wf-1", strategyId: "strat-1", instrument: "NIFTY", timeframe: "5m",
      status: "RUNNING", progress: { done: 1, total: 4 }, oosDays: 5, error: null,
    };
    const loadData = vi.fn().mockResolvedValue(available({
      walkForward: { state: "AVAILABLE" as const, data: [wfJob], asOf: "2026-10-05T18:00:00Z" },
    }));
    const createWalkForwardAction = vi.fn().mockResolvedValue({ success: true, data: { job_id: "wf-new", status: "PENDING", job: wfJob }, isFallback: false });
    const cancelWalkForwardAction = vi.fn().mockResolvedValue({ success: true, data: { job: wfJob }, isFallback: false });
    const node = await mount(<UserTesting
      loadData={loadData}
      createWalkForwardAction={createWalkForwardAction as any}
      cancelWalkForwardAction={cancelWalkForwardAction as any}
    />);

    await setInput(node.querySelector("input[aria-label='Walk-forward strategy ID']") as HTMLInputElement, "strat-1");
    await setInput(node.querySelector("input[aria-label='Walk-forward dataset ID']") as HTMLInputElement, "ds-1");
    await setInput(node.querySelector("input[aria-label='Walk-forward instrument']") as HTMLInputElement, "NIFTY");
    await setInput(node.querySelector("input[aria-label='Walk-forward timeframe']") as HTMLInputElement, "5m");
    await setInput(node.querySelector("input[aria-label='Walk-forward IS days']") as HTMLInputElement, "20");
    await setInput(node.querySelector("input[aria-label='Walk-forward OOS days']") as HTMLInputElement, "5");
    await setInput(node.querySelector("input[aria-label='Walk-forward max windows']") as HTMLInputElement, "8");
    await setInput(node.querySelector("input[aria-label='Walk-forward initial capital']") as HTMLInputElement, "500000");

    const run = [...node.querySelectorAll("button")].find((button) => button.textContent === "Run Walk-Forward");
    expect(run).toBeTruthy();
    await click(run!);
    expect(createWalkForwardAction).toHaveBeenCalledWith({
      strategy_id: "strat-1",
      dataset_id: "ds-1",
      instrument: "NIFTY",
      timeframe: "5m",
      is_days: 20,
      oos_days: 5,
      max_windows: 8,
      initial_capital: 500000,
    });

    const cancel = node.querySelector("button[aria-label='Cancel walk-forward wf-1']");
    expect(cancel).toBeTruthy();
    await click(cancel!);
    expect(cancelWalkForwardAction).toHaveBeenCalledTimes(1);
    expect(cancelWalkForwardAction).toHaveBeenCalledWith("wf-1");
  });

  it("does not enable research mutations when authority is stale", async () => {
    const node = await mount(<UserTesting loadData={async () => ({
      backtests: { state: "STALE" as const, data: [], asOf: "2026-10-05T17:00:00Z" },
      walkForward: { state: "UNKNOWN" as const, data: [], asOf: null },
      reports: { state: "AVAILABLE" as const, data: [], asOf: "2026-10-05T18:00:00Z" },
    })} />);
    const backtestButton = [...node.querySelectorAll("button")].find((button) => button.textContent === "Run Backtest") as HTMLButtonElement | undefined;
    const wfButton = [...node.querySelectorAll("button")].find((button) => button.textContent === "Run Walk-Forward") as HTMLButtonElement | undefined;
    expect(backtestButton?.disabled).toBe(true);
    expect(wfButton?.disabled).toBe(true);
    expect(node.textContent).toContain("STALE");
    expect(node.textContent).toContain("UNKNOWN");
  });
});
