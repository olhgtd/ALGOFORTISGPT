import { useState, useEffect } from "react";
import { Icon } from "../../shared/icons/V3Icons";
import { Sparkline, Drawer, KV, TruthChip, Dot, fmtINR, fmtSignedINR, fmtSignedPct } from "../../shared/utilities/V3Chrome";
import { ProfessionalChart } from "../../shared/components/ProfessionalChart";
import { OptionsWorkspace } from "../components/OptionsWorkspace";
import { queryCurrentUserProfile, type UserProfileData } from "../../shared/services/integrationClient";
import {
  PORTFOLIO,
  STRATEGIES,
  USER_CONNECTORS,
  ALERTS,
  ACTIVITY,
  DEFAULT_SELECTED_CONTRACT,
  DEFAULT_GLOBAL_STRIKE_POLICY,
  type SelectedOptionContract,
  type GlobalStrikePolicy,
} from "../../sampleData";

/* USER HOME — PASS 2 composition.
   Priority: Portfolio value → dominant Market Workspace (Canvas Chart + First-Class Options Strike Ladder)
   → compact Strategies / Connections (V2_ONLY_AGENTS: Agents region removed from V1 surface) → activity entry point.
   Full Options Chain & Activity live behind progressive disclosure. */

interface Props {
  go: (screen: string) => void;
  policy?: GlobalStrikePolicy;
  onChangePolicy?: (next: GlobalStrikePolicy) => void;
  previewMode?: boolean;
}

const STAGE_TONE: Record<string, "ok" | "warn" | "dim" | "live"> = { LIVE: "ok", PAPER: "live", BACKTEST: "dim" };

