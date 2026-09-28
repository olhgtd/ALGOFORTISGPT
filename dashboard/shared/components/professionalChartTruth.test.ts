import { describe, expect, it } from "vitest";
import { deriveProfessionalChartQuote } from "./professionalChartTruth";

const candle = (time: string, open: number, close: number) => ({
  time,
  open,
  high: Math.max(open, close) + 10,
  low: Math.min(open, close) - 10,
  close,
  volume: 1000,
});

describe("professionalChartTruth", () => {
  it("returns no numeric quote when canonical chart authority is unavailable", () => {
    expect(deriveProfessionalChartQuote("BACKEND_UNAVAILABLE", [])).toEqual({
      price: null,
      change: null,
      changePct: null,
    });
  });

  it("derives the displayed quote from canonical candles only", () => {
    const quote = deriveProfessionalChartQuote("AVAILABLE", [
      candle("09:20", 22000, 22020),
      candle("09:25", 22020, 22060),
    ]);
    expect(quote.price).toBe(22060);
    expect(quote.change).toBe(40);
    expect(quote.changePct).toBeCloseTo((40 / 22020) * 100, 8);
  });

  it("does not fabricate a zero change with only one candle", () => {
    const quote = deriveProfessionalChartQuote("AVAILABLE", [candle("09:20", 22000, 22020)]);
    expect(quote.price).toBe(22020);
    expect(quote.change).toBeNull();
    expect(quote.changePct).toBeNull();
  });
});
