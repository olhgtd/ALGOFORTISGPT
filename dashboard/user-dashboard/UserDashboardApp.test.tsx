import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { UserDashboardApp } from "./UserDashboardApp";
import { deriveUserShellStatus } from "./shellState";

let root: Root | null = null;
let container: HTMLDivElement | null = null;

beforeEach(() => {
  window.history.replaceState({}, "", "/?surface=dashboard-v3&workspace=user#markets");
});

afterEach(async () => {
  if (root) await act(async () => root?.unmount());
  container?.remove();
  root = null;
  container = null;
  window.history.replaceState({}, "", "/");
});

const unavailableShell = async () => ({
  status: deriveUserShellStatus({ mode: "UNKNOWN", automationState: "UNKNOWN" }),
  notifications: [],
  risk: { state: "UNKNOWN" as const, level: null, reasons: [] },
});

const mount = async (loadShell = unavailableShell) => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);

  await act(async () => {
    root?.render(<UserDashboardApp theme="dark" toggleTheme={() => {}} loadShell={loadShell} shellRefreshMs={0} />);
    await Promise.resolve();
    await Promise.resolve();
  });

  return container;
};

describe("UserDashboardApp shared shell authority", () => {
  it("keeps mode and automation UNKNOWN until an authority supplies them", async () => {
    const node = await mount();
    const workspace = node.querySelector(".af-user-workspace");

    expect(workspace?.getAttribute("data-mode")).toBe("unknown");
    expect(workspace?.getAttribute("data-operational-state")).toBe("unknown");
    expect(node.querySelector(".af-mode-chip")?.textContent).toBe("Unavailable");
    expect(node.textContent).not.toContain("STOPPED");
    expect(node.textContent).not.toContain("Paper");
  });

  it("hydrates authoritative shell status even when the dashboard opens directly on Markets", async () => {
    const node = await mount(async () => ({
      status: deriveUserShellStatus({
        mode: "PAPER",
        automationState: "PAUSED",
        brokerState: "DISCONNECTED",
        engineState: "AVAILABLE",
        dataFreshness: "STALE",
      }),
      notifications: [],
      risk: { state: "UNKNOWN" as const, level: null, reasons: [] },
    }));

    const workspace = node.querySelector(".af-user-workspace");
    expect(workspace?.getAttribute("data-mode")).toBe("paper");
    expect(workspace?.getAttribute("data-operational-state")).toBe("paused");
    expect(node.querySelector(".af-mode-chip")?.textContent).toBe("Paper");
  });

  it("feeds authoritative derived notices into the Attention Center", async () => {
    const node = await mount(async () => ({
      status: deriveUserShellStatus({
        mode: "PAPER",
        automationState: "READY_FOR_RESUME",
        brokerState: "NEEDS_ATTENTION",
        engineState: "AVAILABLE",
        dataFreshness: "STALE",
        notifications: { actionRequired: 1 },
      }),
      notifications: [{
        id: "manual-resume",
        priority: "Action Required" as const,
        title: "Manual resume required",
        detail: "READY_FOR_RESUME is authoritative.",
      }],
      risk: { state: "AVAILABLE" as const, level: "BLOCKED", reasons: [] },
    }));

    const bell = node.querySelector("[data-testid='notification-bell']") as HTMLButtonElement;
    expect(bell.getAttribute("aria-label")).toContain("1 unread");
    await act(async () => bell.click());
    expect(node.textContent).toContain("Manual resume required");
    expect(node.textContent).toContain("READY_FOR_RESUME is authoritative.");
  });
});
