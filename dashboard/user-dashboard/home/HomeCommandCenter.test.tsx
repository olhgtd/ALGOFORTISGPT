import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { HomeCommandCenter } from "./HomeCommandCenter";
import { buildHomeCommandCenterModel } from "./homeModel";

let root: Root | null = null;
let container: HTMLDivElement | null = null;

afterEach(async () => {
  if (root) await act(async () => root?.unmount());
  container?.remove();
  root = null;
  container = null;
});

const renderModel = async (model = buildHomeCommandCenterModel({})) => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root?.render(<HomeCommandCenter model={model} onNavigate={() => {}} />));
  return container;
};

describe("HomeCommandCenter", () => {
  it("renders missing authority as UNAVAILABLE without fake zero or PASS values", async () => {
    const node = await renderModel();
    expect(node.textContent).toContain("UNAVAILABLE");
    expect(node.textContent).not.toContain("₹0");
    expect(node.textContent).not.toMatch(/\bPASS\b/);
    expect(node.textContent).not.toContain("Confirm");
    expect(node.textContent).not.toContain("Auto");
  });

  it("keeps Live locked and recovery manual when those states are authoritative", async () => {
    const model = buildHomeCommandCenterModel({
      shell: { mode: "LIVE", automationState: "RECOVERY", brokerState: "CONNECTED", engineState: "AVAILABLE", dataFreshness: "STALE" },
      portfolio: { state: "AVAILABLE", source: "PERSISTED_PAPER_RUNTIME", accounts: [], positions: [], events: [] },
    });
    const node = await renderModel(model);
    expect(node.textContent).toContain("READ_ONLY / DISARMED");
    expect(node.textContent).toContain("RECOVERY");
    expect(node.textContent).toContain("Manual resume required");
    expect(node.textContent).not.toContain("Laya Confirm");
    expect(node.textContent).not.toContain("Laya Auto");
  });
});
