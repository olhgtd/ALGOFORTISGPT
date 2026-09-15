import React, { useEffect, useRef, useState, useCallback } from "react";
import { Icon } from "../icons/V3Icons";
import { TruthChip, fmtSignedINR, fmtSignedPct } from "../utilities/V3Chrome";
import { type ProCandle, type UnderlyingConfig, UNDERLYINGS } from "../data";
import { queryMarketChart, type MarketChartState } from "../services/integrationClient";
import type { SelectedOptionContract } from "../../user-dashboard/data";

export interface ProfessionalChartProps {
  underlying: string;
  selectedContract: SelectedOptionContract | null;
  chartTarget: "underlying" | "contract";
  onToggleTarget: (target: "underlying" | "contract") => void;
  onOpenOptionChain?: () => void;
  theme?: "dark" | "light";
}

const TIMEFRAMES = ["1m", "5m", "15m", "1h", "1d"] as const;
type Timeframe = (typeof TIMEFRAMES)[number];

const PADDING = { top: 28, right: 76, bottom: 26, left: 16 };
const VOLUME_HEIGHT_RATIO = 0.16;

export const ProfessionalChart: React.FC<ProfessionalChartProps> = ({
  underlying,
  selectedContract,
  chartTarget,
  onToggleTarget,
  onOpenOptionChain,
  theme,
}) => {
  const [timeframe, setTimeframe] = useState<Timeframe>("5m");
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [crosshairPos, setCrosshairPos] = useState<{ x: number; y: number } | null>(null);
  const [mode, setMode] = useState<"LIVE" | "HISTORICAL">("LIVE");
  const [themeTick, setThemeTick] = useState(0);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const underlyingCfg: UnderlyingConfig = UNDERLYINGS[underlying] || UNDERLYINGS.NIFTY;

  // F-8: candles resolve ONLY through the backend canonical data service.
  // No synthetic/demo/sample candles are ever generated in production.
  const [candles, setCandles] = useState<ProCandle[]>([]);
  const [chartState, setChartState] = useState<MarketChartState>("LOADING");
  const [chartDetail, setChartDetail] = useState<string | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    // Contract-level history has no authoritative source; report honestly.
    if (chartTarget === "contract") {
      setCandles([]);
      setChartState("NO_DATA");
      setChartDetail("Contract-level history is unavailable from the canonical data service.");
      return () => { cancelled = true; };
    }
    setChartState("LOADING");
    setChartDetail(undefined);
    const backendTimeframe = timeframe === "1h" ? "1H" : timeframe;
    queryMarketChart({
      instrument: underlying,
      timeframe: backendTimeframe,
      mode: mode === "LIVE" ? "LIVE" : "FROZEN_HISTORICAL",
      limit: 500,
    }).then((result) => {
      if (cancelled) return;
      setChartState(result.state);
      setChartDetail(result.detail);
      setCandles(
        result.candles.map((c) => ({
          time: c.time,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
          volume: typeof c.volume === "number" ? c.volume : 0,
        }))
      );
    }).catch(() => {
      if (cancelled) return;
      setChartState("BACKEND_UNAVAILABLE");
      setChartDetail(undefined);
      setCandles([]);
    });
    return () => { cancelled = true; };
  }, [underlying, timeframe, mode, chartTarget]);

  // Active chart title & price info
  const isContractView = chartTarget === "contract" && selectedContract !== null;
  
  const displayTitle = isContractView
    ? `${selectedContract.underlying} ${selectedContract.expiry} ${selectedContract.strike} ${selectedContract.optionType}`
    : `${underlyingCfg.name} (SPOT)`;

  const displayExchange = isContractView ? "NFO" : underlyingCfg.exchange;

  const currentPrice = isContractView ? selectedContract.ltp : underlyingCfg.spot;
  const currentChg = isContractView ? selectedContract.change : underlyingCfg.change;
  const currentChgPct = isContractView ? selectedContract.changePct : underlyingCfg.changePct;
  const isPos = currentChg >= 0;

  // Generate realistic candles based on instrument, target & timeframe
  const activeCandle = hoverIndex !== null && candles[hoverIndex] ? candles[hoverIndex] : candles[candles.length - 1];
  // Authoritative reference price: last canonical close when available, else static config display.
  const effectivePrice = chartState === "AVAILABLE" && candles.length > 0 ? candles[candles.length - 1].close : currentPrice;
  const candleChg = activeCandle ? activeCandle.close - activeCandle.open : 0;
  const candleChgPct = activeCandle && activeCandle.open > 0 ? (candleChg / activeCandle.open) * 100 : 0;

  // Render chart on canvas with theme-awareness
  const renderCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;

    if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
      canvas.width = width * dpr;
      canvas.height = height * dpr;
    }

    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    // Determine current theme colors
    const isLight =
      theme === "light" ||
      (typeof document !== "undefined" &&
        (document.documentElement.getAttribute("data-theme") === "light" ||
          document.querySelector(".v3-root")?.getAttribute("data-theme") === "light"));

    const bgCanvas = isLight ? "#ffffff" : "#070a0f";
    const gridStroke = isLight ? "#e2e8f0" : "#131b26";
    const textFill = isLight ? "#64748b" : "#50627a";
    const bullColor = isLight ? "#059669" : "#10b981";
    const bearColor = isLight ? "#dc2626" : "#ef4444";
    const bullVol = isLight ? "rgba(5, 150, 105, 0.22)" : "rgba(16, 185, 129, 0.22)";
    const bearVol = isLight ? "rgba(220, 38, 38, 0.22)" : "rgba(239, 68, 68, 0.22)";
    const crosshairStroke = isLight ? "rgba(2, 132, 199, 0.75)" : "rgba(56, 189, 248, 0.6)";
    const tagBg = isLight ? "#ffffff" : "#1e293b";
    const tagBorder = isLight ? "#cbd5e1" : "#38bdf8";
    const tagText = isLight ? "#0f172a" : "#f0f4f8";

    // Deep canvas background
    ctx.fillStyle = bgCanvas;
    ctx.fillRect(0, 0, width, height);

    if (!candles || candles.length === 0) {
      ctx.restore();
      return;
    }

    const chartWidth = width - PADDING.left - PADDING.right;
    const volumeHeight = height * VOLUME_HEIGHT_RATIO;
    const priceHeight = height - PADDING.top - PADDING.bottom - volumeHeight;

    const count = candles.length;
    const barWidth = Math.max(4, chartWidth / count);
    const candleWidth = Math.max(2, barWidth * 0.65);

    // Compute price min / max
    let pMin = Infinity;
    let pMax = -Infinity;
    let vMax = 0;

    candles.forEach((c) => {
      if (c.low < pMin) pMin = c.low;
      if (c.high > pMax) pMax = c.high;
      if (c.volume > vMax) vMax = c.volume;
    });

    const pPad = (pMax - pMin) * 0.08 || 1;
    pMin -= pPad;
    pMax += pPad;
    const pRange = pMax - pMin || 1;
    vMax = vMax || 1;

    const yPrice = (p: number) => PADDING.top + priceHeight * (1 - (p - pMin) / pRange);
    const yVolume = (v: number) => height - PADDING.bottom - (v / vMax) * volumeHeight;
    const xBar = (i: number) => PADDING.left + (i + 0.5) * barWidth;

    // Grid lines & Price Axis labels
    ctx.strokeStyle = gridStroke;
    ctx.lineWidth = 1;
    ctx.font = "10.5px 'JetBrains Mono', monospace";
    ctx.textAlign = "left";

    const priceSteps = 5;
    for (let i = 0; i <= priceSteps; i++) {
      const p = pMin + (pRange * i) / priceSteps;
      const y = yPrice(p);

      ctx.beginPath();
      ctx.moveTo(PADDING.left, y);
      ctx.lineTo(width - PADDING.right, y);
      ctx.stroke();

      ctx.fillStyle = textFill;
      ctx.fillText(p >= 1000 ? p.toFixed(1) : p.toFixed(2), width - PADDING.right + 8, y + 3.5);
    }

    // Time Axis labels
    ctx.textAlign = "center";
    const labelStep = Math.max(1, Math.floor(count / 6));
    for (let i = 0; i < count; i += labelStep) {
      const x = xBar(i);
      ctx.beginPath();
      ctx.moveTo(x, PADDING.top);
      ctx.lineTo(x, height - PADDING.bottom);
      ctx.stroke();

      ctx.fillStyle = textFill;
      ctx.fillText(candles[i].time, x, height - 8);
    }

    // Draw Volume Bars
    candles.forEach((c, i) => {
      const isUp = c.close >= c.open;
      const x = xBar(i);
      const yTop = yVolume(c.volume);
      const yBottom = height - PADDING.bottom;

      ctx.fillStyle = isUp ? bullVol : bearVol;
      ctx.fillRect(x - candleWidth / 2, yTop, candleWidth, yBottom - yTop);
    });

    // Draw Candlesticks (Green = Bullish, Red = Bearish)
    candles.forEach((c, i) => {
      const isUp = c.close >= c.open;
      const color = isUp ? bullColor : bearColor;
      const x = xBar(i);

      const yO = yPrice(c.open);
      const yC = yPrice(c.close);
      const yH = yPrice(c.high);
      const yL = yPrice(c.low);

      // Wick
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.moveTo(x, yH);
      ctx.lineTo(x, yL);
      ctx.stroke();

      // Body
      ctx.fillStyle = color;
      const bodyTop = Math.min(yO, yC);
      const bodyHeight = Math.max(1.5, Math.abs(yO - yC));
      ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
    });

    // Current LTP reference line
    const ltpY = yPrice(effectivePrice);
    ctx.strokeStyle = isPos ? (isLight ? "rgba(5, 150, 105, 0.65)" : "rgba(16, 185, 129, 0.65)") : (isLight ? "rgba(220, 38, 38, 0.65)" : "rgba(239, 68, 68, 0.65)");
    ctx.setLineDash([3, 4]);
    ctx.beginPath();
    ctx.moveTo(PADDING.left, ltpY);
    ctx.lineTo(width - PADDING.right, ltpY);
    ctx.stroke();
    ctx.setLineDash([]);

    // Live Price Pill on Right Axis
    ctx.fillStyle = isPos ? bullColor : bearColor;
    ctx.fillRect(width - PADDING.right + 2, ltpY - 9, PADDING.right - 6, 18);
    ctx.fillStyle = "#ffffff";
    ctx.font = "bold 10.5px 'JetBrains Mono', monospace";
    ctx.textAlign = "left";
    ctx.fillText(effectivePrice >= 1000 ? effectivePrice.toFixed(1) : effectivePrice.toFixed(2), width - PADDING.right + 6, ltpY + 3.5);

    // Draw Crosshair (if active)
    if (crosshairPos && hoverIndex !== null) {
      const x = xBar(hoverIndex);
      const y = crosshairPos.y;

      ctx.strokeStyle = crosshairStroke;
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 3]);

      // Vertical line
      ctx.beginPath();
      ctx.moveTo(x, PADDING.top);
      ctx.lineTo(x, height - PADDING.bottom);
      ctx.stroke();

      // Horizontal line
      if (y >= PADDING.top && y <= height - PADDING.bottom) {
        ctx.beginPath();
        ctx.moveTo(PADDING.left, y);
        ctx.lineTo(width - PADDING.right, y);
        ctx.stroke();

        // Price Tag on Right Axis
        const hoveredPrice = pMax - ((y - PADDING.top) / priceHeight) * pRange;
        ctx.fillStyle = tagBg;
        ctx.fillRect(width - PADDING.right + 2, y - 8, PADDING.right - 6, 16);
        ctx.strokeStyle = tagBorder;
        ctx.strokeRect(width - PADDING.right + 2, y - 8, PADDING.right - 6, 16);
        ctx.fillStyle = tagText;
        ctx.font = "10px 'JetBrains Mono', monospace";
        ctx.textAlign = "left";
        ctx.fillText(hoveredPrice >= 1000 ? hoveredPrice.toFixed(1) : hoveredPrice.toFixed(2), width - PADDING.right + 6, y + 3.5);
      }
      ctx.setLineDash([]);
    }

    ctx.restore();
  }, [candles, crosshairPos, hoverIndex, effectivePrice, isPos, theme, themeTick]);

  // Redraw when dimensions, candles, or theme change
  useEffect(() => {
    renderCanvas();
    const handleResize = () => renderCanvas();
    window.addEventListener("resize", handleResize);

    // Observer for theme changes on root element
    const observer = new MutationObserver(() => {
      setThemeTick((t) => t + 1);
    });
    if (typeof document !== "undefined") {
      observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
      const rootEl = document.querySelector(".v3-root");
      if (rootEl) observer.observe(rootEl, { attributes: true, attributeFilter: ["data-theme"] });
    }

    return () => {
      window.removeEventListener("resize", handleResize);
      observer.disconnect();
    };
  }, [renderCanvas]);

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas || candles.length === 0) return;
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    const chartWidth = canvas.clientWidth - PADDING.left - PADDING.right;
    const barWidth = chartWidth / candles.length;
    const index = Math.floor((x - PADDING.left) / barWidth);

    if (index >= 0 && index < candles.length) {
      setHoverIndex(index);
      setCrosshairPos({ x, y });
    } else {
      setHoverIndex(null);
      setCrosshairPos(null);
    }
  };

  const handleMouseLeave = () => {
    setHoverIndex(null);
    setCrosshairPos(null);
  };

  return (
    <div className="v3-pro-chart" ref={containerRef}>
      {/* ── Top Bar: Title, Context, Price, Timeframes, Actions ── */}
      <div className="v3-chart-topbar">
        <div className="v3-chart-inst-group">
          <span className="v3-chart-inst-name">{displayTitle}</span>
          <span className="v3-chart-exchange">{displayExchange}</span>

          {isContractView ? (
            <span
              className={
                selectedContract.moneyness === "ATM"
                  ? "v3-atm-badge"
                  : selectedContract.moneyness === "ITM"
                  ? "v3-itm-badge"
                  : "v3-otm-badge"
              }
            >
              {selectedContract.optionType} · {selectedContract.moneyness}
            </span>
          ) : (
            <span className="v3-itm-badge">SPOT INDEX</span>
          )}

          <div className="v3-chart-ltp-box">
            <span className="v3-chart-ltp">₹{effectivePrice.toFixed(2)}</span>
            <span className={`v3-chart-change ${isPos ? "v3-profit-text" : "v3-loss-text"}`}>
              {fmtSignedINR(currentChg, 2)} ({fmtSignedPct(currentChgPct)})
            </span>
          </div>
        </div>

        <div className="v3-chart-controls">
          {/* Target toggle: Underlying vs Option Contract */}
          {selectedContract && (
            <div className="v3-inst-select-group" style={{ marginRight: 6 }}>
              <button
                className={`v3-inst-btn ${chartTarget === "underlying" ? "active" : ""}`}
                onClick={() => onToggleTarget("underlying")}
                title="View underlying index spot chart"
              >
                Index Chart
              </button>
              <button
                className={`v3-inst-btn ${chartTarget === "contract" ? "active" : ""}`}
                onClick={() => onToggleTarget("contract")}
                title={`View ${selectedContract.strike} ${selectedContract.optionType} chart`}
              >
                {selectedContract.strike} {selectedContract.optionType}
              </button>
            </div>
          )}

          {/* Timeframe switchers */}
          <div className="v3-timeframe-group" role="tablist" aria-label="Timeframe selector">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf}
                role="tab"
                aria-selected={timeframe === tf}
                className={`v3-tf-btn ${timeframe === tf ? "active" : ""}`}
                onClick={() => setTimeframe(tf)}
              >
                {tf}
              </button>
            ))}
          </div>

          {/* Option Chain Launcher Button */}
          {onOpenOptionChain && (
            <button className="v3-btn ghost mini" onClick={onOpenOptionChain} title="Open Strike Ladder / Option Chain">
              <Icon name="layers" size={13} /> Option Chain
            </button>
          )}

          {/* Mode Pill — reflects authoritative backend chart state, never sample data */}
          <button
            className={`v3-chip ${chartState === "AVAILABLE" ? "real" : "disabled"}`}
            onClick={() => setMode((m) => (m === "LIVE" ? "HISTORICAL" : "LIVE"))}
            title={chartDetail || `Backend chart state: ${chartState}`}
          >
            {chartState === "LOADING"
              ? "LOADING"
              : chartState === "AVAILABLE"
              ? mode === "LIVE" ? "LIVE · BACKEND" : "FROZEN HISTORICAL · BACKEND"
              : chartState === "NO_DATA"
              ? "NO DATA"
              : chartState === "DATA_PROVIDER_NOT_CONFIGURED"
              ? "DATA PROVIDER NOT CONFIGURED"
              : chartState === "BACKEND_UNAVAILABLE"
              ? "BACKEND UNAVAILABLE"
              : "CHART ERROR"}
          </button>
          <TruthChip
            kind={chartState === "AVAILABLE" ? "REAL" : "DISABLED"}
            title={
              chartState === "AVAILABLE"
                ? "Authoritative backend candles — canonical data service."
                : `No authoritative candles (${chartState}). No synthetic data is ever shown.`
            }
          />
        </div>
      </div>

      {/* ── Dynamic OHLC & Volume HUD Overlay ── */}
      <div className="v3-chart-hud">
        <span className="v3-hud-item">
          TIME: <b>{activeCandle?.time ?? "—"}</b>
        </span>
        <span className="v3-hud-item">
          O: <b>₹{activeCandle?.open.toFixed(2) ?? "—"}</b>
        </span>
        <span className="v3-hud-item">
          H: <b>₹{activeCandle?.high.toFixed(2) ?? "—"}</b>
        </span>
        <span className="v3-hud-item">
          L: <b>₹{activeCandle?.low.toFixed(2) ?? "—"}</b>
        </span>
        <span className="v3-hud-item">
          C: <b>₹{activeCandle?.close.toFixed(2) ?? "—"}</b>
        </span>
        <span className={`v3-hud-item ${candleChg >= 0 ? "v3-profit-text" : "v3-loss-text"}`}>
          CHG: <b>{fmtSignedINR(candleChg, 2)} ({fmtSignedPct(candleChgPct)})</b>
        </span>
        <span className="v3-hud-item">
          VOL: <b>{activeCandle?.volume.toLocaleString() ?? "—"}</b>
        </span>
      </div>

      {/* ── High-DPI Interactive Canvas Chart Surface ── */}
      <div className="v3-chart-canvas-wrap">
        {chartState !== "AVAILABLE" && (
          <div className="v3-chart-state-banner" role="status">
            {chartState === "LOADING" && "Loading authoritative market data…"}
            {chartState === "NO_DATA" && (chartDetail || "No authoritative data for this instrument / timeframe / range.")}
            {chartState === "DATA_PROVIDER_NOT_CONFIGURED" && "Data provider not configured — import local data or configure a provider."}
            {chartState === "BACKEND_UNAVAILABLE" && "Backend unavailable — retry when the runtime is reachable."}
            {chartState === "ERROR" && (chartDetail || "Chart unavailable due to an unexpected error.")}
          </div>
        )}
        <canvas
          ref={canvasRef}
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
          aria-label={`${displayTitle} candlestick chart (interactive canvas)`}
        />
      </div>
    </div>
  );
};
