import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReturningUserFlow } from "../ReturningUserFlow";
import { api, setSessionToken } from "../../../api";

vi.mock("../../../api", () => ({
  api: { passwordLogin: vi.fn() },
  setSessionToken: vi.fn(),
  clearSessionToken: vi.fn(),
}));

let root: Root | null = null;
let container: HTMLDivElement | null = null;

async function mount(requiredRole?: "OWNER" | "USER") {
  const onEnterWorkspace = vi.fn();
  const onSwitchToAccessGate = vi.fn();
  const onSwitchToRecovery = vi.fn();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(
      <ReturningUserFlow
        sentinelxId=""
        onIdChange={() => {}}
        verificationState="ID_ENTRY"
        onStartVerification={() => {}}
        onVerifySuccess={() => {}}
        onVerifyFailure={() => {}}
        onSwitchToAccessGate={onSwitchToAccessGate}
        onSwitchToOwnerSetup={() => {}}
        onSwitchToRecovery={onSwitchToRecovery}
        requiredRole={requiredRole}
        onEnterWorkspace={onEnterWorkspace}
      />,
    );
  });
  return { node: container, onEnterWorkspace, onSwitchToAccessGate, onSwitchToRecovery };
}

async function setValue(selector: string, value: string) {
  const input = container?.querySelector(selector) as HTMLInputElement;
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

async function submit() {
  const form = container?.querySelector("#returning-user-signin-form") as HTMLFormElement;
  await act(async () => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await Promise.resolve();
    await Promise.resolve();
  });
}

beforeEach(() => {
  vi.mocked(api.passwordLogin).mockReset();
  vi.mocked(setSessionToken).mockReset();
});

afterEach(async () => {
  if (root) await act(async () => root?.unmount());
  container?.remove();
  root = null;
  container = null;
});

describe("ReturningUserFlow shared password login", () => {
  it("enables User ID/email and password fields", async () => {
    const { node } = await mount();
    expect((node.querySelector("#sentinelx-id-input") as HTMLInputElement).disabled).toBe(false);
    expect((node.querySelector("#returning-password-input") as HTMLInputElement).disabled).toBe(false);
    expect(node.textContent).not.toContain("Password login is disabled");
  });

  it("routes OWNER only from backend response", async () => {
    vi.mocked(api.passwordLogin).mockResolvedValue({
      access_token: "owner-token",
      expires_at_utc: "2026-09-30T12:00:00+00:00",
      subject: "owner-id",
      role: "OWNER",
      sx_id: "OWNER-001",
      workspace_eligibility: { owner: true, user: true },
    });
    const { onEnterWorkspace } = await mount();
    await setValue("#sentinelx-id-input", "owner@example.com");
    await setValue("#returning-password-input", "OwnerPassword123!");
    await submit();

    expect(api.passwordLogin).toHaveBeenCalledWith({ identifier: "owner@example.com", password: "OwnerPassword123!" });
    expect(setSessionToken).toHaveBeenCalledWith("owner-token");
    expect(onEnterWorkspace).toHaveBeenCalledWith("OWNER");
  });

  it("routes USER only from backend response", async () => {
    vi.mocked(api.passwordLogin).mockResolvedValue({
      access_token: "user-token",
      expires_at_utc: "2026-09-30T12:00:00+00:00",
      subject: "user-id",
      role: "USER",
      sx_id: "AF-U-ABCD-2345",
      workspace_eligibility: { owner: false, user: true },
    });
    const { onEnterWorkspace } = await mount();
    await setValue("#sentinelx-id-input", "AF-U-ABCD-2345");
    await setValue("#returning-password-input", "UserPassword123!");
    await submit();

    expect(setSessionToken).toHaveBeenCalledWith("user-token");
    expect(onEnterWorkspace).toHaveBeenCalledWith("USER");
  });


  it("rejects an Owner account inside the role-locked User package", async () => {
    vi.mocked(api.passwordLogin).mockResolvedValue({
      access_token: "owner-token",
      expires_at_utc: "2026-09-30T12:00:00+00:00",
      subject: "owner-id",
      role: "OWNER",
      sx_id: "OWNER-001",
      workspace_eligibility: { owner: true, user: true },
    });
    const { node, onEnterWorkspace } = await mount("USER");
    await setValue("#sentinelx-id-input", "owner@example.com");
    await setValue("#returning-password-input", "OwnerPassword123!");
    await submit();

    expect(setSessionToken).not.toHaveBeenCalled();
    expect(onEnterWorkspace).not.toHaveBeenCalled();
    expect(node.textContent).toContain("Open AlgoFortis Owner");
  });

  it("renders generic invalid credentials and cooldown failures", async () => {
    vi.mocked(api.passwordLogin).mockRejectedValueOnce(new Error("AlgoFortis request failed (401 INVALID_ID_OR_PASSWORD)"));
    const { node } = await mount();
    await setValue("#sentinelx-id-input", "user@example.com");
    await setValue("#returning-password-input", "WrongPassword123!");
    await submit();
    expect(node.textContent).toContain("INVALID_ID_OR_PASSWORD");

    vi.mocked(api.passwordLogin).mockRejectedValueOnce(new Error("RATE_LIMIT_COOLDOWN: Cooldown active"));
    await setValue("#returning-password-input", "WrongPassword123!");
    await submit();
    expect(node.textContent).toContain("RATE_LIMIT_COOLDOWN");
  });

  it("keeps Activate User and Recovery navigation available", async () => {
    const { node, onSwitchToAccessGate, onSwitchToRecovery } = await mount();
    const activate = node.querySelector("#nav-to-first-time-activation") as HTMLButtonElement;
    const recovery = node.querySelector("#nav-to-recovery-btn") as HTMLButtonElement;
    await act(async () => activate.click());
    await act(async () => recovery.click());
    expect(onSwitchToAccessGate).toHaveBeenCalledTimes(1);
    expect(onSwitchToRecovery).toHaveBeenCalledTimes(1);
  });
});
