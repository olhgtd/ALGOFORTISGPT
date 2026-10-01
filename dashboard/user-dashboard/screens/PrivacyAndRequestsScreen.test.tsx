import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { PrivacyAndRequestsScreen } from "./PrivacyAndRequestsScreen";

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

describe("PrivacyAndRequestsScreen", () => {
  it("renders notice, consent and request status as read-only privacy evidence", async () => {
    const node = await mount(<PrivacyAndRequestsScreen loadData={async () => ({
      state: "AVAILABLE" as const,
      asOf: "2026-10-01T12:00:00Z",
      data: {
        notice_policy_ref: "privacy-notice/1.0.0",
        notice_fingerprint: "a".repeat(64),
        consent_state: "GRANTED",
        request_statuses: [["ACCESS-1", "IN_PROGRESS"], ["GRIEVANCE-1", "RECEIVED"]],
      },
    })} />);
    expect(node.querySelector("[data-testid='privacy-requests-surface']")).not.toBeNull();
    expect(node.textContent).toContain("Privacy & Requests");
    expect(node.textContent).toContain("privacy-notice/1.0.0");
    expect(node.textContent).toContain("GRANTED");
    expect(node.textContent).toContain("ACCESS-1");
    expect(node.textContent).toContain("IN_PROGRESS");
    expect(node.textContent).not.toContain("broker secret");
    expect(node.textContent).not.toContain("Arm Live");
  });

  it("does not fabricate consent or request status when privacy authority is unavailable", async () => {
    const node = await mount(<PrivacyAndRequestsScreen loadData={async () => ({
      state: "UNAVAILABLE" as const,
      asOf: null,
      data: null,
    })} />);
    expect(node.textContent).toContain("UNAVAILABLE");
    expect(node.textContent).not.toContain("GRANTED");
    expect(node.textContent).not.toContain("No requests");
  });
});
