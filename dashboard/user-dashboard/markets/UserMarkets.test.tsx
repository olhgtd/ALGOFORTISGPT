import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { UserMarkets } from "./UserMarkets";

let root: Root | null = null;
let container: HTMLDivElement | null = null;

afterEach(async () => {
  if (root) await act(async () => root?.unmount());
  container?.remove();
  root = null;
  container = null;
});

const candle = (time: string, close: number) => ({
  time,
  open: close - 10,
  high: close + 20,
  low: close - 20,
  close,
  volume: 1200,
});

const query = async (params: { instrument: string; timeframe: string; mode: "LIVE" | "FROZEN_HISTORICAL" | "BACKTEST"; limit?: number }) => ({
  state: "AVAILABLE" as const,
  instrument: params.instrument,
  timeframe: params.timeframe,
  mode: params.mode,
  candles: [candle("09:20", params.instrument === "NIFTY" ? 22000 : 48000), candle("09:25", params.instrument === "NIFTY" ? 22040 : 48030)],
});

describe("UserMarkets", () => {
  it("renders the canonical read-only Markets surface without sample option prices or order authority", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);

    await act(async () => {
      root?.render(<UserMarkets theme="dark" queryMarket={query} />);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.querySelector("[data-testid='markets-surface']")).not.toBeNull();
    expect(container.textContent).toContain("Markets");
    expect(container.textContent).toContain("NIFTY 50");
    expect(container.textContent).toContain("NIFTY BANK");
    expect(container.textContent).toContain("Option Chain");
    expect(container.textContent).toContain("UNAVAILABLE");
    expect(container.textContent).toContain("Generated or sample strikes are intentionally hidden");
    expect(container.textContent).not.toContain("BUY");
    expect(container.textContent).not.toContain("SELL");
    expect(container.textContent).not.toContain("DEV SAMPLE");
  });
});
