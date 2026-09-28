import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UserDashboardShell } from "./UserDashboardShell";
import { deriveUserShellStatus } from "../shellState";
import type { UserScreenId } from "../navigation";

let root: Root | null = null;
let container: HTMLDivElement | null = null;

afterEach(async () => {
  if (root) await act(async () => root?.unmount());
  container?.remove();
  root = null;
  container = null;
});

const mount = async (onNavigate: (screen: UserScreenId) => void = () => {}) => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  const status = deriveUserShellStatus({
    mode: "LIVE",
    automationState: "READY_FOR_RESUME",
    brokerState: "CONNECTED",
    engineState: "AVAILABLE",
    dataFreshness: "STALE",
    notifications: { critical: 1, actionRequired: 2 },
  });

  await act(async () => {
    root?.render(
      <UserDashboardShell
        theme="dark"
        toggleTheme={() => {}}
        activeScreen="home"
        onNavigate={onNavigate}
        onOpenPalette={() => {}}
        status={status}
        notifications={[{ id: "n1", priority: "Critical", title: "Risk state requires attention" }]}
      >
        <div>Home body</div>
      </UserDashboardShell>,
    );
  });
  return container;
};

describe("UserDashboardShell", () => {
  it("renders only the approved seven user navigation destinations in order", async () => {
    const node = await mount();
    expect([...node.querySelectorAll("[data-user-nav]")].map((el) => el.textContent?.trim())).toEqual([
      "Home",
      "Markets",
      "Strategies",
      "Testing & Validation",
      "Trades",
      "Portfolio",
      "Account",
    ]);
    expect(node.textContent).not.toContain("Connections");
    expect(node.textContent).not.toContain("Paper Trading");
    expect(node.textContent).not.toContain("Agents");
    expect(node.textContent).not.toContain("Owner");
  });

  it("shows operational context without implying that broker-connected means Live-armed", async () => {
    const node = await mount();
    expect(node.textContent).toContain("AlgoFortis");
    expect(node.textContent).toContain("Live");
    expect(node.textContent).toContain("READ_ONLY / DISARMED");
    expect(node.textContent).toContain("CONNECTED");
    expect(node.textContent).toContain("AVAILABLE");
    expect(node.querySelector("[data-mode='live']")).not.toBeNull();
    expect(node.querySelector("[data-operational-state='ready-for-resume']")).not.toBeNull();
    expect(node.querySelector("[data-manual-resume-required='true']")).not.toBeNull();
  });

  it("opens the global notification layer from the bell", async () => {
    const node = await mount();
    const bell = node.querySelector<HTMLButtonElement>("[data-testid='notification-bell']");
    expect(bell).not.toBeNull();
    await act(async () => bell?.click());
    expect(node.querySelector("[data-testid='notification-center']")?.textContent).toContain("Risk state requires attention");
  });

  it("routes the profile/account entry to the canonical Account surface", async () => {
    const onNavigate = vi.fn();
    const node = await mount(onNavigate);
    const account = node.querySelector<HTMLButtonElement>("[data-testid='account-entry']");
    expect(account).not.toBeNull();
    await act(async () => account?.click());
    expect(onNavigate).toHaveBeenCalledWith("account");
  });
});
