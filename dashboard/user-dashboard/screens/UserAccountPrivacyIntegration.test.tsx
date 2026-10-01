import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { UserAccount } from "./UserAccount";

let root: Root | null = null;
let container: HTMLDivElement | null = null;

afterEach(async () => {
  if (root) await act(async () => root?.unmount());
  container?.remove();
  root = null;
  container = null;
});

describe("UserAccount privacy integration", () => {
  it("keeps Privacy & Requests inside Account instead of creating a top-level user destination", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root?.render(<UserAccount
        loadData={async () => ({
          profile: { state: "UNAVAILABLE" as const, data: null, asOf: null },
          connections: { state: "UNAVAILABLE" as const, data: [], asOf: null },
        })}
        loadPrivacyData={async () => ({
          state: "AVAILABLE" as const,
          asOf: null,
          data: {
            notice_policy_ref: "privacy-notice/1.0.0",
            notice_fingerprint: "a".repeat(64),
            consent_state: "GRANTED",
            request_statuses: [["ACCESS-1", "IN_PROGRESS"]],
          },
        })}
      />);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(container.querySelector("[data-testid='account-surface']")).not.toBeNull();
    expect(container.querySelector("[data-testid='privacy-requests-surface']")).not.toBeNull();
    expect(container.textContent).toContain("Privacy & Requests");
  });
});
