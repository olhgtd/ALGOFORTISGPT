import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { submitUserStrategy } from "../../shared/services/integrationClient";
import { UserStrategies } from "./UserStrategies";

let root: Root | null = null;
let container: HTMLDivElement | null = null;

afterEach(async () => {
  if (root) await act(async () => root?.unmount());
  container?.remove();
  root = null;
  container = null;
  vi.restoreAllMocks();
  delete (window as any).__ALGOFORTIS_ENABLE_BACKEND__;
  delete (window as any).__ALGOFORTIS_API_URL__;
});

const strategyEntry = {
  strategy_id: "strat-1",
  version_id: "v1",
  stage: "BACKTESTED",
  visibility: "PRIVATE",
  admin_status: "ACTIVE",
  protective_policy: "POL-1",
  archived: false,
};

const readiness = {
  strategyId: "strat-1",
  backtest: { ready: true, code: "READY", reason: "Qualified" },
  paper: { ready: true, code: "READY", reason: "Qualified" },
  livePaper: { ready: true, code: "READY", reason: "Qualified" },
  live: { ready: false, code: "DISARMED", reason: "Live remains disarmed" },
};

const surface = (deployments: any[] = []) => ({
  state: "AVAILABLE" as const,
  strategies: [{ entry: strategyEntry as any, readiness: readiness as any, deployments }],
  deploymentsState: "AVAILABLE" as const,
  asOf: "2026-10-05T18:00:00Z",
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

const input = (node: HTMLElement, label: string): HTMLInputElement => {
  const el = node.querySelector(`input[aria-label='${label}']`);
  expect(el, `canonical input missing: ${label}`).not.toBeNull();
  if (!(el instanceof HTMLInputElement)) throw new Error(`canonical input missing: ${label}`);
  return el;
};

const textarea = (node: HTMLElement, label: string): HTMLTextAreaElement => {
  const el = node.querySelector(`textarea[aria-label='${label}']`);
  expect(el, `canonical textarea missing: ${label}`).not.toBeNull();
  if (!(el instanceof HTMLTextAreaElement)) throw new Error(`canonical textarea missing: ${label}`);
  return el;
};

const setControlValue = async (el: HTMLInputElement | HTMLTextAreaElement, value: string) => {
  await act(async () => {
    const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
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

describe("canonical user strategy mutation client", () => {
  it("posts exact strategy source and protective policy to canonical backend", async () => {
    (window as any).__ALGOFORTIS_ENABLE_BACKEND__ = true;
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      strategy_id: "strat-1",
      version_id: "v1",
      stage: "DRAFT",
      source_sha256: "abc",
    }), { status: 200, headers: { "Content-Type": "application/json" } }));

    const result = await submitUserStrategy("class Strategy {}", "POL-1");

    expect(result.success).toBe(true);
    expect(result.isFallback).toBe(false);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith("/api/v1/strategies", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        source: "class Strategy {}",
        protective_policy_identity: "POL-1",
      }),
    }));
  });

  it("fails closed on backend rejection without sample success", async () => {
    (window as any).__ALGOFORTIS_ENABLE_BACKEND__ = true;
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "strategy rejected" }), {
      status: 422,
      headers: { "Content-Type": "application/json" },
    }));

    const result = await submitUserStrategy("bad", null);

    expect(result.success).toBe(false);
    expect(result.isFallback).toBe(false);
    expect(result.error).toContain("strategy rejected");
  });
});

