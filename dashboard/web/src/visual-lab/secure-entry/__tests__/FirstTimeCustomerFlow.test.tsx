import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FirstTimeCustomerFlow } from "../FirstTimeCustomerFlow";
import { api } from "../../../api";

vi.mock("../../../api", () => ({
  api: {
    passwordActivate: vi.fn(),
  },
}));

let root: Root | null = null;
let container: HTMLDivElement | null = null;

async function mount(onSwitchToReturningUser = vi.fn()) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(
      <FirstTimeCustomerFlow
        accessId=""
        onAccessIdChange={() => {}}
        gateStep="ENTER_ACCESS_ID"
        onGateStepChange={() => {}}
        onSwitchToReturningUser={onSwitchToReturningUser}
      />,
    );
  });
  return { node: container, onSwitchToReturningUser };
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
  const form = container?.querySelector("#access-gate-form") as HTMLFormElement;
  await act(async () => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await Promise.resolve();
    await Promise.resolve();
  });
}

beforeEach(() => {
  vi.mocked(api.passwordActivate).mockReset();
});

afterEach(async () => {
  if (root) await act(async () => root?.unmount());
  container?.remove();
  root = null;
  container = null;
});

describe("FirstTimeCustomerFlow password activation", () => {
  it("renders the five required V1-style activation fields", async () => {
    const { node } = await mount();
    expect(node.querySelector("#access-id-input")).not.toBeNull();
    expect(node.querySelector("#activation-code-input")).not.toBeNull();
    expect(node.querySelector("#activation-email-input")).not.toBeNull();
    expect(node.querySelector("#activation-password-input")).not.toBeNull();
    expect(node.querySelector("#activation-confirm-password-input")).not.toBeNull();
    expect(node.textContent).not.toContain("REGISTER PASSKEY");
  });

  it("blocks mismatched passwords before calling the backend", async () => {
    await mount();
    await setValue("#access-id-input", "AF-U-ABCD-2345");
    await setValue("#activation-code-input", "AF-ACT-AAAA-BBBB-CCCC");
    await setValue("#activation-email-input", "user@example.com");
    await setValue("#activation-password-input", "UserPassword123!");
    await setValue("#activation-confirm-password-input", "DifferentPassword123!");
    await submit();

    expect(api.passwordActivate).not.toHaveBeenCalled();
    expect(container?.textContent).toContain("Passwords do not match");
  });

  it("clears secrets after success and offers Sign In", async () => {
    vi.mocked(api.passwordActivate).mockResolvedValue({ activated: true, authentication_required: true });
    const { node, onSwitchToReturningUser } = await mount();
    await setValue("#access-id-input", "AF-U-ABCD-2345");
    await setValue("#activation-code-input", "AF-ACT-AAAA-BBBB-CCCC");
    await setValue("#activation-email-input", "user@example.com");
    await setValue("#activation-password-input", "UserPassword123!");
    await setValue("#activation-confirm-password-input", "UserPassword123!");
    await submit();

    expect(api.passwordActivate).toHaveBeenCalledWith({
      identifier: "AF-U-ABCD-2345",
      activation_code: "AF-ACT-AAAA-BBBB-CCCC",
      email: "user@example.com",
      password: "UserPassword123!",
      confirm_password: "UserPassword123!",
    });
    expect((node.querySelector("#activation-code-input") as HTMLInputElement | null)?.value ?? "").toBe("");
    expect((node.querySelector("#activation-password-input") as HTMLInputElement | null)?.value ?? "").toBe("");
    const signIn = node.querySelector("#activation-signin-btn") as HTMLButtonElement;
    expect(signIn).not.toBeNull();
    await act(async () => signIn.click());
    expect(onSwitchToReturningUser).toHaveBeenCalledTimes(1);
  });

  it("renders backend failure inline without echoing secret values", async () => {
    vi.mocked(api.passwordActivate).mockRejectedValue(new Error("AlgoFortis request failed (403 Activation unavailable)"));
    const { node } = await mount();
    await setValue("#access-id-input", "AF-U-ABCD-2345");
    await setValue("#activation-code-input", "AF-ACT-SECRET-CODE");
    await setValue("#activation-email-input", "user@example.com");
    await setValue("#activation-password-input", "UserPassword123!");
    await setValue("#activation-confirm-password-input", "UserPassword123!");
    await submit();

    expect(node.textContent).toContain("Activation unavailable");
    expect(node.textContent).not.toContain("AF-ACT-SECRET-CODE");
    expect(node.textContent).not.toContain("UserPassword123!");
  });
});
