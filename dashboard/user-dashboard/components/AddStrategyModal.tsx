import React, { useState } from "react";
import { Icon } from "../../shared/icons/V3Icons";
import { TruthChip, Dot, Drawer } from "../../shared/utilities/V3Chrome";
import { STRATEGY_TEMPLATES, type StrategyTemplate, type StrategyRow } from "../../sampleData";

export interface AddStrategyModalProps {
  open: boolean;
  onClose: () => void;
  onAddStrategy?: (strategy: StrategyRow) => void;
}

type OnboardingTab = "UPLOAD" | "CREATE" | "TEMPLATE";

export const AddStrategyModal: React.FC<AddStrategyModalProps> = ({ open, onClose, onAddStrategy }) => {
  const [tab, setTab] = useState<OnboardingTab>("UPLOAD");
  const [strategyName, setStrategyName] = useState("");
  const [description, setDescription] = useState("");
  const [instruments, setInstruments] = useState<string[]>(["NIFTY"]);
  const [uploadedFile, setUploadedFile] = useState<string | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<StrategyTemplate>(STRATEGY_TEMPLATES[0]);
  const [scanRunning, setScanRunning] = useState(false);
  const [scanResult, setScanResult] = useState<"IDLE" | "PASSED" | "FAILED">("IDLE");

  if (!open) return null;

  const handleSimulateScan = () => {
    setScanRunning(true);
    setTimeout(() => {
      setScanRunning(false);
      setScanResult("PASSED");
    }, 600);
  };

  const handleRegister = () => {
    if (!strategyName.trim()) return;
    const newStrat: StrategyRow = {
      id: `strat-${Date.now().toString().slice(-4)}`,
      name: strategyName.trim(),
      version: "v0.1",
      language: "Python",
      stage: "BACKTEST_ELIGIBLE",
      quality: 60,
      evidenceAttached: false,
      pnl: "n/a",
      isProfit: true,
      note: "Static scan passed · registered in governed chain",
      description: description || "User uploaded Python strategy.",
      author: "Alexander Vance",
      lastUpdated: "Just now",
      scanStatus: "PASSED",
      conformanceCheck: "CONFORMANT",
      winRate: 60.0,
      maxDrawdown: -4.5,
      profitFactor: 1.5,
      sharpeRatio: 1.3,
      totalTrades: 0,
      activePositions: 0,
    };
    if (onAddStrategy) onAddStrategy(newStrat);
    onClose();
  };

  const toggleInstrument = (inst: string) => {
    setInstruments((prev) =>
      prev.includes(inst) ? (prev.length > 1 ? prev.filter((i) => i !== inst) : prev) : [...prev, inst]
    );
  };

  return (
    <>
      <button className="v3-backdrop" aria-label="Close add strategy modal" onClick={onClose} />
      <aside className="v3-drawer" style={{ width: "min(640px, 94vw)" }} role="dialog" aria-modal="true" aria-label="Add Python Strategy">
        <div className="v3-drawer-head">
          <div>
            <h3 className="v3-drawer-title">+ Add Strategy</h3>
            <div className="v3-row-sub">Governed Python Strategy Onboarding · DEV PREVIEW</div>
          </div>
          <button className="v3-btn ghost mini" onClick={onClose} aria-label="Close modal">
            <Icon name="close" size={14} /> Close
          </button>
        </div>

        <div className="v3-drawer-body">
          {/* ── Method Tabs ── */}
          <div className="v3-tabs" style={{ marginBottom: 18 }}>
            <button
              className={`v3-tab ${tab === "UPLOAD" ? "active" : ""}`}
              onClick={() => setTab("UPLOAD")}
            >
              <Icon name="upload" size={13} style={{ marginRight: 6 }} /> Upload Python (.py)
            </button>
            <button
              className={`v3-tab ${tab === "CREATE" ? "active" : ""}`}
              onClick={() => setTab("CREATE")}
            >
              <Icon name="code" size={13} style={{ marginRight: 6 }} /> Create New
            </button>
            <button
              className={`v3-tab ${tab === "TEMPLATE" ? "active" : ""}`}
              onClick={() => setTab("TEMPLATE")}
            >
              <Icon name="layers" size={13} style={{ marginRight: 6 }} /> From Template
            </button>
          </div>

          {/* ── Governed Lifecycle Progression Diagram ── */}
          <div className="v3-lifecycle-diagram" style={{ margin: "4px 0 14px" }}>
            <div className="v3-lifecycle-step done">
              <span className="step-num">1</span>
              <span>Static Scan</span>
            </div>
            <span className="step-arrow">→</span>
            <div className="v3-lifecycle-step done">
              <span className="step-num">2</span>
              <span>Conformance</span>
            </div>
            <span className="step-arrow">→</span>
            <div className="v3-lifecycle-step active">
              <span className="step-num">3</span>
              <span>Backtest Evidence</span>
            </div>
            <span className="step-arrow">→</span>
            <div className="v3-lifecycle-step">
              <span className="step-num">4</span>
              <span>Paper Evaluation</span>
            </div>
            <span className="step-arrow">→</span>
            <div className="v3-lifecycle-step">
              <span className="step-num">5</span>
              <span>LIVE_ELIGIBLE</span>
            </div>
          </div>

          <div className="v3-governed-note" style={{ margin: "12px 0 20px" }}>
            <Dot tone="warn" />
            <span>
              <b>Governed Lifecycle Invariant:</b> Direct live promotion is strictly prohibited.
              All uploaded strategies must complete: <b>Static Scan → Conformance → Backtest Evidence → Paper Evaluation → Explicit LIVE_ELIGIBLE Promotion</b>.
            </span>
          </div>

          {/* ── TAB 1: UPLOAD PYTHON FILE ── */}
          {tab === "UPLOAD" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {/* Dropzone */}
              <div
                className="v3-dropzone"
                onClick={() => setUploadedFile("nifty_mean_reversion_v1.py")}
                title="Click to simulate strategy file selection"
              >
                <Icon name="upload" size={28} className="v3-dim" />
                <div style={{ fontWeight: 600, fontSize: 13.5, color: "var(--v3-ink)" }}>
                  {uploadedFile ? uploadedFile : "Drag & drop your Python strategy (.py) or click to browse"}
                </div>
                <span className="v3-row-sub" style={{ marginTop: 2 }}>
                  Must inherit from <code>algofortis.strategy.BaseStrategy</code> · Max 5MB
                </span>
                {uploadedFile && (
                  <span className="v3-itm-badge" style={{ marginTop: 6 }}>
                    <Icon name="check" size={12} /> File attached · 4.2 KB
                  </span>
                )}
              </div>

              {/* Strategy Name & Description Inputs */}
              <div>
                <label className="v3-field-label">Strategy Name</label>
                <input
                  className="v3-input"
                  placeholder="e.g. NIFTY Volatility Skew Reversion"
                  value={strategyName}
                  onChange={(e) => setStrategyName(e.target.value)}
                />
              </div>

              <div>
                <label className="v3-field-label">Description (Optional)</label>
                <input
                  className="v3-input"
                  placeholder="Brief summary of entry/exit rules and target market regime"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </div>

              {/* Target Instruments */}
              <div>
                <label className="v3-field-label">Target Instruments</label>
                <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                  {["NIFTY", "BANKNIFTY"].map((inst) => (
                    <button
                      key={inst}
                      type="button"
                      className={`v3-tf-btn ${instruments.includes(inst) ? "active" : ""}`}
                      onClick={() => toggleInstrument(inst)}
                      style={{ padding: "6px 14px", fontSize: 12 }}
                    >
                      {inst}
                    </button>
                  ))}
                </div>
              </div>

              {/* Static Scan Button */}
              {scanResult === "IDLE" ? (
                <button
                  className="v3-btn primary"
                  disabled={!uploadedFile || !strategyName.trim() || scanRunning}
                  onClick={handleSimulateScan}
                  style={{ width: "100%", marginTop: 8 }}
                >
                  <Icon name="shield" size={15} /> {scanRunning ? "Running AST Security Scan…" : "Run Static Scan & Register Strategy"}
                </button>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 4 }}>
                  <div className="v3-stat-line" style={{ color: "var(--v3-profit-text)", fontWeight: 600 }}>
                    <Icon name="check" size={16} /> Static AST scan passed (0 syntax errors, 0 unauthorized syscalls, BaseStrategy conformant).
                  </div>
                  <button className="v3-btn primary" onClick={handleRegister} style={{ width: "100%" }}>
                    <Icon name="check" size={15} /> Register as BACKTEST_ELIGIBLE
                  </button>
                </div>
              )}
            </div>
          )}

          {/* ── TAB 2: CREATE NEW STRATEGY ── */}
          {tab === "CREATE" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div>
                <label className="v3-field-label">Strategy Name</label>
                <input
                  className="v3-input"
                  placeholder="e.g. NIFTY Iron Condor Automated"
                  value={strategyName}
                  onChange={(e) => setStrategyName(e.target.value)}
                />
              </div>

              <div>
                <label className="v3-field-label">Python Starter Code</label>
                <div className="v3-code-preview">
                  <pre>{`from algofortis.strategy import BaseStrategy, Signal, OrderType

class CustomStrategy(BaseStrategy):
    """AlgoFortis Governed Strategy Template"""
    
    def on_tick(self, tick):
        # 1. Enforce pre-trade risk envelope
        if not self.risk_watchdog.is_safe():
            return
            
        # 2. Compute signal logic
        # Your execution logic here
        pass`}</pre>
                </div>
              </div>

              <button
                className="v3-btn primary"
                disabled={!strategyName.trim()}
                onClick={handleRegister}
                style={{ width: "100%", marginTop: 8 }}
              >
                <Icon name="code" size={15} /> Create Draft Strategy (DEV PREVIEW)
              </button>
            </div>
          )}

          {/* ── TAB 3: START FROM TEMPLATE ── */}
          {tab === "TEMPLATE" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="v3-rows">
                {STRATEGY_TEMPLATES.map((tmpl) => (
                  <div
                    key={tmpl.id}
                    className={`v3-row ${selectedTemplate.id === tmpl.id ? "active" : ""}`}
                    style={{
                      cursor: "pointer",
                      padding: "12px 14px",
                      borderRadius: 12,
                      border: selectedTemplate.id === tmpl.id ? "1px solid var(--v3-line-strong)" : "1px solid var(--v3-line)",
                      background: selectedTemplate.id === tmpl.id ? "var(--v3-surface-3)" : "transparent",
                    }}
                    onClick={() => {
                      setSelectedTemplate(tmpl);
                      setStrategyName(tmpl.name);
                    }}
                  >
                    <div className="v3-row-main">
                      <div className="v3-row-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span>{tmpl.name}</span>
                        <span className="v3-itm-badge" style={{ fontSize: 9.5 }}>{tmpl.category}</span>
                      </div>
                      <div className="v3-row-sub" style={{ marginTop: 3 }}>
                        {tmpl.description}
                      </div>
                    </div>
                    <span className="v3-mono v3-dim" style={{ fontSize: 10 }}>{tmpl.complexity}</span>
                  </div>
                ))}
              </div>

              <button
                className="v3-btn primary"
                onClick={() => {
                  setStrategyName(selectedTemplate.name);
                  handleRegister();
                }}
                style={{ width: "100%", marginTop: 8 }}
              >
                <Icon name="layers" size={15} /> Use Template: {selectedTemplate.name}
              </button>
            </div>
          )}

          <div style={{ marginTop: 24, paddingTop: 12, borderTop: "1px solid var(--v3-line)" }}>
            <TruthChip kind="SAMPLE" title="Strategy onboarding simulation — non-authoritative." />
          </div>
        </div>
      </aside>
    </>
  );
};
