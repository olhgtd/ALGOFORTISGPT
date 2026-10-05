import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UserTrades } from "./UserTrades";

let root: Root | null = null;
let container: HTMLDivElement | null = null;

afterEach(async () => {
  if (root) await act(async () => root?.unmount());
  container?.remove();
  root = null;
  container = null;
});

const trading = async () => ({
  PAPER: {
    state: "AVAILABLE" as const,
    snapshot: { execution_mode: "PAPER" as const, availability: "AVAILABLE" as const, source: "paper", accounts: [], positions: [], orders: [], events: [], aggregate_exposure: null, limitations: [] },
  },
  LIVE: { state: "UNAVAILABLE" as const, snapshot: null },
});

const session = (id: string, status: string) => ({
  session_id: id,
  user_id: "u1",
  strategy_id: "strat-1",
  strategy_name: "ORB",
  strategy_version: "v1",
  instrument: "NIFTY",
  timeframe: "5m",
  initial_capital: 50000,
  current_equity: 50000,
  available_cash: 50000,
  used_capital: 0,
  realized_pnl: 0,
  unrealized_pnl: 0,
  day_pnl: 0,
  total_pnl: 0,
  return_pct: 0,
  trades_count: 0,
  status,
  data_source_mode: "HISTORICAL_REPLAY",
});

const sessionsResult = (rows: any[]) => Promise.resolve({
  data: rows,
  source: "BACKEND" as const,
  trust: "FRESH" as const,
  asOf: "2026-10-05T18:00:00Z",
  isFallback: false,
});

const mount = async (node: React.ReactNode) => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(node);
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
  return container;
};

const input = (node: HTMLElement, label: string): HTMLInputElement => {
  const el = node.querySelector(`input[aria-label='${label}']`);
  expect(el, `canonical input missing: ${label}`).not.toBeNull();
  if (!(el instanceof HTMLInputElement)) throw new Error(`canonical input missing: ${label}`);
  return el;
};

const setInput = async (el: HTMLInputElement, value: string) => {
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  });
};

const click = async (el: Element | undefined | null, label: string) => {
  expect(el, `canonical control missing: ${label}`).toBeTruthy();
  if (!el) throw new Error(`canonical control missing: ${label}`);
  await act(async () => {
    (el as HTMLElement).click();
    await Promise.resolve();
    await Promise.resolve();
  });
};

describe("canonical Paper session actions", () => {
  it("creates a governed historical-replay paper session with exact payload", async () => {
    const loadData = vi.fn(trading);
    const loadPaperSessionsAction = vi.fn(() => sessionsResult([]));
    const createPaperSessionAction = vi.fn().mockResolvedValue({ ok: true, data: session("ps-new", "INITIALIZED"), isFallback: false });
    const node = await mount(<UserTrades
      loadData={loadData}
      loadPaperSessionsAction={loadPaperSessionsAction as any}
      createPaperSessionAction={createPaperSessionAction as any}
    />);

    await setInput(input(node, "Paper strategy ID"), "strat-1");
    await setInput(input(node, "Paper instrument"), "NIFTY");
    await setInput(input(node, "Paper timeframe"), "5m");
    await setInput(input(node, "Paper initial capital"), "50000");
    await setInput(input(node, "Paper dataset ID"), "ds-1");
    await setInput(input(node, "Paper date range"), "2026-01-05");

    const create = [...node.querySelectorAll("button")].find((button) => button.textContent === "Create Paper Session");
    await click(create, "Create Paper Session");

    expect(createPaperSessionAction).toHaveBeenCalledTimes(1);
    expect(createPaperSessionAction).toHaveBeenCalledWith({
      strategy_id: "strat-1",
      instrument: "NIFTY",
      timeframe: "5m",
      initial_capital: 50000,
      data_source_mode: "HISTORICAL_REPLAY",
      dataset_id: "ds-1",
      date_range: "2026-01-05",
    });
    expect(loadPaperSessionsAction.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(loadData.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(node.textContent).toContain("Paper session created");
  });

  it("starts initialized sessions and stops running sessions through backend authority", async () => {
    const loadPaperSessionsAction = vi.fn(() => sessionsResult([
      session("ps-init", "INITIALIZED"),
      session("ps-run", "RUNNING"),
    ]));
    const startPaperSessionAction = vi.fn().mockResolvedValue({ ok: true, data: session("ps-init", "RUNNING"), isFallback: false });
    const stopPaperSessionAction = vi.fn().mockResolvedValue({ ok: true, data: session("ps-run", "STOPPED"), isFallback: false });
    const node = await mount(<UserTrades
      loadData={trading}
      loadPaperSessionsAction={loadPaperSessionsAction as any}
      startPaperSessionAction={startPaperSessionAction as any}
      stopPaperSessionAction={stopPaperSessionAction as any}
    />);

    await click(node.querySelector("button[aria-label='Start paper session ps-init']"), "Start ps-init");
    expect(startPaperSessionAction).toHaveBeenCalledTimes(1);
    expect(startPaperSessionAction).toHaveBeenCalledWith("ps-init");

    await click(node.querySelector("button[aria-label='Stop paper session ps-run']"), "Stop ps-run");
    expect(stopPaperSessionAction).toHaveBeenCalledTimes(1);
    expect(stopPaperSessionAction).toHaveBeenCalledWith("ps-run");
  });

  it("keeps session evidence visible when backend rejects a paper action", async () => {
    const loadPaperSessionsAction = vi.fn(() => sessionsResult([session("ps-init", "INITIALIZED")]));
    const startPaperSessionAction = vi.fn().mockResolvedValue({ ok: false, error: "RiskGate hold active", isFallback: false });
    const node = await mount(<UserTrades
      loadData={trading}
      loadPaperSessionsAction={loadPaperSessionsAction as any}
      startPaperSessionAction={startPaperSessionAction as any}
    />);

    await click(node.querySelector("button[aria-label='Start paper session ps-init']"), "Start ps-init");
    expect(node.textContent).toContain("RiskGate hold active");
    expect(node.textContent).toContain("ps-init");
    expect(node.textContent).toContain("INITIALIZED");
  });

  it("never exposes live arming or live order mutation controls", async () => {
    const node = await mount(<UserTrades loadData={trading} loadPaperSessionsAction={vi.fn(() => sessionsResult([])) as any} />);
    expect(node.textContent).toContain("READ_ONLY / DISARMED");
    expect(node.textContent).not.toContain("Arm Live");
    expect(node.textContent).not.toContain("Place Live Order");
    expect(node.innerHTML).not.toContain("/api/v1/live/arm");
  });
});