describe("canonical Strategies action surface", () => {
  it("submits strategy source and refreshes authoritative registry", async () => {
    const loadData = vi.fn().mockResolvedValue(surface());
    const submitStrategyAction = vi.fn().mockResolvedValue({ success: true, data: { strategy_id: "new-strat", version_id: "v1", stage: "DRAFT" }, isFallback: false });
    const node = await mount(<UserStrategies loadData={loadData} submitStrategyAction={submitStrategyAction as any} />);

    await setControlValue(textarea(node, "Strategy source"), "class MyStrategy {}");
    await setControlValue(input(node, "Protective policy identity"), "POL-CONSERVATIVE");
    const submit = [...node.querySelectorAll("button")].find((button) => button.textContent === "Submit Strategy");
    await click(submit, "Submit Strategy");

    expect(submitStrategyAction).toHaveBeenCalledTimes(1);
    expect(submitStrategyAction).toHaveBeenCalledWith("class MyStrategy {}", "POL-CONSERVATIVE");
    expect(loadData.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(node.textContent).toContain("Strategy submitted");
  });

  it("requests PAPER_ELIGIBLE promotion without directly mutating stage", async () => {
    const loadData = vi.fn().mockResolvedValue(surface());
    const requestPromotionAction = vi.fn().mockResolvedValue({ success: true, data: { request_id: "pr-1", status: "PENDING" }, isFallback: false });
    const node = await mount(<UserStrategies loadData={loadData} requestPromotionAction={requestPromotionAction as any} />);

    await click(node.querySelector("button[aria-label='Request promotion strat-1']"), "Request promotion strat-1");

    expect(requestPromotionAction).toHaveBeenCalledTimes(1);
    expect(requestPromotionAction).toHaveBeenCalledWith("strat-1", {
      target_stage: "PAPER_ELIGIBLE",
      notes: "User requested Paper eligibility from canonical Strategies surface",
    });
    expect(node.textContent).toContain("Promotion request accepted");
  });

  it("creates deployments only as LIVE_PAPER and exposes safe lifecycle controls", async () => {
    const deployments = [
      { deploymentId: "dep-active", strategyId: "strat-1", strategyVersionId: "v1", connectionId: "conn-1", instrument: "NIFTY", timeframe: "5m", executionMode: "LIVE_PAPER", status: "DEPLOYED", blockReason: null },
      { deploymentId: "dep-paused", strategyId: "strat-1", strategyVersionId: "v1", connectionId: "conn-1", instrument: "NIFTY", timeframe: "5m", executionMode: "LIVE_PAPER", status: "PAUSED", blockReason: null },
      { deploymentId: "dep-live", strategyId: "strat-1", strategyVersionId: "v1", connectionId: "conn-1", instrument: "NIFTY", timeframe: "5m", executionMode: "LIVE", status: "BLOCKED", blockReason: "Live disarmed" },
    ];
    const loadData = vi.fn().mockResolvedValue(surface(deployments));
    const createDeploymentAction = vi.fn().mockResolvedValue({ success: true, data: deployments[0], isFallback: false });
    const pauseDeploymentAction = vi.fn().mockResolvedValue({ success: true, data: { ...deployments[0], status: "PAUSED" }, isFallback: false });
    const resumeDeploymentAction = vi.fn().mockResolvedValue({ success: true, data: { ...deployments[1], status: "DEPLOYED" }, isFallback: false });
    const stopDeploymentAction = vi.fn().mockResolvedValue({ success: true, data: { ...deployments[0], status: "STOPPED" }, isFallback: false });
    const node = await mount(<UserStrategies
      loadData={loadData}
      createDeploymentAction={createDeploymentAction as any}
      pauseDeploymentAction={pauseDeploymentAction as any}
      resumeDeploymentAction={resumeDeploymentAction as any}
      stopDeploymentAction={stopDeploymentAction as any}
    />);

    await setControlValue(input(node, "Deployment connection ID strat-1"), "conn-1");
    await setControlValue(input(node, "Deployment instrument strat-1"), "NIFTY");
    await setControlValue(input(node, "Deployment timeframe strat-1"), "5m");
    await setControlValue(input(node, "Deployment risk ref strat-1"), "risk-v1");
    await click(node.querySelector("button[aria-label='Create LIVE_PAPER deployment strat-1']"), "Create LIVE_PAPER deployment strat-1");

    expect(createDeploymentAction).toHaveBeenCalledTimes(1);
    expect(createDeploymentAction).toHaveBeenCalledWith({
      strategy_id: "strat-1",
      strategy_version_id: "v1",
      connection_id: "conn-1",
      instrument: "NIFTY",
      timeframe: "5m",
      execution_mode: "LIVE_PAPER",
      risk_ref: "risk-v1",
    });
    expect(node.querySelector("select[aria-label='Deployment execution mode']")).toBeNull();

    await click(node.querySelector("button[aria-label='Pause deployment dep-active']"), "Pause dep-active");
    expect(pauseDeploymentAction).toHaveBeenCalledWith("dep-active");
    await click(node.querySelector("button[aria-label='Resume deployment dep-paused']"), "Resume dep-paused");
    expect(resumeDeploymentAction).toHaveBeenCalledWith("dep-paused");
    await click(node.querySelector("button[aria-label='Stop deployment dep-active']"), "Stop dep-active");
    expect(stopDeploymentAction).toHaveBeenCalledWith("dep-active");

    expect(node.querySelector("button[aria-label='Resume deployment dep-live']")).toBeNull();
    expect(node.querySelector("button[aria-label='Pause deployment dep-live']")).toBeNull();
    expect(node.textContent).toContain("READ_ONLY / DISARMED");
  });

  it("keeps authoritative strategy evidence visible when a deployment is rejected", async () => {
    const loadData = vi.fn().mockResolvedValue(surface());
    const createDeploymentAction = vi.fn().mockResolvedValue({ success: false, error: "connection is not eligible for LIVE_PAPER", isFallback: false });
    const node = await mount(<UserStrategies loadData={loadData} createDeploymentAction={createDeploymentAction as any} />);

    await setControlValue(input(node, "Deployment connection ID strat-1"), "bad-conn");
    await click(node.querySelector("button[aria-label='Create LIVE_PAPER deployment strat-1']"), "Create LIVE_PAPER deployment strat-1");

    expect(node.textContent).toContain("connection is not eligible for LIVE_PAPER");
    expect(node.textContent).toContain("strat-1");
    expect(node.textContent).toContain("BACKTESTED");
  });
});
