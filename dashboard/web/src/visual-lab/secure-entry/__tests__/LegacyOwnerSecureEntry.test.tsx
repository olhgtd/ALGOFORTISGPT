import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LegacyUserSecureEntryApp } from "../LegacyUserSecureEntryApp";
import { api } from "../../../api";

vi.mock("../../../api", () => ({
  api: {
    securityStatus: vi.fn(),
    ownerBootstrapStatus: vi.fn(),
  },
}));

vi.mock("../LegacyEntryShell", () => ({
  LegacyEntryShell: ({ children }: { children: React.ReactNode }) => <div id="legacy-shell">{children}</div>,
}));
vi.mock("../LegacyUserFirstTimeCustomerFlow", () => ({ LegacyUserFirstTimeCustomerFlow: () => <div id="mock-user-flow" /> }));
vi.mock("../LocalOwnerSetupCard", () => ({
  LocalOwnerSetupCard: (props: { onSwitchToLogin?: () => void }) => (
    <div id="mock-owner-setup">
      {props.onSwitchToLogin && <button id="mock-owner-setup-login" onClick={props.onSwitchToLogin}>Sign In</button>}
    </div>
  ),
}));
vi.mock("../LegacyUserLoginCard", () => ({
  LegacyUserLoginCard: (props: { onForgotPassword?: () => void }) => (
    <div id="mock-owner-login">
      {props.onForgotPassword && <button id="mock-owner-forgot" onClick={props.onForgotPassword}>Forgot password?</button>}
    </div>
  ),
}));
vi.mock("../LegacyLocalRecoveryCard", () => ({ LegacyLocalRecoveryCard: () => <div id="mock-owner-recovery" /> }));

let root: Root | null = null;
let container: HTMLDivElement | null = null;

async function mountOwner() {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root?.render(<LegacyUserSecureEntryApp appTarget="owner" />);
    await Promise.resolve();
    await Promise.resolve();
  });
  return container;
}

beforeEach(() => {
  vi.mocked(api.securityStatus).mockResolvedValue({
    password_authentication: "PENDING_SETUP",
    owner_initialized: false,
    webauthn: "NOT_CONFIGURED",
    webauthn_enrollment: "NOT_CONFIGURED",
    normal_mtls: "NOT_CONFIGURED",
    break_glass: "NOT_CONFIGURED",
    owner_authenticators_ready: false,
    normal_mtls_required: false,
  });
  vi.mocked(api.ownerBootstrapStatus).mockResolvedValue({
    owner_presence: "ABSENT_CONFIRMED",
    owner_setup_allowed: true,
    recommended_flow: "LOCAL_OWNER_SETUP",
    authority: "EXPLICIT_LOCAL_BOOTSTRAP",
    reason: "trusted first bootstrap",
  });
});

afterEach(async () => {
  if (root) await act(async () => root?.unmount());
  container?.remove();
  root = null;
  container = null;
});

describe("legacy Owner entry route", () => {
  it("shows donor Owner setup with a Sign In escape on first-run", async () => {
    const node = await mountOwner();
    expect(node.querySelector("#mock-owner-setup")).not.toBeNull();
    const login = node.querySelector("#mock-owner-setup-login") as HTMLButtonElement;
    expect(login).not.toBeNull();
    await act(async () => login.click());
    expect(node.querySelector("#mock-owner-login")).not.toBeNull();
  });

  it("keeps Owner login reachable when bootstrap authority does not allow creation", async () => {
    vi.mocked(api.ownerBootstrapStatus).mockResolvedValue({
      owner_presence: "REMOTE_EXISTS",
      owner_setup_allowed: false,
      recommended_flow: "LOCAL_LOGIN",
      authority: "REMOTE",
      reason: "existing owner",
    });
    const node = await mountOwner();
    expect(node.querySelector("#mock-owner-login")).not.toBeNull();
    expect(node.querySelector("#mock-owner-setup")).toBeNull();
  });

  it("restores donor Forgot Password to emergency recovery", async () => {
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
      owner_presence: "LOCAL_EXISTS",
      owner_setup_allowed: false,
      recommended_flow: "LOCAL_LOGIN",
      authority: "LOCAL",
      reason: "existing owner",
    });
    const node = await mountOwner();
    const forgot = node.querySelector("#mock-owner-forgot") as HTMLButtonElement;
    expect(forgot).not.toBeNull();
    await act(async () => forgot.click());
    expect(node.querySelector("#mock-owner-recovery")).not.toBeNull();
  });
});
