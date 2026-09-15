import React, { useState, useMemo } from "react";
import { Icon } from "../../shared/icons/V3Icons";
import { TruthChip, Dot, fmtSignedINR, fmtSignedPct, Drawer, KV } from "../../shared/utilities/V3Chrome";
import {
  type SelectedOptionContract,
  type StrikeRow,
  type OptionMoneyness,
  type GlobalStrikePolicy,
  DEFAULT_GLOBAL_STRIKE_POLICY,
  resolveStrikesFromPolicy,
  UNDERLYINGS,
  resolveAtmStrike,
  generateOptionChain,
} from "../../sampleData";

export interface OptionsWorkspaceProps {
  underlying: string;
  onSelectUnderlying: (underlying: string) => void;
  selectedContract: SelectedOptionContract | null;
  onSelectContract: (contract: SelectedOptionContract) => void;
  onViewContractChart?: (contract: SelectedOptionContract) => void;
  policy?: GlobalStrikePolicy;
  isCompact?: boolean;
}

export const OptionsWorkspace: React.FC<OptionsWorkspaceProps> = ({
  underlying,
  onSelectUnderlying,
  selectedContract,
  onSelectContract,
  onViewContractChart,
  policy = DEFAULT_GLOBAL_STRIKE_POLICY,
  isCompact = false,
}) => {
  const cfg = UNDERLYINGS[underlying] || UNDERLYINGS.NIFTY;
  const resolvedAtm = resolveAtmStrike(cfg.spot, cfg.step);
  const policyRes = useMemo(() => {
    return resolveStrikesFromPolicy(cfg.spot, cfg.step, policy);
  }, [cfg, policy]);

  const [expiry, setExpiry] = useState<string>(cfg.expiries[0]);
  const [filterView, setFilterView] = useState<"ALL" | "CALLS" | "PUTS">("ALL");
  const [strikeRange, setStrikeRange] = useState<"ATM_10" | "ALL">("ATM_10");
  const [mobileTab, setMobileTab] = useState<"CE" | "PE">("CE");
  const [drawerContract, setDrawerContract] = useState<SelectedOptionContract | null>(null);

  // Generate Strike Ladder rows using resolved ATM context
  const allRows: StrikeRow[] = useMemo(() => {
    return generateOptionChain(underlying, expiry);
  }, [underlying, expiry]);

  const visibleRows = useMemo(() => {
    if (strikeRange === "ATM_10") {
      const atmIndex = allRows.findIndex((r) => r.isAtm);
      if (atmIndex !== -1) {
        return allRows.slice(Math.max(0, atmIndex - 5), Math.min(allRows.length, atmIndex + 6));
      }
    }
    return allRows;
  }, [allRows, strikeRange]);

  const handleSelect = (strike: number, type: "CE" | "PE", leg: any, moneyness: OptionMoneyness) => {
    const contract: SelectedOptionContract = {
      underlying,
      expiry,
      strike,
      optionType: type,
      moneyness,
      ltp: leg.ltp,
      change: leg.change,
      changePct: leg.changePct,
      bid: leg.bid,
      ask: leg.ask,
      volume: leg.volume,
      oi: leg.oi,
      oiChange: leg.oiChange,
      iv: leg.iv,
      delta: leg.delta,
      theta: leg.theta,
      gamma: leg.gamma,
      vega: leg.vega,
      lotSize: cfg.lotSize,
      greeksAuthority: leg.greeksAuthority,
    };
    onSelectContract(contract);
  };

  return (
    <div className="v3-options-workspace">
      {/* ── Selector Bar: Underlying Index + Expiry + Filter ── */}
      <div className="v3-options-bar">
        {/* Underlying Selector */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <span className="v3-region-title" style={{ marginRight: 4 }}>Underlying:</span>
          <div className="v3-inst-select-group" role="tablist" aria-label="Underlying index selector">
            {Object.keys(UNDERLYINGS).map((sym) => {
              const uCfg = UNDERLYINGS[sym];
              const uAtm = resolveAtmStrike(uCfg.spot, uCfg.step);
              return (
                <button
                  key={sym}
                  role="tab"
                  aria-selected={underlying === sym}
                  className={`v3-inst-btn ${underlying === sym ? "active" : ""}`}
                  onClick={() => {
                    onSelectUnderlying(sym);
                    setExpiry(UNDERLYINGS[sym].expiries[0]);
                  }}
                  title={`Spot ₹${uCfg.spot.toFixed(1)} · ATM Strike: ${uAtm}`}
                >
                  {sym} <span style={{ opacity: 0.65, fontSize: 10.5 }}>₹{uCfg.spot.toFixed(1)}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Expiry Selector */}
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
          <span className="v3-region-note" style={{ fontSize: 11, marginRight: 2 }}>EXPIRY:</span>
          <div className="v3-expiry-select-group" role="tablist" aria-label="Option expiry selector">
            {cfg.expiries.map((exp) => (
              <button
                key={exp}
                role="tab"
                aria-selected={expiry === exp}
                className={`v3-expiry-btn ${expiry === exp ? "active" : ""}`}
                onClick={() => setExpiry(exp)}
              >
                {exp}
              </button>
            ))}
          </div>
        </div>

        {/* Strike Filter / Range */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginLeft: "auto", flexWrap: "wrap" }}>
          <div className="v3-timeframe-group">
            <button
              className={`v3-tf-btn ${strikeRange === "ATM_10" ? "active" : ""}`}
              onClick={() => setStrikeRange("ATM_10")}
            >
              Near ATM
            </button>
            <button
              className={`v3-tf-btn ${strikeRange === "ALL" ? "active" : ""}`}
              onClick={() => setStrikeRange("ALL")}
            >
              All Strikes
            </button>
          </div>

          <div className="v3-timeframe-group">
            <button
              className={`v3-tf-btn ${filterView === "ALL" ? "active" : ""}`}
              onClick={() => setFilterView("ALL")}
            >
              Both
            </button>
            <button
              className={`v3-tf-btn ${filterView === "CALLS" ? "active" : ""}`}
              onClick={() => setFilterView("CALLS")}
            >
              Calls
            </button>
            <button
              className={`v3-tf-btn ${filterView === "PUTS" ? "active" : ""}`}
              onClick={() => setFilterView("PUTS")}
            >
              Puts
            </button>
          </div>

          <TruthChip kind="SAMPLE" title="Options strike ladder — simulated option prices." />
        </div>
      </div>

      {/* ── Global Option Strike Policy Context ── */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 10,
          padding: "8px 12px",
          background: "var(--v3-surface-2)",
          border: "1px solid var(--v3-line-strong)",
          borderRadius: 8,
          marginBottom: 10,
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Icon name="layers" size={14} style={{ color: "var(--v3-profit)" }} />
          <span style={{ fontSize: 12, color: "var(--v3-ink)" }}>
            Global Strike Policy Target: <b>{policyRes.policyDescription}</b> · Target Strikes: <b>{policyRes.ceStrike} CE</b> / <b>{policyRes.peStrike} PE</b>
          </span>
          <span
            className="v3-chip"
            style={{
              background: "rgba(16, 185, 129, 0.12)",
              color: "var(--v3-profit-text)",
              borderColor: "rgba(16, 185, 129, 0.35)",
              fontSize: 9.5,
              fontWeight: 700,
            }}
          >
            GLOBAL · APPLIES TO ALL STRATEGIES
          </span>
        </div>
        <span className="v3-mono v3-dim" style={{ fontSize: 10.5 }}>
          Unified Strategy Envelope
        </span>
      </div>

      {/* ── ATM Resolution & Calculation Authority Footnote ── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "0 4px 10px", flexWrap: "wrap" }}>
        <span className="v3-region-note" style={{ fontSize: 11.5 }}>
          ATM Reference: <b style={{ color: "#fde68a" }}>{resolvedAtm}</b> (Resolved from Spot <b>₹{cfg.spot.toFixed(2)}</b> via {cfg.step}pt interval rounding · SAMPLE)
        </span>
        <span className="v3-region-note" style={{ fontSize: 11, color: "var(--v3-ink-dim)" }}>
          Greeks: <b style={{ color: "var(--v3-warn-text)" }}>DEV SAMPLE / ESTIMATED</b> (Non-authoritative simulation)
        </span>
      </div>

      {/* ── Selected Contract Context Banner ── */}
      {selectedContract && (
        <div className="v3-selected-contract-banner">
          <div className="v3-contract-tag">
            <Dot tone={selectedContract.change >= 0 ? "ok" : "neg"} />
            <span className="v3-contract-title">
              {selectedContract.underlying} {selectedContract.expiry} <b>{selectedContract.strike} {selectedContract.optionType}</b>
            </span>
          </div>

          <div className="v3-contract-sub">
            <span
              className={
                selectedContract.moneyness === "ATM"
                  ? "v3-atm-badge"
                  : selectedContract.moneyness === "ITM"
                  ? "v3-itm-badge"
                  : "v3-otm-badge"
              }
            >
              {selectedContract.moneyness}
            </span>
            <span className="v3-mono v3-dim">Lot: {selectedContract.lotSize}</span>
            <span className="v3-mono" style={{ fontWeight: 700, color: "var(--v3-ink)" }}>
              LTP ₹{selectedContract.ltp.toFixed(2)}
            </span>
            <span className={selectedContract.change >= 0 ? "v3-profit-text" : "v3-loss-text"} style={{ font: "600 12px var(--v3-mono)" }}>
              {fmtSignedINR(selectedContract.change, 2)} ({fmtSignedPct(selectedContract.changePct)})
            </span>
          </div>

          <div className="v3-greeks-row">
            <span title="Implied Volatility (Sample)">IV: <b>{selectedContract.iv}</b></span>
            <span title="Delta (DEV SAMPLE / ESTIMATED)">Δ: <b>{selectedContract.delta}</b></span>
            <span title="Theta (DEV SAMPLE / ESTIMATED)">θ: <b>{selectedContract.theta}</b></span>
            <span title="Open Interest">OI: <b>{selectedContract.oi}</b></span>
            <span className="v3-chip disabled" style={{ padding: "2px 7px", fontSize: 9 }} title="Production Greeks calculation authority not attached in this prototype.">
              GREEKS · DEV ESTIMATED
            </span>

            {onViewContractChart && (
              <button
                className="v3-btn primary mini"
                onClick={() => onViewContractChart(selectedContract)}
                title="Load this contract into the interactive chart"
              >
                <Icon name="chart" size={13} /> View Contract Chart
              </button>
            )}

            <button
              className="v3-btn ghost mini"
              onClick={() => setDrawerContract(selectedContract)}
              title="Open contract details & Greek estimates breakdown"
            >
              <Icon name="activity" size={13} /> Details
            </button>
          </div>
        </div>
      )}

      {/* ── Desktop Professional Strike Ladder ── */}
      <div className="v3-ladder-wrap" role="region" aria-label="Options Strike Ladder">
        {/* Ladder Header */}
        <div className="v3-ladder-head">
          <div className="h-calls">
            <span>IV (EST)</span>
            <span>OI</span>
            <span>CHG%</span>
            <span>CALL LTP</span>
          </div>
          <div className="h-strike">
            STRIKE (ATM: {resolvedAtm})
          </div>
          <div className="h-puts">
            <span>PUT LTP</span>
            <span>CHG%</span>
            <span>OI</span>
            <span>IV (EST)</span>
          </div>
        </div>

        {/* Ladder Rows */}
        <div className="v3-ladder-body">
          {visibleRows.map((row) => {
            const isCallSelected =
              selectedContract?.strike === row.strike && selectedContract?.optionType === "CE";
            const isPutSelected =
              selectedContract?.strike === row.strike && selectedContract?.optionType === "PE";
            const isPolicyTarget = row.strike === policyRes.ceStrike || row.strike === policyRes.peStrike;

            return (
              <div
                key={row.strike}
                className={`v3-ladder-row ${row.isAtm ? "atm-row" : ""}`}
              >
                {/* ── CALLS (LEFT) ── */}
                <div
                  className={`v3-ladder-call-cell ${row.call.moneyness === "ITM" ? "itm" : ""} ${
                    isCallSelected ? "selected" : ""
                  }`}
                  onClick={() => handleSelect(row.strike, "CE", row.call, row.call.moneyness)}
                  title={`Select ${underlying} ${row.strike} CE (${row.call.moneyness}) · Delta: ${row.call.delta} (EST)`}
                >
                  <span className="v3-dim" style={{ fontSize: 10.5 }}>{row.call.iv}</span>
                  <span className="v3-ink3" style={{ fontSize: 11 }}>{row.call.oi}</span>
                  <span className={row.call.change >= 0 ? "v3-profit-text" : "v3-loss-text"}>
                    {fmtSignedPct(row.call.changePct, 1)}
                  </span>
                  <span style={{ fontWeight: 700, color: isCallSelected ? "var(--v3-ink)" : "var(--v3-ink)" }}>
                    ₹{row.call.ltp.toFixed(2)}
                  </span>
                </div>

                {/* ── STRIKE (CENTER) ── */}
                <div className={`v3-ladder-strike-cell ${row.isAtm ? "atm" : ""}`}>
                  <span>{row.strike}</span>
                  {row.isAtm ? (
                    <span className="v3-atm-badge" style={{ marginTop: 2 }}>ATM</span>
                  ) : (
                    <div style={{ display: "flex", gap: 4, marginTop: 2, alignItems: "center" }}>
                      <span className="v3-dim" style={{ fontSize: 9 }}>C:{row.call.moneyness}</span>
                      <span className="v3-dim" style={{ fontSize: 9 }}>P:{row.put.moneyness}</span>
                    </div>
                  )}
                  {isPolicyTarget && (
                    <span
                      className="v3-tag"
                      style={{
                        marginTop: 2,
                        fontSize: 8.5,
                        padding: "1px 4px",
                        background: "rgba(16, 185, 129, 0.15)",
                        color: "var(--v3-profit-text)",
                        borderColor: "rgba(16, 185, 129, 0.35)",
                      }}
                      title="Target strike under active Global Option Strike Policy"
                    >
                      TARGET
                    </span>
                  )}
                </div>

                {/* ── PUTS (RIGHT) ── */}
                <div
                  className={`v3-ladder-put-cell ${row.put.moneyness === "ITM" ? "itm" : ""} ${
                    isPutSelected ? "selected" : ""
                  }`}
                  onClick={() => handleSelect(row.strike, "PE", row.put, row.put.moneyness)}
                  title={`Select ${underlying} ${row.strike} PE (${row.put.moneyness}) · Delta: ${row.put.delta} (EST)`}
                >
                  <span style={{ fontWeight: 700, color: isPutSelected ? "var(--v3-ink)" : "var(--v3-ink)" }}>
                    ₹{row.put.ltp.toFixed(2)}
                  </span>
                  <span className={row.put.change >= 0 ? "v3-profit-text" : "v3-loss-text"}>
                    {fmtSignedPct(row.put.changePct, 1)}
                  </span>
                  <span className="v3-ink3" style={{ fontSize: 11 }}>{row.put.oi}</span>
                  <span className="v3-dim" style={{ fontSize: 10.5 }}>{row.put.iv}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Mobile Adaptive Options View ── */}
      <div className="v3-mobile-options-card">
        {/* Mobile CE / PE Tab Split */}
        <div className="v3-tabs" style={{ marginBottom: 12 }}>
          <button
            className={`v3-tab ${mobileTab === "CE" ? "active" : ""}`}
            onClick={() => setMobileTab("CE")}
          >
            Calls (CE)
          </button>
          <button
            className={`v3-tab ${mobileTab === "PE" ? "active" : ""}`}
            onClick={() => setMobileTab("PE")}
          >
            Puts (PE)
          </button>
        </div>

        {/* Mobile Strikes List */}
        <div className="v3-rows">
          {visibleRows.map((row) => {
            const leg = mobileTab === "CE" ? row.call : row.put;
            const isSelected =
              selectedContract?.strike === row.strike && selectedContract?.optionType === mobileTab;

            return (
              <div
                key={row.strike}
                className="v3-mobile-strike-item"
                onClick={() => handleSelect(row.strike, mobileTab, leg, leg.moneyness)}
                style={{
                  background: isSelected ? "var(--v3-surface-3)" : row.isAtm ? "rgba(245, 158, 11, 0.08)" : "transparent",
                  cursor: "pointer",
                }}
              >
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ font: "700 14px var(--v3-mono)", color: "var(--v3-ink)" }}>{row.strike}</span>
                    <span
                      className={
                        leg.moneyness === "ATM"
                          ? "v3-atm-badge"
                          : leg.moneyness === "ITM"
                          ? "v3-itm-badge"
                          : "v3-otm-badge"
                      }
                    >
                      {mobileTab} · {leg.moneyness}
                    </span>
                  </div>
                  <div className="v3-row-sub" style={{ marginTop: 2 }}>
                    OI: {leg.oi} · Δ: {leg.delta} (EST)
                  </div>
                </div>

                <div style={{ textAlign: "right" }}>
                  <div style={{ font: "700 14px var(--v3-mono)", color: "var(--v3-ink)" }}>₹{leg.ltp.toFixed(2)}</div>
                  <div className={leg.change >= 0 ? "v3-profit-text" : "v3-loss-text"} style={{ font: "600 11.5px var(--v3-mono)" }}>
                    {fmtSignedINR(leg.change, 2)} ({fmtSignedPct(leg.changePct)})
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Contract Detail & Greeks Truth Drawer ── */}
      <Drawer
        open={drawerContract !== null}
        title={drawerContract ? `${drawerContract.underlying} ${drawerContract.expiry} ${drawerContract.strike} ${drawerContract.optionType}` : ""}
        sub="Contract Specifications & Truth Disclosure"
        onClose={() => setDrawerContract(null)}
      >
        {drawerContract && (
          <>
            <dl style={{ margin: "0 0 20px" }}>
              <KV k="Underlying" v={drawerContract.underlying} />
              <KV k="Underlying Spot" v={`₹${cfg.spot.toFixed(2)}`} />
              <KV k="Resolved ATM" v={`${resolvedAtm} (${cfg.step}pt interval)`} />
              <KV k="Expiry Date" v={drawerContract.expiry} />
              <KV k="Strike Price" v={`₹${drawerContract.strike.toLocaleString()}`} />
              <KV k="Option Type" v={drawerContract.optionType === "CE" ? "Call Option (CE)" : "Put Option (PE)"} />
              <KV k="Moneyness Context" v={`${drawerContract.moneyness} (${drawerContract.optionType === "CE" ? (drawerContract.strike < cfg.spot ? "Spot > Strike" : drawerContract.strike === resolvedAtm ? "Near Spot" : "Spot < Strike") : (drawerContract.strike > cfg.spot ? "Strike > Spot" : drawerContract.strike === resolvedAtm ? "Near Spot" : "Strike < Spot")})`} />
              <KV k="Last Traded Price" v={`₹${drawerContract.ltp.toFixed(2)}`} />
              <KV
                k="Day Change"
                v={`${fmtSignedINR(drawerContract.change, 2)} (${fmtSignedPct(drawerContract.changePct)})`}
                vClass={drawerContract.change >= 0 ? "v3-profit-text" : "v3-loss-text"}
              />
              <KV k="Bid / Ask Spread" v={`₹${drawerContract.bid.toFixed(2)} / ₹${drawerContract.ask.toFixed(2)}`} />
              <KV k="Open Interest (OI)" v={`${drawerContract.oi} (${drawerContract.oiChange})`} />
              <KV k="Implied Volatility (IV)" v={drawerContract.iv} />
              <KV k="Delta (Δ)" v={`${drawerContract.delta} (DEV ESTIMATED)`} />
              <KV k="Theta (θ)" v={`${drawerContract.theta} pts/day (DEV ESTIMATED)`} />
              <KV k="Gamma (γ)" v={`${drawerContract.gamma} (DEV ESTIMATED)`} />
              <KV k="Vega (ν)" v={`${drawerContract.vega} (DEV ESTIMATED)`} />
              <KV k="Lot Size" v={drawerContract.lotSize.toString()} />
              <KV k="Greeks Authority" v="DEV SAMPLE / ESTIMATED — Non-Authoritative" vClass="v3-warn-text" />
              <KV k="Price Feed Authority" v="DEV PREVIEW / SAMPLE — Simulated" />
            </dl>

            {onViewContractChart && (
              <button
                className="v3-btn primary"
                style={{ width: "100%", marginTop: 12 }}
                onClick={() => {
                  onViewContractChart(drawerContract);
                  setDrawerContract(null);
                }}
              >
                <Icon name="chart" size={15} /> Switch Main Chart to this Contract
              </button>
            )}
          </>
        )}
      </Drawer>
    </div>
  );
};
