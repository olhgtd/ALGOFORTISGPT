/**
 * AlgoFortis Public Website – Main Surface Controller
 * Surface: algofortis.com
 *
 * Governed by DESIGN.md – Institutional Dark Terminal & Trading Aesthetic
 */

import React, { useState, useEffect } from "react";
import { CinematicHero } from "./CinematicHero";
import { WebsiteSections } from "./WebsiteSections";
import { DocsModal } from "./DocsModal";
import "./website.css";

interface AlgoFortisWebsiteProps {
  onLaunchApp: () => void;
}

export const AlgoFortisWebsite: React.FC<AlgoFortisWebsiteProps> = ({ onLaunchApp }) => {
  const [utcTime, setUtcTime] = useState<string>("");
  const [isDocsOpen, setIsDocsOpen] = useState<boolean>(false);

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setUtcTime(
        now.toISOString().replace("T", " ").replace("Z", " UTC")
      );
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  const handleExplore = () => {
    const el = document.getElementById("capabilities");
    if (el) {
      el.scrollIntoView({ behavior: "smooth" });
    }
  };

  return (
    <div className="sx-website-root">
      {/* ─── Top Telemetry & Surface Ticker ─── */}
      <div className="sx-surface-tape">
        <div className="sx-tape-left">
          <span className="sx-tape-tag accent">
            <span className="sx-pulse-dot" /> SURFACE: algofortis.com (PUBLIC)
          </span>
          <span className="sx-tape-tag">
            NETWORK: NOMINAL • LATENCY &lt;45μs
          </span>
        </div>
        <div className="sx-tape-right">
          <span className="sx-sample-notice">
            [ALGOFORTIS OS • ARCHITECTURAL RELEASE • AUTHORITATIVE]
          </span>
          <span style={{ fontFamily: "var(--sx-font-mono)" }}>
            {utcTime || "2026-08-27 12:00:00 UTC"}
          </span>
        </div>
      </div>

      {/* ─── Main Navigation Header ─── */}
      <header className="sx-header">
        <div
          className="sx-brand-group"
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          style={{ cursor: "pointer", display: "flex", alignItems: "center", gap: "10px" }}
        >
          <img src="/algofortis_logo.png" alt="AlgoFortis" style={{ width: "28px", height: "28px", objectFit: "contain" }} />
          <div className="sx-brand-text">
            <div className="sx-brand-title">
              <span style={{ color: "#f8fafc" }}>ALGO</span><span style={{ color: "#f59e0b" }}>FORTIS</span>
              <span className="sx-brand-version">v1.0.0</span>
            </div>
            <div className="sx-brand-subtitle">
              TRADING RESEARCH &amp; RISK OS
            </div>
          </div>
        </div>

        <nav className="sx-nav-links">
          <a href="#capabilities" className="sx-nav-link">Capabilities</a>
          <a href="#governance" className="sx-nav-link">Governance</a>
          <a href="#simulation" className="sx-nav-link">Simulation</a>
          <a href="#architecture" className="sx-nav-link">Architecture</a>
          <button
            className="sx-nav-link"
            onClick={() => setIsDocsOpen(true)}
            style={{ padding: 0 }}
          >
            Documentation
          </button>
        </nav>

        <div className="sx-header-actions">
          <button
            className="sx-btn sx-btn-secondary"
            onClick={() => setIsDocsOpen(true)}
          >
            Docs ↗
          </button>
          <button
            className="sx-btn sx-btn-terminal"
            onClick={onLaunchApp}
            id="nav-btn-app-login"
          >
            <span style={{ color: "#f59e0b" }}>●</span>
            Launch Terminal →
          </button>
        </div>
      </header>

      {/* ─── 1. Hero with 5-Second Cinematic Opening ─── */}
      <CinematicHero
        onExplore={handleExplore}
        onOpenDocs={() => setIsDocsOpen(true)}
        onLaunchApp={onLaunchApp}
      />

      {/* ─── 2 - 10. Platform Sections & Footer ─── */}
      <WebsiteSections
        onOpenDocs={() => setIsDocsOpen(true)}
        onLaunchApp={onLaunchApp}
      />

      {/* ─── Documentation Modal ─── */}
      <DocsModal
        isOpen={isDocsOpen}
        onClose={() => setIsDocsOpen(false)}
      />
    </div>
  );
};
