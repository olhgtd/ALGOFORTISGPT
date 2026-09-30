import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SecureEntryApp } from "../SecureEntryApp";
import { api } from "../../../api";

vi.mock("../../../api", () => ({
  api: {
    securityStatus: vi.fn(),
    ownerBootstrapStatus: vi.fn(),
  },
}));
vi.mock("../SentinelXCore", () => ({ SentinelXCore: () => <div id="mock-core" /> }));
vi.mock("../../../../shared/utilities/V3Chrome", () => ({ GlobalRealTimeClock: () => <div id="mock-clock" /> }));
vi.mock("../ReturningUserFlow", () => ({
  ReturningUserFlow: (props: { onSwitchToAccessGate: () => void; onSwitchToRecovery: () => void }) => (
    <div id="mock-returning">
      <button id="mock-activate-switch" onClick={props.onSwitchToAccessGate}>Activate User</button>
      <button id="mock-recovery-switch" onClick={props.onSwitchToRecovery}>Recovery</button>
    </div>
  ),
}));
vi.mock("../FirstTimeCustomerFlow", () => ({ FirstTimeCustomerFlow: () => <div id="mock-activation" /> }));
vi.mock("../LocalOwnerSetupCard", () => ({ LocalOwnerSetupCard: () => <div id="mock-owner-setup" /> }));
vi.mock("../HelpRecoveryFlow", () => ({ HelpRecoveryFlow: () => <div id="mock-recovery" /> }));
vi.mock("../OwnerSetupFlow", () => ({ OwnerSetupFlow: () => <div id="legacy-owner-setup" /> }));

let root: Root | null = null;
let container: HTMLDivElement | null = null;

async function mount() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(<SecureEntryApp />);
    await Promise.resolve();
    await Promise.resolve();
  });
  return container;
}

beforeEach(() => {
  vi.mocked(api.securityStatus).mockResolvedValue({
    password_authentication: "ENABLED",
    owner_initialized: true,
    webauthn: "NOT_CONFIGURED",
    webauthn_enrollment: "NOT_CONFIGURED",
    normal_mtls: "NOT_CONFIGURED",
    break_glass: "NOT_CONFIGURED",
    owner_authenticators_ready: false,
    normal_mtls_required: false,
  });
});

afterEach(async () => {
  if (root) await act(async () => root?.unmount());
  container?.remove();
  root = null;
  container = null;
});

describe("SecureEntryApp canonical routing", () => {
  it("maps LOCAL_LOGIN to the shared returning-user gate", async () => {
    vi.mocked(api.ownerBootstrapStatus).mockResolvedValue({
      owner_presence: "LOCAL_EXISTS",
      owner_setup_allowed: false,
      recommended_flow: "LOCAL_LOGIN",
      authority: "LOCAL",
      reason: "existing owner",
    });
    const node = await mount();
    expect(node.querySelector("#mock-returning")).not.toBeNull();
    expect(node.querySelector("#local-login-card")).toBeNull();
  });

  it("fails closed on a fresh second PC when authority cannot prove owner absence", async () => {
    vi.mocked(api.ownerBootstrapStatus).mockResolvedValue({
      owner_presence: "UNKNOWN",
      owner_setup_allowed: false,
      recommended_flow: "UNAVAILABLE",
      authority: "UNAVAILABLE",
      reason: "roaming authority unavailable",
    });
    const node = await mount();
    expect(node.textContent).toContain("Account authority unavailable");
    expect(node.querySelector("#mock-owner-setup")).toBeNull();
    expect(node.querySelector("#legacy-owner-setup")).toBeNull();
  });

  it("renders Owner Setup only when explicitly authorized", async () => {
    vi.mocked(api.ownerBootstrapStatus).mockResolvedValue({
      owner_presence: "ABSENT_CONFIRMED",
      owner_setup_allowed: true,
      recommended_flow: "LOCAL_OWNER_SETUP",
      authority: "TRUSTED_BOOTSTRAP",
      reason: "trusted first bootstrap",
    });
    const node = await mount();
    expect(node.querySelector("#mock-owner-setup")).not.toBeNull();
  });

  it("lets normal Sign In navigate to Activate User without exposing Owner Setup", async () => {
    vi.mocked(api.ownerBootstrapStatus).mockResolvedValue({
      owner_presence: "LOCAL_EXISTS",
      owner_setup_allowed: false,
      recommended_flow: "RETURNING_USER",
      authority: "LOCAL",
      reason: "existing owner",
    });
    const node = await mount();
    const activate = node.querySelector("#mock-activate-switch") as HTMLButtonElement;
    await act(async () => activate.click());
    expect(node.querySelector("#mock-activation")).not.toBeNull();
    expect(node.querySelector("#mock-owner-setup")).toBeNull();
  });
});
