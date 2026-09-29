import { describe, expect, it } from "vitest";
import { deriveMarketSnapshot, optionChainAuthority } from "./marketsModel";

const candle = (time: string, open: number, high: number, low: number, close: number, volume = 1000) => ({
  time, open, high, low, close, volume,
});

describe("marketsModel", () => {
  it("never invents numeric market values when chart authority is unavailable", () => {
    const snapshot = deriveMarketSnapshot("BACKEND_UNAVAILABLE", []);
    expect(snapshot.state).toBe("BACKEND_UNAVAILABLE");
    expect(snapshot.price).toBeNull();
    expect(snapshot.change).toBeNull();
    expect(snapshot.changePct).toBeNull();
    expect(snapshot.open).toBeNull();
    expect(snapshot.high).toBeNull();
    expect(snapshot.low).toBeNull();
    expect(snapshot.volume).toBeNull();
    expect(snapshot.asOf).toBeNull();
  });

  it("derives price and last-bar change only from canonical candles", () => {
    const snapshot = deriveMarketSnapshot("AVAILABLE", [
      candle("09:20", 22000, 22030, 21990, 22020, 1200),
      candle("09:25", 22020, 22070, 22010, 22060, 1800),
    ]);

    expect(snapshot.state).toBe("AVAILABLE");
    expect(snapshot.price).toBe(22060);
    expect(snapshot.change).toBe(40);
    expect(snapshot.changePct).toBeCloseTo((40 / 22020) * 100, 8);
    expect(snapshot.open).toBe(22020);
    expect(snapshot.high).toBe(22070);
    expect(snapshot.low).toBe(22010);
    expect(snapshot.volume).toBe(1800);
    expect(snapshot.asOf).toBe("09:25");
  });

  it("keeps stale canonical values visible and explicitly stale", () => {
    const snapshot = deriveMarketSnapshot("STALE", [
      candle("09:20", 22000, 22030, 21990, 22020, 1200),
      candle("09:25", 22020, 22070, 22010, 22060, 1800),
    ]);

    expect(snapshot.state).toBe("STALE");
    expect(snapshot.price).toBe(22060);
    expect(snapshot.asOf).toBe("09:25");
  });

  it("does not fabricate change when only one authoritative candle exists", () => {
    const snapshot = deriveMarketSnapshot("AVAILABLE", [candle("09:20", 22000, 22030, 21990, 22020)]);
    expect(snapshot.price).toBe(22020);
    expect(snapshot.change).toBeNull();
    expect(snapshot.changePct).toBeNull();
  });

  it("fails closed if an AVAILABLE payload contains an invalid latest candle", () => {
    const snapshot = deriveMarketSnapshot("AVAILABLE", [candle("09:20", 22000, 22030, 21990, Number.NaN)]);
    expect(snapshot.state).toBe("ERROR");
    expect(snapshot.price).toBeNull();
  });

  it("keeps option-chain sample generation out of the finished Markets surface", () => {
    expect(optionChainAuthority.state).toBe("UNAVAILABLE");
    expect(optionChainAuthority.sampleFallbackAllowed).toBe(false);
    expect(optionChainAuthority.orderAuthority).toBe(false);
  });
});
