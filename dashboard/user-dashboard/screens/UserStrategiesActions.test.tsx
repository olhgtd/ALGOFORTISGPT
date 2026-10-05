import { afterEach, describe, expect, it, vi } from "vitest";
import { submitUserStrategy } from "../../shared/services/integrationClient";

afterEach(() => {
  vi.restoreAllMocks();
  delete (window as any).__ALGOFORTIS_ENABLE_BACKEND__;
  delete (window as any).__ALGOFORTIS_API_URL__;
});

describe("canonical user strategy mutation client", () => {
  it("posts exact strategy source and protective policy to canonical backend", async () => {
    (window as any).__ALGOFORTIS_ENABLE_BACKEND__ = true;
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      strategy_id: "strat-1",
      version_id: "v1",
      stage: "DRAFT",
      source_sha256: "abc",
    }), { status: 200, headers: { "Content-Type": "application/json" } }));

    const result = await submitUserStrategy("class Strategy {}", "POL-1");

    expect(result.success).toBe(true);
    expect(result.isFallback).toBe(false);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith("/api/v1/strategies", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        source: "class Strategy {}",
        protective_policy_identity: "POL-1",
      }),
    }));
  });

  it("fails closed on backend rejection without sample success", async () => {
    (window as any).__ALGOFORTIS_ENABLE_BACKEND__ = true;
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ detail: "strategy rejected" }), {
      status: 422,
      headers: { "Content-Type": "application/json" },
    }));

    const result = await submitUserStrategy("bad", null);

    expect(result.success).toBe(false);
    expect(result.isFallback).toBe(false);
    expect(result.error).toContain("strategy rejected");
  });
});
