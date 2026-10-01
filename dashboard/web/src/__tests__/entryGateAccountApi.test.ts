import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, clearSessionToken, getSessionToken } from "../api";

function okJson(payload: unknown) {
  return Promise.resolve(new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "content-type": "application/json" },
  }));
}

describe("entry gate account API", () => {
  beforeEach(() => {
    clearSessionToken();
    vi.unstubAllGlobals();
  });

  it("posts only canonical activation fields", async () => {
    const fetchMock = vi.fn(() => okJson({ activated: true, authentication_required: true }));
    vi.stubGlobal("fetch", fetchMock);

    await api.passwordActivate({
      identifier: "AF-U-ABCD-2345",
      activation_code: "AF-ACT-AAAA-BBBB-CCCC",
      email: "user@example.com",
      password: "UserPassword123!",
      confirm_password: "UserPassword123!",
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/auth/password/activate");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      identifier: "AF-U-ABCD-2345",
      activation_code: "AF-ACT-AAAA-BBBB-CCCC",
      email: "user@example.com",
      password: "UserPassword123!",
      confirm_password: "UserPassword123!",
    });
  });

  it("posts only identifier and password for shared login", async () => {
    const fetchMock = vi.fn(() => okJson({
      access_token: "opaque-session",
      expires_at_utc: "2026-09-30T12:00:00+00:00",
      subject: "11111111-1111-1111-1111-111111111111",
      role: "USER",
      sx_id: "AF-U-ABCD-2345",
      workspace_eligibility: { owner: false, user: true },
    }));
    vi.stubGlobal("fetch", fetchMock);

    const result = await api.passwordLogin({
      identifier: "user@example.com",
      password: "UserPassword123!",
    });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/auth/password/login");
    expect(JSON.parse(String(init.body))).toEqual({
      identifier: "user@example.com",
      password: "UserPassword123!",
    });
    expect(result.role).toBe("USER");
    expect(result.workspace_eligibility).toEqual({ owner: false, user: true });
    expect("password" in result).toBe(false);
    expect("password_hash" in result).toBe(false);
    expect("password_salt" in result).toBe(false);
    // API transport never creates browser auth state by itself; the login UI
    // stores the returned token only after a successful role-derived response.
    expect(getSessionToken()).toBeNull();
  });
});
