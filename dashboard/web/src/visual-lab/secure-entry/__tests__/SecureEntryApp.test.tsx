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
vi.mock("../../../../../shared/utilities/V3Chrome", () => ({ GlobalRealTimeClock: () => <div id="mock-clock" /> }));
vi.mock("../ReturningUserFlow", () => ({
  ReturningUserFlow: (props: { onSwitchToAccessGate: () => void; onSwitchToRecovery: () => void; requiredRole?: "OWNER" | "USER" }) => (
    <div id="mock-returning" data-required-role={props.requiredRole ?? ""}>
      <button id="mock-activate-switch" onClick={props.onSwitchToAccessGate}>Activate User</button>
      <button id="mock-recovery-switch" onClick={props.onSwitchToRecovery}>Recovery</button>
    </div>
  ),
}));
vi.mock("../FirstTimeCustomerFlow", () => ({ FirstTimeCustomerFlow: () => <div id="mock-activation" /> }));
vi.mock("../LocalOwnerSetupCard", () => ({
  LocalOwnerSetupCard: (props: { onSwitchToLogin?: () => void }) => (
    <div id="mock-owner-setup">
      {props.onSwitchToLogin && <button id="mock-owner-setup-login" onClick={props.onSwitchToLogin}>Sign In</button>}
    </div>
  ),
}));
vi.mock("../LocalLoginCard", () => ({
  LocalLoginCard: (props: { onSwitchToOwnerSetup?: () => void }) => (
    <div id="mock-owner-login">
      {props.onSwitchToOwnerSetup && <button id="mock-owner-create" onClick={props.onSwitchToOwnerSetup}>Create Owner</button>}
    </div>
  ),
}));
vi.mock("../HelpRecoveryFlow", () => ({ HelpRecoveryFlow: () => <div id="mock-recovery" /> }));

let root: Root | null = null;
let container: HTMLDivElement | null = null;

async function mount(appRole?: "owner" | "user") {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(<SecureEntryApp appRole={appRole} />);
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
  vi.mocked(api.ownerBootstrapStatus).mockResolvedValue({
    owner_presence: "UNKNOWN",
    owner_setup_allowed: false,
    recommended_flow: "UNAVAILABLE",
    authority: "UNAVAILABLE",
    reason: "roaming authority unavailable",
  });
});

afterEach(async () => {
  if (root) await act(async () => root?.unmount());
  container?.remove();
  root = null;
  container = null;
});

describe("SecureEntryApp manual role parity", () => {
  it("opens the User package on the manual activation gate and never Owner setup", async () => {
    const node = await mount("user");
    expect(node.querySelector("#mock-activation")).not.toBeNull();
    expect(node.querySelector("#mock-owner-setup")).toBeNull();
    expect(node.querySelector("#mock-owner-login")).toBeNull();
  });

  it("keeps User returning login locked to USER role", async () => {
    const node = await mount("user");
    const activation = node.querySelector("#mock-activation");
    expect(activation).not.toBeNull();
  });

  it("opens Owner login even when remote/bootstrap authority is unavailable", async () => {
    const node = await mount("owner");
    expect(node.querySelector("#mock-owner-login")).not.toBeNull();
    expect(node.textContent).not.toContain("Account authority unavailable");
    expect(node.querySelector("#mock-owner-setup")).toBeNull();
  });

  it("shows first-run Owner creation only when explicitly authorized and still offers login", async () => {
    vi.mocked(api.ownerBootstrapStatus).mockResolvedValue({
      owner_presence: "ABSENT_CONFIRMED",
      owner_setup_allowed: true,
      recommended_flow: "LOCAL_OWNER_SETUP",
      authority: "EXPLICIT_LOCAL_BOOTSTRAP",
      reason: "trusted first bootstrap",
    });
    const node = await mount("owner");
    expect(node.querySelector("#mock-owner-setup")).not.toBeNull();
    const login = node.querySelector("#mock-owner-setup-login") as HTMLButtonElement;
    expect(login).not.toBeNull();
    await act(async () => login.click());
    expect(node.querySelector("#mock-owner-login")).not.toBeNull();
    const create = node.querySelector("#mock-owner-create") as HTMLButtonElement;
    expect(create).not.toBeNull();
  });

  it("preserves the generic shared gate behavior outside role-locked desktop packages", async () => {
    vi.mocked(api.ownerBootstrapStatus).mockResolvedValue({
      owner_presence: "LOCAL_EXISTS",
      owner_setup_allowed: false,
      recommended_flow: "RETURNING_USER",
      authority: "LOCAL",
      reason: "existing owner",
    });
    const node = await mount();
    expect(node.querySelector("#mock-returning")).not.toBeNull();
  });
});
