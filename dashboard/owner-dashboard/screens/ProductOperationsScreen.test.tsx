import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { ProductOperationsScreen } from "./ProductOperationsScreen";

let root: Root | null = null;
let container: HTMLDivElement | null = null;

afterEach(async () => {
  if (root) await act(async () => root?.unmount());
  container?.remove();
  root = null;
  container = null;
});

async function mount(node: React.ReactNode) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(node);
    await Promise.resolve();
    await Promise.resolve();
  });
  return container;
}

describe("ProductOperationsScreen", () => {
  it("renders authoritative product-operations health without trading authority", async () => {
    const node = await mount(<ProductOperationsScreen loadData={async () => ({
      state: "AVAILABLE" as const,
      asOf: "2026-10-01T12:00:00Z",
      data: {
        unresolved_incidents: 2,
        alert_health: "DEGRADED",
        privacy_requests: [["RECEIVED", 3], ["IN_PROGRESS", 1]],
        stale_policy_count: 1,
        backup_status: "PASS",
        restore_status: "PASS",
        rollback_status: "PASS",
        active_policy_versions: ["privacy-notice/1.0.0"],
        live_state: "READ_ONLY/DISARMED",
        ai_authority: "RESEARCH_SHADOW_ONLY",
      },
    })} />);
    expect(node.querySelector("[data-testid='product-operations-surface']")).not.toBeNull();
    expect(node.textContent).toContain("Product Operations");
    expect(node.textContent).toContain("DEGRADED");
    expect(node.textContent).toContain("READ_ONLY/DISARMED");
    expect(node.textContent).toContain("RESEARCH_SHADOW_ONLY");
    expect(node.textContent).not.toContain("Arm Live");
    expect(node.textContent).not.toContain("Place Order");
  });

  it("fails closed when owner ProductOps authority is unavailable", async () => {
    const node = await mount(<ProductOperationsScreen loadData={async () => ({
      state: "UNAVAILABLE" as const,
      asOf: null,
      data: null,
    })} />);
    expect(node.textContent).toContain("UNAVAILABLE");
    expect(node.textContent).not.toContain("0 incidents");
    expect(node.textContent).not.toContain("PASS");
  });
});
