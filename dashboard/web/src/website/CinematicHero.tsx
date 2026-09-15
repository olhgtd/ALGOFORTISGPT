/**
 * AlgoFortis Public Website – 5-Second Cinematic Opening & Hero Prototype
 * Surface: algofortis.com
 */

import React, { useEffect, useState, useRef } from "react";
import type { AnimationStage } from "./types";

interface CinematicHeroProps {
  onExplore: () => void;
  onOpenDocs: () => void;
  onLaunchApp: () => void;
}

export const CinematicHero: React.FC<CinematicHeroProps> = ({
  onExplore,
  onOpenDocs,
  onLaunchApp,
}) => {
  const [stage, setStage] = useState<AnimationStage>("dark_init");
  const [elapsedMs, setElapsedMs] = useState<number>(0);
  const [isSettled, setIsSettled] = useState<boolean>(false);
  const [livePrice, setLivePrice] = useState<number>(24520.45);
  const [liveVolume, setLiveVolume] = useState<string>("14.2M");

  const startTimeRef = useRef<number>(Date.now());

  // Run the 4.5s cinematic timeline once on mount
  useEffect(() => {
    startTimeRef.current = Date.now();

    const interval = setInterval(() => {
      const currentElapsed = Date.now() - startTimeRef.current;
      setElapsedMs(currentElapsed);

      if (currentElapsed >= 4400) {
        setStage("settled");
        setIsSettled(true);
        clearInterval(interval);
      } else if (currentElapsed >= 3000) {
        setStage("settling");
      } else if (currentElapsed >= 1500) {
        setStage("fragments_fly");
      } else if (currentElapsed >= 800) {
        setStage("headline_rise");
      } else if (currentElapsed >= 400) {
        setStage("logo_entry");
      } else {
        setStage("dark_init");
      }
    }, 50);

    return () => clearInterval(interval);
  }, []);

  // Subtle sample tick updater for non-authoritative market fragment
  useEffect(() => {
    const tick = setInterval(() => {
      setLivePrice((prev) => {
        const delta = (Math.random() - 0.48) * 2.5;
        return Number((prev + delta).toFixed(2));
      });
    }, 1200);
    return () => clearInterval(tick);
  }, []);

  const handleReplay = () => {
    setIsSettled(false);
    setStage("dark_init");
    startTimeRef.current = Date.now();
    const interval = setInterval(() => {
      const currentElapsed = Date.now() - startTimeRef.current;
      setElapsedMs(currentElapsed);

      if (currentElapsed >= 4400) {
        setStage("settled");
        setIsSettled(true);
        clearInterval(interval);
      } else if (currentElapsed >= 3000) {
        setStage("settling");
      } else if (currentElapsed >= 1500) {
        setStage("fragments_fly");
      } else if (currentElapsed >= 800) {
        setStage("headline_rise");
      } else if (currentElapsed >= 400) {
        setStage("logo_entry");
      } else {
        setStage("dark_init");
      }
    }, 50);
  };

  const isStageLogo =
    stage === "logo_entry" ||
    stage === "headline_rise" ||
    stage === "fragments_fly" ||
    stage === "settling" ||
    stage === "settled";

  const isStageHeadline =
    stage === "headline_rise" ||
    stage === "fragments_fly" ||
    stage === "settling" ||
    stage === "settled";

  const isStageFragments =
    stage === "fragments_fly" ||
    stage === "settling" ||
    stage === "settled";

  return (
    <section className="sx-cinematic-container" id="hero-cinematic">
      {/* ─── 0.0 - 0.5s Background Grid & Horizon ─── */}
      <div className={`sx-grid-backdrop ${stage ? "stage-active" : ""}`} />
      <div className={`sx-ambient-horizon ${stage ? "stage-active" : ""}`} />

      <div className="sx-hero-content">
        {/* ─── 0.4 - 1.2s Brand Vertex Identity ─── */}
        <div
          className={`sx-hero-identity-box ${
            isStageLogo ? "stage-enter" : ""
          }`}
        >
          <div className="sx-hero-shield-icon" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
            <img src="/algofortis_logo.png" alt="AlgoFortis" style={{ width: "32px", height: "32px", objectFit: "contain" }} />
          </div>
          <div className="sx-hero-eyebrow">
            <span className="sx-eyebrow-accent" style={{ color: "#f59e0b" }}>ALGOFORTIS OS</span>
            <span>•</span>
            <span>FAIL-CLOSED INSTITUTIONAL CONTROL</span>
          </div>
        </div>

        {/* ─── 0.8 - 2.0s Headline & Core Product Statement ─── */}
        <div
          className={`sx-hero-headline-group ${
            isStageHeadline ? "stage-enter" : ""
          }`}
        >
          <h1 className="sx-hero-title">
            Trading Research &amp; <br />
            <span className="sx-gradient-text">Risk Operating System</span>
          </h1>
          <p className="sx-hero-statement">
            Deterministic backtest engine, cryptographic strategy governance,
            sub-millisecond risk watchdogs, and fail-closed safety for
            quantitative trading research and execution.
          </p>
        </div>

        {/* ─── 0.8 - 2.0s Action CTAs ─── */}
        <div
          className={`sx-hero-actions-bar ${
            isStageHeadline ? "stage-enter" : ""
          } ${isSettled ? "settled" : ""}`}
        >
          <button
            className="sx-btn sx-btn-primary"
            onClick={onExplore}
            id="hero-btn-explore"
          >
            Explore AlgoFortis ↓
          </button>
          <button
            className="sx-btn sx-btn-secondary"
            onClick={onOpenDocs}
            id="hero-btn-docs"
          >
            Documentation ↗
          </button>
          <button
            className="sx-btn sx-btn-terminal"
            onClick={onLaunchApp}
            id="hero-btn-app-login"
          >
            <span style={{ color: "#f59e0b" }}>●</span>
            Launch Terminal →
          </button>
          {isSettled && (
            <button
              className="sx-btn sx-btn-secondary"
              onClick={handleReplay}
              title="Replay 5-second cinematic opening"
              style={{ fontSize: "11px", padding: "6px 10px" }}
              id="hero-btn-replay"
            >
              ⟳ Replay Intro
            </button>
          )}
        </div>

        {/* ─── 1.5 - 3.2s Assembled Trading Terminal Fragments ─── */}
        <div
          className={`sx-hero-terminal-showcase ${
            isStageFragments ? "stage-enter" : ""
          } ${isSettled ? "settled" : ""}`}
          id="assembled-control-center"
        >
          {/* Terminal Chrome Bar */}
          <div className="sx-terminal-header">
            <div className="sx-terminal-controls">
              <span className="sx-dot red" />
              <span className="sx-dot yellow" />
              <span className="sx-dot green" />
            </div>
            <div className="sx-terminal-title">
              <span>ALGOFORTIS TERMINAL — RESEARCH &amp; RISK OS v1.0.0</span>
              <span style={{ color: "var(--sx-ink-dim)" }}>|</span>
              <span>DETERMINISTIC LATENCY &lt;45μs</span>
            </div>
            <div className="sx-terminal-badges">
              <span className="sx-trust-pill fresh">
                <span className="sx-pulse-dot" /> LIVE ATTESTED
              </span>
              <span className="sx-trust-pill sample">RESEARCH OS</span>
            </div>
          </div>

          {/* Staggered Fragment Panels Grid */}
          <div className="sx-terminal-body-grid">
            {/* Left Fragment: Strategy Governance Pipeline */}
            <div className="sx-fragment-col stagger-1">
              <div className="sx-fragment-title">
                <span>Strategy Governance</span>
                <span style={{ color: "var(--sx-sky-text)" }}>4 ACTIVE</span>
              </div>
              <div className="sx-strategy-node-list">
                <div className="sx-node-item active">
                  <div className="sx-node-status ok" />
                  <div className="sx-node-info">
                    <span className="name">ORB_Breakout_5m</span>
                    <span className="sub">NIFTY Futures • Sharpe 2.41</span>
                  </div>
                  <span className="sx-pill-green">VALIDATED</span>
                </div>
                <div className="sx-node-item active">
                  <div className="sx-node-status ok" />
                  <div className="sx-node-info">
                    <span className="name">MeanRevert_Bollinger_1m</span>
                    <span className="sub">BANKNIFTY • Sharpe 1.89</span>
                  </div>
                  <span className="sx-pill-green">VALIDATED</span>
                </div>
                <div className="sx-node-item standby">
                  <div className="sx-node-status warn" />
                  <div className="sx-node-info">
                    <span className="name">TrendFollow_EMA_15m</span>
                    <span className="sub">FINNIFTY • Warmup (18/200 bars)</span>
                  </div>
                  <span className="sx-pill-warn">WARMING</span>
                </div>
                <div className="sx-node-item standby">
                  <div className="sx-node-status dim" />
                  <div className="sx-node-info">
                    <span className="name">GammaScalp_Options_1m</span>
                    <span className="sub">NIFTY CE/PE • Research Sandbox</span>
                  </div>
                  <span className="sx-pill-dim">SANDBOX</span>
                </div>
              </div>
            </div>

            {/* Middle Fragment: Microstructure Live Feed / Chart Preview */}
            <div className="sx-fragment-col stagger-2 middle-chart-fragment">
              <div className="sx-fragment-title">
                <span>Deterministic Feed: NIFTY FUT (1m)</span>
                <span className="sx-price-ticker">
                  ₹{livePrice.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  <span className="sx-price-delta up">+0.42%</span>
                </span>
              </div>
              <div className="sx-micro-chart-canvas">
                {/* SVG Simulated Micro-Candlestick Chart Fragment */}
                <svg className="sx-hero-chart-svg" viewBox="0 0 360 140">
                  <defs>
                    <linearGradient id="gridGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                      <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.08" />
                      <stop offset="100%" stopColor="#38bdf8" stopOpacity="0" />
                    </linearGradient>
                  </defs>
                  <path d="M 0 110 L 30 102 L 60 115 L 90 98 L 120 85 L 150 92 L 180 72 L 210 65 L 240 78 L 270 54 L 300 48 L 330 35 L 360 28" fill="none" stroke="#38bdf8" strokeWidth="2" />
                  <path d="M 0 110 L 30 102 L 60 115 L 90 98 L 120 85 L 150 92 L 180 72 L 210 65 L 240 78 L 270 54 L 300 48 L 330 35 L 360 28 L 360 140 L 0 140 Z" fill="url(#gridGrad)" />
                  {/* Candlestick Glyphs */}
                  <line x1="60" y1="95" x2="60" y2="125" stroke="#ef4444" strokeWidth="1" />
                  <rect x="56" y="102" width="8" height="13" fill="#ef4444" />
                  <line x1="120" y1="75" x2="120" y2="105" stroke="#10b981" strokeWidth="1" />
                  <rect x="116" y="85" width="8" height="12" fill="#10b981" />
                  <line x1="180" y1="60" x2="180" y2="88" stroke="#10b981" strokeWidth="1" />
                  <rect x="176" y="70" width="8" height="14" fill="#10b981" />
                  <line x1="270" y1="40" x2="270" y2="70" stroke="#10b981" strokeWidth="1" />
                  <rect x="266" y="50" width="8" height="15" fill="#10b981" />
                  <line x1="330" y1="20" x2="330" y2="50" stroke="#10b981" strokeWidth="1" />
                  <rect x="326" y="28" width="8" height="16" fill="#10b981" />
                </svg>
              </div>
              <div className="sx-chart-footer-metrics">
                <span>VOL: {liveVolume}</span>
                <span>VWAP: ₹24,498.10</span>
                <span>ATR(14): 42.60</span>
                <span>SPREAD: 0.05</span>
              </div>
            </div>

            {/* Right Fragment: Risk Sentinel HUD */}
            <div className="sx-fragment-col stagger-3">
              <div className="sx-fragment-title">
                <span>Real-Time Risk Sentinels</span>
                <span className="sx-pill-green">ARMED (0 FAILS)</span>
              </div>
              <div className="sx-sentinel-hud-list">
                <div className="sx-hud-item">
                  <div className="sx-hud-label">
                    <span>Daily Drawdown Limit (2.00%)</span>
                    <span className="val ok">0.42% / ₹21,000</span>
                  </div>
                  <div className="sx-progress-track">
                    <div className="sx-progress-bar ok" style={{ width: "21%" }} />
                  </div>
                </div>
                <div className="sx-hud-item">
                  <div className="sx-hud-label">
                    <span>Max Open Positions (3 Limit)</span>
                    <span className="val ok">1 / 3 ACTIVE</span>
                  </div>
                  <div className="sx-progress-track">
                    <div className="sx-progress-bar ok" style={{ width: "33%" }} />
                  </div>
                </div>
                <div className="sx-hud-item">
                  <div className="sx-hud-label">
                    <span>Order Velocity Gate (&lt;10 req/s)</span>
                    <span className="val ok">1.2 req/s</span>
                  </div>
                  <div className="sx-progress-track">
                    <div className="sx-progress-bar ok" style={{ width: "12%" }} />
                  </div>
                </div>
                <div className="sx-hud-item">
                  <div className="sx-hud-label">
                    <span>Kill Switch &amp; Protective Stops</span>
                    <span className="val text-success">READY · HARD STOP ON</span>
                  </div>
                  <div className="sx-progress-track">
                    <div className="sx-progress-bar ok" style={{ width: "100%" }} />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
