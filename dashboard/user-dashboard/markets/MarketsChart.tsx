import React, { useEffect, useMemo, useState } from "react";
import type { MarketChartMode } from "../../shared/services/integrationClient";
import { deriveProfessionalChartQuote } from "../../shared/components/professionalChartTruth";
import { queryUserMarketChart, type UserMarketChartResult } from "../data/userMarketAuthority";
import { MARKET_INSTRUMENTS, marketStateLabel, type MarketInstrumentId, type MarketsAuthorityState } from "./marketsModel";

type MarketQuery = typeof queryUserMarketChart;
type ChartTimeframe = "1m" | "5m" | "15m" | "1H" | "1d";

const TIMEFRAMES: readonly ChartTimeframe[] = ["1m", "5m", "15m", "1H", "1d"];

export interface MarketsChartProps {
  instrument: MarketInstrumentId;
  theme: "dark" | "light";
  queryMarket?: MarketQuery;
}

const loadingResult = (instrument: string, timeframe: string, mode: MarketChartMode): UserMarketChartResult => ({
  state: "LOADING",
  instrument,
  timeframe,
  mode,
  candles: [],
});

const formatNumber = (value: number | null, digits = 2) => value === null
  ? "—"
  : value.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });

const formatSigned = (value: number | null, digits = 2) => {
  if (value === null) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
};

const authorityClass = (state: MarketsAuthorityState): string =>
  state === "AVAILABLE" ? "available" : state === "STALE" ? "stale" : state === "LOADING" ? "unknown" : "unavailable";

