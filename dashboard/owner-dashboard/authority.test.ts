import { describe, expect, it } from "vitest";
import {
  authoritativeCount,
  authorityDisplayValue,
  toAuthorityEnvelope,
  toAuthorityState,
} from "./authority";

describe("Owner authority truth", () => {
  it("maps backend freshness without guessing", () => {
    expect(toAuthorityState("BACKEND", "FRESH")).toBe("AVAILABLE");
    expect(toAuthorityState("BACKEND", "STALE")).toBe("STALE");
    expect(toAuthorityState("BACKEND", "UNKNOWN")).toBe("UNKNOWN");
    expect(toAuthorityState("UNAVAILABLE", "UNKNOWN")).toBe("UNAVAILABLE");
    expect(toAuthorityState("SAMPLE_FALLBACK", "UNKNOWN")).toBe("UNKNOWN");
  });

  it("never presents unavailable count as zero", () => {
    const unavailable = toAuthorityEnvelope({
      source: "UNAVAILABLE",
      trust: "UNKNOWN",
      asOf: "2026-09-29T00:00:00Z",
      data: [] as unknown[],
      error: "BACKEND_AUTHORITY_UNAVAILABLE",
    });
    const availableEmpty = toAuthorityEnvelope({
      source: "BACKEND",
      trust: "FRESH",
      asOf: "2026-09-29T00:00:00Z",
      data: [] as unknown[],
    });

    expect(authoritativeCount(unavailable, (rows) => rows.length)).toBeNull();
    expect(authorityDisplayValue(authoritativeCount(unavailable, (rows) => rows.length))).toBe("—");
    expect(authoritativeCount(availableEmpty, (rows) => rows.length)).toBe(0);
    expect(authorityDisplayValue(authoritativeCount(availableEmpty, (rows) => rows.length))).toBe("0");
  });
});