export const UserHome: React.FC<Props> = ({ go, policy = DEFAULT_GLOBAL_STRIKE_POLICY, previewMode = false }) => {
  const [detail, setDetail] = useState<"portfolio" | "alerts" | "activity" | "options-modal" | null>(null);
  const [underlying, setUnderlying] = useState("NIFTY");
  const [selectedContract, setSelectedContract] = useState<SelectedOptionContract | null>(DEFAULT_SELECTED_CONTRACT);
  const [chartTarget, setChartTarget] = useState<"underlying" | "contract">("underlying");
  const [profile, setProfile] = useState<UserProfileData | null>(null);

  useEffect(() => {
    let active = true;
    queryCurrentUserProfile().then((res) => {
      if (active && res.data) setProfile(res.data);
    });
    return () => { active = false; };
  }, []);

  const connected = previewMode ? USER_CONNECTORS.filter((c) => c.status === "CONNECTED").length : 0;
  const delayed = previewMode ? USER_CONNECTORS.filter((c) => c.data === "DELAYED").length : 0;
  const offline = previewMode ? USER_CONNECTORS.filter((c) => c.status === "DISCONNECTED" || c.data === "NONE").length : 0;
  const attentionAlerts = previewMode ? ALERTS.filter((a) => a.level === "ATTENTION").length : 0;

  const handleSelectContract = (contract: SelectedOptionContract) => {
    setSelectedContract(contract);
  };

  const handleViewContractChart = (contract: SelectedOptionContract) => {
    setSelectedContract(contract);
    setChartTarget("contract");
  };

  return (
    <>
      <div className="v3-screen-head">
        <div>
          <h2 className="v3-screen-title">Good afternoon, {profile?.display_name || "Trader"}</h2>
          <p className="v3-screen-sub">{profile?.sx_id || "AUTHORITATIVE RUNTIME"} · Real-time portfolio overview</p>
        </div>
        <TruthChip kind="REAL" title="REAL + WORKING — Authoritative User Workspace" />
      </div>

      {/* A — Portfolio value / daily performance with semantic financial colors */}
      <section className="v3-region tight" style={{ display: "flex", flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", gap: 28, flexWrap: "wrap", paddingTop: 8 }}>
        <div>
          <div className="v3-hero-label">Portfolio Value · Total Equity</div>
          <div className="v3-hero-value" style={{ marginTop: 7 }}>
            ₹0
          </div>
          <div className="v3-hero-delta" style={{ marginTop: 8 }}>
            <Dot tone="dim" />
            <span className="v3-dim" style={{ fontWeight: 700 }}>
              ₹0 (0.00%)
            </span> today
          </div>
        </div>
        <div style={{ flex: "0 1 300px", minWidth: 200, alignSelf: "flex-end" }}>
          <Sparkline points={[0, 0, 0, 0, 0]} height={54} />
        </div>
        <button className="v3-entry-link" onClick={() => go("portfolio")}>
          Portfolio details <Icon name="chevron" size={14} />
        </button>
      </section>

      {/* Quick Financial Summary Strip */}
      <div className="v3-kpi-grid" style={{ margin: "10px 0 8px" }}>
        <div className="v3-kpi-card">
          <div className="v3-kpi-title">Available Cash</div>
          <div className="v3-kpi-val">
            ₹0
          </div>
          <div className="v3-kpi-sub">
            No paper simulation capital allocated
          </div>
        </div>
        <div className="v3-kpi-card">
          <div className="v3-kpi-title">Capital Used</div>
          <div className="v3-kpi-val">
            ₹0 (0.0%)
          </div>
          <div className="v3-kpi-sub">Risk envelope safe</div>
        </div>
        <div className="v3-kpi-card">
          <div className="v3-kpi-title">Active Strategies</div>
          <div className="v3-kpi-val">
            0 Active
          </div>
          <div className="v3-kpi-sub">
            0 Live Readiness · 0 Paper
          </div>
        </div>
        <div className="v3-kpi-card">
          <div className="v3-kpi-title">Win Rate (Month)</div>
          <div className="v3-kpi-val">
            0.0%
          </div>
          <div className="v3-kpi-sub">
            0 trades recorded
          </div>
        </div>
      </div>

      <hr className="v3-divide" />

      {/* B — Market & Options Workspace */}
      <section className="v3-region">
        <div className="v3-region-head">
          <span className="v3-region-title">Market &amp; Options</span>
          <span style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <span className="v3-region-note">High-DPI Interactive Chart &amp; First-Class Options Ladder</span>
            <button
              className="v3-btn ghost mini"
              onClick={() => setDetail("options-modal")}
              title="Open full options chain drawer"
            >
              <Icon name="layers" size={13} /> Full Option Chain
            </button>
          </span>
        </div>

        {/* 1. Professional OHLC Candlestick Chart */}
        <ProfessionalChart
          underlying={underlying}
          selectedContract={selectedContract}
          chartTarget={chartTarget}
          onToggleTarget={(target) => setChartTarget(target)}
          onOpenOptionChain={() => setDetail("options-modal")}
        />

        {/* 2. Integrated Options Strike Ladder & Contract Selector */}
        <div style={{ marginTop: 18 }}>
          <div className="v3-region-head" style={{ marginBottom: 12 }}>
            <span className="v3-region-title" style={{ fontSize: 11.5 }}>Options Strike Ladder</span>
            <span className="v3-region-note" style={{ fontSize: 11.5 }}>
              Select any strike to inspect Greeks and switch the chart
            </span>
          </div>

          <OptionsWorkspace
            underlying={underlying}
            onSelectUnderlying={(sym) => {
              setUnderlying(sym);
              setChartTarget("underlying");
            }}
            selectedContract={selectedContract}
            onSelectContract={handleSelectContract}
            onViewContractChart={handleViewContractChart}
            policy={policy}
          />
        </div>
      </section>

      <hr className="v3-divide" />

      {/* C / D — Compact Strategies, Connections (V2_ONLY_AGENTS: Agents region removed) */}
      <div className="v3-grid" style={{ paddingTop: 4 }}>
        <section className="v3-region v3-sp6">
          <div className="v3-region-head" style={{ marginBottom: 12 }}>
            <span className="v3-region-title">Strategies</span>
            <span className="v3-region-note">0 versions</span>
          </div>
          <div className="v3-rows">
            <div className="v3-row" style={{ padding: "12px 0", color: "var(--v3-ink3)", fontSize: 12 }}>
              No strategies assigned yet
            </div>
          </div>
          <button className="v3-entry-link" style={{ marginTop: 14 }} onClick={() => go("strategies")}>
            All strategies <Icon name="chevron" size={14} />
          </button>
        </section>

        <section className="v3-region v3-sp6">
          <div className="v3-region-head" style={{ marginBottom: 12 }}>
            <span className="v3-region-title">Connections</span>
          </div>
          <div className="v3-stat-big">0 Connected</div>
          <div style={{ marginTop: 12 }}>
            <div className="v3-stat-line"><Dot tone="dim" /> No broker connections configured</div>
          </div>
          <button className="v3-entry-link" style={{ marginTop: 16 }} onClick={() => go("connections")}>
            Manage connections <Icon name="chevron" size={14} />
          </button>
        </section>
        {/* V2_ONLY_AGENTS: former Agents summary region removed from V1 User Home.
            Prototype preserved in screens/Agents.tsx + sampleData.ts for V2. */}
      </div>

      <hr className="v3-divide" />

      {/* F — Recent Activity Entry Point with Financial Semantics */}
      <section className="v3-region tight" style={{ display: "flex", alignItems: "center", gap: 20, flexWrap: "wrap", paddingBottom: 6 }}>
        <span className="v3-region-title" style={{ margin: 0 }}>Recent</span>
        <span className="v3-region-note" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          No recent activity recorded
        </span>
        <span style={{ marginLeft: "auto", display: "flex", gap: 22, alignItems: "center", flexWrap: "wrap" }}>
          {previewMode && attentionAlerts > 0 && (
            <button className="v3-entry-link" onClick={() => setDetail("alerts")}>
              <Dot tone="warn" /> {attentionAlerts} alerts need attention
            </button>
          )}
          <button className="v3-entry-link" onClick={() => setDetail("activity")}>
            All activity <Icon name="chevron" size={14} />
          </button>
        </span>
      </section>

      {/* ── Detail Drawers ── */}
      <Drawer open={detail === "portfolio"} title="Portfolio Details" sub="Authoritative Portfolio Ledger" onClose={() => setDetail(null)}>
        <dl style={{ margin: 0 }}>
          <KV k="Net Asset Value" v={`₹${fmtINR(PORTFOLIO.nav)}`} />
          <KV k="Day P&L" v={`+₹${fmtINR(PORTFOLIO.dayPnl)} (+${PORTFOLIO.dayPnlPct}%)`} vClass="v3-profit-text" />
          <KV k="Week P&L" v={`+${PORTFOLIO.weekPnlPct}%`} vClass="v3-profit-text" />
          <KV k="Data authority" v="AUTHORITATIVE RUNTIME · Zero open positions" />
        </dl>
      </Drawer>

      <Drawer open={detail === "alerts"} title="Alerts" sub="Authoritative Alerts Stream" onClose={() => setDetail(null)}>
        <div className="v3-rows">
          {ALERTS.map((a, i) => (
            <div className="v3-row" key={i}>
              <div className="v3-row-main">
                <div className="v3-row-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Dot tone={a.level === "ATTENTION" ? "warn" : "dim"} />
                  <span>{a.text}</span>
                </div>
              </div>
              <span className="v3-mono v3-dim" style={{ fontSize: 11, flexShrink: 0 }}>{a.time}</span>
            </div>
          ))}
        </div>
      </Drawer>

      <Drawer open={detail === "activity"} title="Activity / Orders" sub="Authoritative Activity Stream" onClose={() => setDetail(null)}>
        <div className="v3-rows">
          {ACTIVITY.map((a, i) => (
            <div className="v3-row" key={i}>
              <div className="v3-row-main">
                <div className="v3-row-sub" style={{ marginTop: 0, color: "var(--v3-ink-2)" }}>
                  {a.text}
                </div>
              </div>
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {a.pnl && (
                  <span className={a.isProfit ? "v3-profit-text" : "v3-loss-text"} style={{ font: "700 11px var(--v3-mono)" }}>
                    {a.pnl}
                  </span>
                )}
                <span className="v3-mono v3-dim" style={{ fontSize: 10.5 }}>{a.time}</span>
              </span>
            </div>
          ))}
        </div>
      </Drawer>

      {/* Full Option Chain Modal Drawer */}
      <Drawer
        open={detail === "options-modal"}
        title={`${underlying} Option Chain / Strike Ladder`}
        sub="All strikes, IV, OI & Greeks"
        onClose={() => setDetail(null)}
      >
        <OptionsWorkspace
          underlying={underlying}
          onSelectUnderlying={setUnderlying}
          selectedContract={selectedContract}
          onSelectContract={(c) => {
            handleSelectContract(c);
            setDetail(null);
          }}
          onViewContractChart={(c) => {
            handleViewContractChart(c);
            setDetail(null);
          }}
          policy={policy}
        />
      </Drawer>
    </>
  );
};
