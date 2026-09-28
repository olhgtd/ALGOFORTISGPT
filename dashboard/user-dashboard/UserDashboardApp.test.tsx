import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { UserDashboardApp } from "./UserDashboardApp";

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

const mount = async () => {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);

  await act(async () => {
    root?.render(<UserDashboardApp theme="dark" toggleTheme={() => {}} />);
  });

  return container;
};

describe("UserDashboardApp shell authority defaults", () => {
  it("keeps mode and automation UNKNOWN until an authority supplies them", async () => {
    const node = await mount();
    const workspace = node.querySelector(".af-user-workspace");

    expect(workspace?.getAttribute("data-mode")).toBe("unknown");
    expect(workspace?.getAttribute("data-operational-state")).toBe("unknown");
    expect(node.querySelector(".af-mode-chip")?.textContent).toBe("Unavailable");
    expect(node.textContent).not.toContain("STOPPED");
    expect(node.textContent).not.toContain("Paper");
  });
});
