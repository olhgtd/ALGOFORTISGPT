/**
 * AlgoFortis Public Website – Sections 2 to 10
 * Surface: algofortis.com
 *
 * 2. Platform Capabilities
 * 3. Strategy Governance
 * 4. Backtesting
 * 5. Paper / Operational Control
 * 6. Security & Audit
 * 7. Architecture
 * 8. Documentation Entry
 * 9. Secure Application Entry
 * 10. Footer
 */

import React, { useState } from "react";

interface WebsiteSectionsProps {
  onOpenDocs: () => void;
  onLaunchApp: () => void;
}

export const WebsiteSections: React.FC<WebsiteSectionsProps> = ({
  onOpenDocs,
  onLaunchApp,
}) => {
  const [activeGovTab, setActiveGovTab] = useState<number>(0);

  const govSteps = [
    {
      num: "01",
      title: "DRAFT & INGESTION",
      desc: "Strategy code registered with strict AST linting and frozen schema definitions.",
      req: "GATE: AST Validated & Types Checked",
    },
    {
      num: "02",
      title: "STATIC VALIDATION",
      desc: "Algorithmic invariant checking, memory bounds assertions, and parameter constraint bounds.",
      req: "GATE: Zero Forbidden Module Imports",
    },
    {
      num: "03",
      title: "DETERMINISTIC BACKTEST",
      desc: "Tick-level historical replay with verified zero lookahead bias and slippage models.",
      req: "GATE: Sharpe > 1.8 & MaxDD < 8%",
    },
    {
      num: "04",
      title: "PAPER ATTESTATION",
      desc: "Real-time sandbox execution on live FIX feeds without capital risk.",
      req: "GATE: 72h Continuous Uptime Attested",
    },
    {
      num: "05",
      title: "LIVE_LOCKED CAPITAL",
      desc: "FIDO2 hardware key authorized production allocation with hard kill-switches.",
      req: "GATE: Dual-Operator Cryptographic Sign-Off",
    },
  ];

  return (
    <>
      {/* ═══════════════════════════════════════════════════════════════════════
          SECTION 2: PLATFORM CAPABILITIES
          ═══════════════════════════════════════════════════════════════════════ */}
      <section className="sx-section-wrapper" id="capabilities">
        <div className="sx-section-header">
          <span className="sx-section-eyebrow">Institutional Architecture</span>
          <h2 className="sx-section-title">Engineered for Fail-Closed Precision</h2>
          <p className="sx-section-desc">
            Six foundational pillars built from the ground up for high-frequency quantitative execution, 
            absolute audit transparency, and uncompromised security.
          </p>
        </div>

        <div className="sx-capabilities-grid">
          {/* Pillar 1 */}
          <div className="sx-capability-card">
            <div className="sx-cap-icon-box">⚡</div>
            <h3 className="sx-cap-title">Deterministic Order Engine</h3>
            <p className="sx-cap-body">
              Zero-garbage-collection hot path in C-extension bindings ensuring sub-50 microsecond 
              order calculation and dispatch with strictly bounded execution variance.
            </p>
            <div className="sx-cap-specs">
              <span className="sx-spec-badge">LATENCY &lt;50μs</span>
              <span className="sx-spec-badge">C-EXT ACCELERATED</span>
              <span className="sx-spec-badge">ZERO JANK</span>
            </div>
          </div>

          {/* Pillar 2 */}
          <div className="sx-capability-card">
            <div className="sx-cap-icon-box">🛡</div>
            <h3 className="sx-cap-title">Sub-Millisecond Risk Sentinel</h3>
            <p className="sx-cap-body">
              Continuous real-time portfolio margin check, max drawdown perimeter guards, 
              and hard auto-disarm kill switches that sever exchange order flows in microseconds.
            </p>
            <div className="sx-cap-specs">
              <span className="sx-spec-badge">HARD KILL-SWITCH</span>
              <span className="sx-spec-badge">MARGIN AUTO-GUARD</span>
              <span className="sx-spec-badge">FAIL-CLOSED</span>
            </div>
          </div>

          {/* Pillar 3 */}
          <div className="sx-capability-card">
            <div className="sx-cap-icon-box">🔗</div>
            <h3 className="sx-cap-title">Cryptographic Execution Audit</h3>
            <p className="sx-cap-body">
              Every order state transition, risk verdict, and fill event is immutably recorded 
              in an append-only SQLite WAL ledger chained with SHA-256 state hashes.
            </p>
            <div className="sx-cap-specs">
              <span className="sx-spec-badge">SHA-256 HASH CHAIN</span>
              <span className="sx-spec-badge">SQLITE WAL</span>
              <span className="sx-spec-badge">NON-REPUDIATION</span>
            </div>
          </div>

          {/* Pillar 4 */}
          <div className="sx-capability-card">
            <div className="sx-cap-icon-box">🔒</div>
            <h3 className="sx-cap-title">FIDO2 Hardware Key Authentication</h3>
            <p className="sx-cap-body">
              Zero passwords, zero plaintext secrets. High-privilege capital allocation, strategy deployment, 
              and live override operations mandate cryptographic WebAuthn physical tokens.
            </p>
            <div className="sx-cap-specs">
              <span className="sx-spec-badge">WEBAUTHN MANDATE</span>
              <span className="sx-spec-badge">DUAL STEP-UP</span>
              <span className="sx-spec-badge">ZERO PHISHING</span>
            </div>
          </div>

          {/* Pillar 5 */}
          <div className="sx-capability-card">
            <div className="sx-cap-icon-box">📊</div>
            <h3 className="sx-cap-title">High-Density Telemetry & Blotter</h3>
            <p className="sx-cap-body">
              Desktop-class financial interface featuring real-time tick streaming, millisecond-resolution 
              candlestick charting, virtualized multi-asset blotters, and fail-closed trust indicators.
            </p>
            <div className="sx-cap-specs">
              <span className="sx-spec-badge">CANVAS RENDERER</span>
              <span className="sx-spec-badge">TRUST BADGES</span>
              <span className="sx-spec-badge">VIRTUALIZED BLOTTER</span>
            </div>
          </div>

          {/* Pillar 6 */}
          <div className="sx-capability-card">
            <div className="sx-cap-icon-box">📜</div>
            <h3 className="sx-cap-title">Strategy Lifecycle Governance</h3>
            <p className="sx-cap-body">
              A formal finite state machine that enforces strict promotion criteria across 5 sequential 
              verification stages before a strategy can execute against live capital.
            </p>
            <div className="sx-cap-specs">
              <span className="sx-spec-badge">5-STAGE FSM</span>
              <span className="sx-spec-badge">PROMOTION GATES</span>
              <span className="sx-spec-badge">CODE CHECKSUMS</span>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════════
          SECTION 3: STRATEGY GOVERNANCE
          ═══════════════════════════════════════════════════════════════════════ */}
      <section className="sx-section-wrapper" id="governance">
        <div className="sx-section-header">
          <span className="sx-section-eyebrow">Formal Verification Pipeline</span>
          <h2 className="sx-section-title">5-Stage Strategy Governance</h2>
          <p className="sx-section-desc">
            No code bypasses the state machine. Every quantitative strategy must formally satisfy 
            all upstream gating requirements before being unlocked for live execution.
          </p>
        </div>

        <div className="sx-governance-flow">
          {govSteps.map((step, idx) => (
            <div
              key={step.num}
              className={`sx-gov-step-card ${activeGovTab === idx ? "active-gate" : ""}`}
              onClick={() => setActiveGovTab(idx)}
              style={{ cursor: "pointer" }}
            >
              <div className="sx-step-number">{step.num}</div>
              <h4 className="sx-step-title">{step.title}</h4>
              <p className="sx-step-desc">{step.desc}</p>
              <div className="sx-step-gate-req">{step.req}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════════
          SECTIONS 4 & 5: BACKTESTING & PAPER CONTROL
          ═══════════════════════════════════════════════════════════════════════ */}
      <section className="sx-section-wrapper" id="simulation">
        <div className="sx-section-header">
          <span className="sx-section-eyebrow">Verification Environments</span>
          <h2 className="sx-section-title">Deterministic Backtesting & Live Paper Control</h2>
          <p className="sx-section-desc">
            Exact historical replication paired with a high-fidelity paper trading sandbox 
            that mirrors live exchange behavior without capital exposure.
          </p>
        </div>

        <div className="sx-dual-engine-grid">
          {/* Backtesting Engine */}
          <div className="sx-engine-panel">
            <span className="sx-engine-tag">SECTION 4 • ENGINE SIMULATION</span>
            <h3 className="sx-engine-title">Microsecond Backtest Engine</h3>
            <div className="sx-engine-features-list">
              <div className="sx-feature-row">
                <span className="sx-check-icon">✓</span>
                <span><strong>Zero Lookahead Bias:</strong> Strict sequential timestamp progression guaranteed at the byte-stream level.</span>
              </div>
              <div className="sx-feature-row">
                <span className="sx-check-icon">✓</span>
                <span><strong>Microsecond Tick Replay:</strong> High-density order book reconstruction across equities, futures, and options.</span>
              </div>
              <div className="sx-feature-row">
                <span className="sx-check-icon">✓</span>
                <span><strong>Dynamic Slippage & Fee Models:</strong> Realistic liquidity exhaustion and market impact simulation.</span>
              </div>
              <div className="sx-feature-row">
                <span className="sx-check-icon">✓</span>
                <span><strong>Institutional Risk Attribution:</strong> Automated calculation of Sharpe, Sortino, Calmar, and Tail Risk metrics.</span>
              </div>
            </div>
          </div>

          {/* Paper Operational Control */}
          <div className="sx-engine-panel">
            <span className="sx-engine-tag">SECTION 5 • OPERATIONAL SANDBOX</span>
            <h3 className="sx-engine-title">Live Paper Operational Control</h3>
            <div className="sx-engine-features-list">
              <div className="sx-feature-row">
                <span className="sx-check-icon">✓</span>
                <span><strong>Live WebSocket / FIX Ingestion:</strong> Real-time production market feeds feeding simulated order routing.</span>
              </div>
              <div className="sx-feature-row">
                <span className="sx-check-icon">✓</span>
                <span><strong>Synthetic Fill Latency:</strong> Injection of realistic network jitter and exchange matching engine delays.</span>
              </div>
              <div className="sx-feature-row">
                <span className="sx-check-icon">✓</span>
                <span><strong>Safe Mode Gating:</strong> Instantaneous order lock prevents accidental live order dispatch during testing.</span>
              </div>
              <div className="sx-feature-row">
                <span className="sx-check-icon">✓</span>
                <span><strong>72h Continuous Soak Test:</strong> Automated drift detection comparing paper signals against live order books.</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════════
          SECTION 6 & 7: SECURITY FOUNDATION & ARCHITECTURE
          ═══════════════════════════════════════════════════════════════════════ */}
      <section className="sx-section-wrapper" id="architecture">
        <div className="sx-section-header">
          <span className="sx-section-eyebrow">System Topology</span>
          <h2 className="sx-section-title">Institutional Security & Core Architecture</h2>
          <p className="sx-section-desc">
            Clean architectural separation between execution hot paths, persistent audit stores, 
            and the zero-trust administrative perimeter.
          </p>
        </div>

        <div className="sx-arch-diagram">
          <div className="sx-arch-layers">
            <div className="sx-arch-layer-card">
              <div className="sx-arch-layer-name">LAYER 1 • ENGINE CORE</div>
              <div className="sx-arch-layer-desc">
                High-performance C-extensions, event dispatch loop, in-memory ring buffers, sub-50μs order evaluation.
              </div>
            </div>

            <div className="sx-arch-layer-card">
              <div className="sx-arch-layer-name">LAYER 2 • RISK SENTINEL</div>
              <div className="sx-arch-layer-desc">
                Pre-trade margin verification, portfolio limit enforcement, automated kill-switch armed at all times.
              </div>
            </div>

            <div className="sx-arch-layer-card">
              <div className="sx-arch-layer-name">LAYER 3 • AUDIT & OUTBOX</div>
              <div className="sx-arch-layer-desc">
                Transactional outbox pattern, SQLite WAL persistence, cryptographic SHA-256 hash chains for non-repudiation.
              </div>
            </div>

            <div className="sx-arch-layer-card">
              <div className="sx-arch-layer-name">LAYER 4 • SECURE GATEWAY</div>
              <div className="sx-arch-layer-desc">
                FIDO2 WebAuthn hardware key perimeter, fail-closed trust badge attestation, zero plain-text credentials.
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════════
          SECTION 8: DOCUMENTATION ENTRY
          ═══════════════════════════════════════════════════════════════════════ */}
      <section className="sx-section-wrapper" id="documentation">
        <div className="sx-section-header">
          <span className="sx-section-eyebrow">Developer & Operator Docs</span>
          <h2 className="sx-section-title">Architectural Documentation</h2>
          <p className="sx-section-desc">
            Explore frozen technical specifications, state machine invariants, and API contracts.
          </p>
        </div>

        <div style={{ display: "flex", justifyContent: "center", gap: "16px" }}>
          <button className="sx-btn sx-btn-primary" onClick={onOpenDocs}>
            Open Documentation Explorer ↗
          </button>
          <a
            href="#hero-cinematic"
            className="sx-btn sx-btn-secondary"
            onClick={(e) => {
              e.preventDefault();
              window.scrollTo({ top: 0, behavior: "smooth" });
            }}
          >
            Back to Top ↑
          </a>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════════
          SECTION 9: SECURE APPLICATION ENTRY SURFACE
          ═══════════════════════════════════════════════════════════════════════ */}
      <section className="sx-section-wrapper" id="secure-app">
        <div className="sx-gateway-banner">
          <div className="sx-gateway-text">
            <h3 className="sx-gateway-title">AlgoFortis Secure Control Center</h3>
            <p className="sx-gateway-desc">
              Authoritative execution dashboard accessible exclusively to authenticated institutional operators. 
              Protected by WebAuthn hardware passkeys and strict fail-closed governance.
            </p>
            <div className="sx-gateway-auth-badges">
              <span className="sx-auth-pill">FIDO2 HARDWARE KEY</span>
              <span className="sx-auth-pill">SURFACE: app.algofortis.com</span>
              <span className="sx-auth-pill">TLS 1.3 / E2E ATTESTED</span>
            </div>
          </div>
          <div>
            <button
              className="sx-btn sx-btn-primary"
              onClick={onLaunchApp}
              style={{ padding: "12px 24px", fontSize: "14px" }}
              id="cta-launch-terminal"
            >
              Launch Terminal [app.algofortis.com] →
            </button>
          </div>
        </div>
      </section>

      {/* ═══════════════════════════════════════════════════════════════════════
          SECTION 10: INSTITUTIONAL FOOTER
          ═══════════════════════════════════════════════════════════════════════ */}
      <footer className="sx-footer">
        <div className="sx-footer-inner">
          <div className="sx-footer-brand-summary">
            <div className="sx-brand-title">
              <span>ALGOFORTIS</span>
              <span className="sx-brand-version">v9.0.0</span>
            </div>
            <p className="sx-footer-desc">
              Institutional algorithmic trading research, risk operating system and fail-closed security infrastructure. 
              Deterministic execution, cryptographic auditability, and formal strategy governance.
            </p>
          </div>

          <div>
            <div className="sx-footer-col-title">Platform</div>
            <div className="sx-footer-link-list">
              <a href="#capabilities" className="sx-footer-link">Engine Capabilities</a>
              <a href="#governance" className="sx-footer-link">Strategy Governance</a>
              <a href="#simulation" className="sx-footer-link">Backtesting Replay</a>
              <a href="#simulation" className="sx-footer-link">Paper Operational Sandbox</a>
            </div>
          </div>

          <div>
            <div className="sx-footer-col-title">Architecture</div>
            <div className="sx-footer-link-list">
              <a href="#architecture" className="sx-footer-link">System Topology</a>
              <button onClick={onOpenDocs} className="sx-footer-link">Architecture Specs</button>
              <button onClick={onOpenDocs} className="sx-footer-link">FIDO2 WebAuthn Perimeter</button>
              <button onClick={onOpenDocs} className="sx-footer-link">SQLite WAL Hash Chains</button>
            </div>
          </div>

          <div>
            <div className="sx-footer-col-title">Surfaces</div>
            <div className="sx-footer-link-list">
              <span className="sx-footer-link" style={{ color: "var(--sx-sky-text)" }}>
                ● algofortis.com (Public)
              </span>
              <button onClick={onLaunchApp} className="sx-footer-link">
                app.algofortis.com (Secure Terminal)
              </button>
              <span className="sx-footer-link" style={{ color: "var(--sx-ink-dim)" }}>
                api.algofortis.com (FIX / REST)
              </span>
            </div>
          </div>
        </div>

        <div className="sx-footer-bottom">
          <div>
            © 2026 AlgoFortis Technologies. All rights reserved. 
            <span style={{ marginLeft: "12px", color: "var(--sx-amber-text)" }}>
              [SAMPLE DATA • ARCHITECTURAL PROTOTYPE • NON-AUTHORITATIVE]
            </span>
          </div>
          <div>
            BUILD: <span style={{ color: "var(--sx-sky-text)" }}>9a8f2c-release</span> | FINGERPRINT: <span style={{ color: "var(--sx-ink-mono)" }}>SHA256: 4e82b7...d109</span>
          </div>
        </div>
      </footer>
    </>
  );
};