export const MarketsChart: React.FC<MarketsChartProps> = ({ instrument, theme, queryMarket = queryUserMarketChart }) => {
  const [timeframe, setTimeframe] = useState<ChartTimeframe>("5m");
  const [mode, setMode] = useState<MarketChartMode>("LIVE");
  const [result, setResult] = useState<UserMarketChartResult>(() => loadingResult(instrument, timeframe, mode));

  useEffect(() => {
    let active = true;
    setResult(loadingResult(instrument, timeframe, mode));
    queryMarket({ instrument, timeframe, mode, limit: 160 })
      .then((next) => { if (active) setResult(next); })
      .catch(() => {
        if (active) setResult({ state: "BACKEND_UNAVAILABLE", instrument, timeframe, mode, candles: [] });
      });
    return () => { active = false; };
  }, [instrument, timeframe, mode, queryMarket]);

  const meta = MARKET_INSTRUMENTS.find((item) => item.id === instrument) ?? MARKET_INSTRUMENTS[0];
  const state: MarketsAuthorityState = result.state;
  const quote = deriveProfessionalChartQuote(state, result.candles);
  const candles = useMemo(() => result.candles.slice(-90), [result.candles]);
  const latest = candles[candles.length - 1] ?? null;

  const geometry = useMemo(() => {
    if ((state !== "AVAILABLE" && state !== "STALE") || candles.length === 0) return null;
    const highs = candles.map((c) => c.high).filter(Number.isFinite);
    const lows = candles.map((c) => c.low).filter(Number.isFinite);
    if (highs.length !== candles.length || lows.length !== candles.length) return null;
    const max = Math.max(...highs);
    const min = Math.min(...lows);
    const range = Math.max(max - min, 1);
    const maxVolume = Math.max(...candles.map((c) => Number.isFinite(c.volume) ? Number(c.volume) : 0), 1);
    return { max, min, range, maxVolume };
  }, [candles, state]);

  const changeTone = quote.change === null ? "neutral" : quote.change > 0 ? "positive" : quote.change < 0 ? "negative" : "neutral";

  return (
    <section className="af-markets-chart" data-testid="markets-chart" data-theme={theme}>
      <div className="af-markets-chart-head">
        <div>
          <span className="af-eyebrow">Canonical Chart</span>
          <div className="af-markets-chart-title-row">
            <h2>{meta.label}</h2>
            <span className="af-markets-exchange">{meta.exchange}</span>
            <span className={`af-authority af-authority-${authorityClass(state)}`}>{marketStateLabel(state)}</span>
          </div>
          <div className="af-markets-chart-quote">
            <strong>{formatNumber(quote.price)}</strong>
            <span className={`af-market-tone-${changeTone}`}>
              {formatSigned(quote.change)} {quote.changePct === null ? "" : `(${formatSigned(quote.changePct)}%)`}
            </span>
          </div>
          {state === "STALE" && <p className="af-markets-note">STALE — canonical values are shown for context only and are not promoted to fresh market truth.</p>}
        </div>

        <div className="af-markets-chart-controls">
          <div className="af-markets-segment" role="tablist" aria-label="Market timeframe">
            {TIMEFRAMES.map((item) => (
              <button key={item} type="button" className={timeframe === item ? "active" : ""} onClick={() => setTimeframe(item)}>{item}</button>
            ))}
          </div>
          <button type="button" className="af-markets-mode-button" onClick={() => setMode((current) => current === "LIVE" ? "FROZEN_HISTORICAL" : "LIVE")}>
            {mode === "LIVE" ? "Live read" : "Frozen history"}
          </button>
        </div>
      </div>

      <div className="af-markets-chart-hud">
        <span>TIME <b>{latest?.time ?? "—"}</b></span>
        <span>O <b>{latest ? formatNumber(latest.open) : "—"}</b></span>
        <span>H <b>{latest ? formatNumber(latest.high) : "—"}</b></span>
        <span>L <b>{latest ? formatNumber(latest.low) : "—"}</b></span>
        <span>C <b>{latest ? formatNumber(latest.close) : "—"}</b></span>
        <span>VOL <b>{latest && Number.isFinite(latest.volume) ? Number(latest.volume).toLocaleString("en-IN") : "—"}</b></span>
      </div>

      <div className="af-markets-chart-stage">
        {geometry ? (
          <svg viewBox="0 0 1000 360" preserveAspectRatio="none" role="img" aria-label={`${meta.label} authoritative candlestick chart`}>
            <g className="af-chart-grid">
              {[0, 1, 2, 3, 4].map((i) => <line key={`h-${i}`} x1="0" x2="1000" y1={40 + i * 62} y2={40 + i * 62} />)}
              {[1, 2, 3, 4, 5].map((i) => <line key={`v-${i}`} x1={i * 166.66} x2={i * 166.66} y1="20" y2="330" />)}
            </g>
            {candles.map((candle, index) => {
              const x = 12 + index * (976 / Math.max(candles.length, 1));
              const step = 976 / Math.max(candles.length, 1);
              const width = Math.max(2.2, Math.min(7, step * 0.58));
              const priceY = (value: number) => 24 + ((geometry.max - value) / geometry.range) * 252;
              const openY = priceY(candle.open);
              const closeY = priceY(candle.close);
              const highY = priceY(candle.high);
              const lowY = priceY(candle.low);
              const up = candle.close >= candle.open;
              const bodyY = Math.min(openY, closeY);
              const bodyH = Math.max(1.8, Math.abs(openY - closeY));
              const volumeH = (Number(candle.volume ?? 0) / geometry.maxVolume) * 54;
              return (
                <g key={`${candle.time}-${index}`} className={up ? "af-candle-up" : "af-candle-down"}>
                  <line x1={x} x2={x} y1={highY} y2={lowY} className="af-candle-wick" />
                  <rect x={x - width / 2} y={bodyY} width={width} height={bodyH} className="af-candle-body" />
                  <rect x={x - width / 2} y={330 - volumeH} width={width} height={volumeH} className="af-candle-volume" />
                </g>
              );
            })}
          </svg>
        ) : (
          <div className="af-markets-chart-empty" role="status">
            <strong>{marketStateLabel(state)}</strong>
            <span>{result.detail || (state === "LOADING" ? "Loading authoritative candles…" : "No synthetic or sample candles are shown when canonical data is unavailable.")}</span>
          </div>
        )}
      </div>
    </section>
  );
};
