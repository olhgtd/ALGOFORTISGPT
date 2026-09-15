import React, { useState, useMemo } from "react";
import { Icon } from "../../shared/icons/V3Icons";
import { Panel, Drawer, KV, TruthChip, Dot } from "../../shared/utilities/V3Chrome";
import {
  getStoredOwnerReports,
  getStoredOwnerAuditEvents,
  requestReportGenerationSimulated,
  type OwnerReportRow,
  type OwnerAuditRow,
  type ReportCategoryType,
} from "../../sampleData";
import { queryAuditEvents, queryOwnerReports, type IntegrationResult, type AuthoritativeReportItem } from "../../shared/services/integrationClient";

export interface AdminReportsAuditScreenProps {
  initialTab?: "reports" | "audit";
  go?: (screenId: string) => void;
  previewMode?: boolean;
}

const SEVERITY_TONE: Record<string, "ok" | "warn" | "neg" | "dim" | "live"> = {
  INFO: "ok",
  WARNING: "warn",
  CRITICAL: "neg",
};

const STATUS_TONE: Record<string, "ok" | "warn" | "neg" | "dim" | "live"> = {
  SUCCESS: "ok",
  READY: "ok",
  APPROVED: "ok",
  REJECTED: "warn",
  FAILED: "neg",
  CRITICAL: "neg",
  CANCELLED: "dim",
  EXPIRED: "dim",
  GENERATING: "live",
  REQUESTED: "dim",
};

export const AdminReportsAuditScreen: React.FC<AdminReportsAuditScreenProps> = ({
  initialTab = "reports",
  go,
  previewMode = false,
}) => {
  const [activeTab, setActiveTab] = useState<"reports" | "audit">(initialTab);
  const [reports, setReports] = useState<OwnerReportRow[]>(() => previewMode ? getStoredOwnerReports() : []);
  const [auditEvents, setAuditEvents] = useState<OwnerAuditRow[]>(() => getStoredOwnerAuditEvents());
  const [auditIntegration, setAuditIntegration] = useState<IntegrationResult<OwnerAuditRow[]>>({
    data: getStoredOwnerAuditEvents(),
    source: "SAMPLE_FALLBACK",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: true,
  });

  React.useEffect(() => {
    let isMounted = true;
    queryAuditEvents().then((res) => {
      if (isMounted) {
        setAuditIntegration(res);
        setAuditEvents(res.data);
      }
    });
    if (!previewMode) {
      queryOwnerReports().then((res) => {
        if (isMounted && res.source === "BACKEND") {
          const mapped: OwnerReportRow[] = res.data.map((r) => ({
            id: r.id,
            reportId: r.id,
            reportType: (r.category as any) || "BACKTEST_SUMMARY",
            title: r.title,
            scope: r.title,
            environment: "SYSTEM",
            period: r.period,
            generatedAt: r.generatedAt,
            status: (r.status as any) || "AVAILABLE",
            format: (r.format as any) || "JSON / SUMMARY",
            evidenceRef: r.id,
            metrics: { records: 1, size: r.fileSize },
            provenance: "AlgoFortis Authoritative Runtime",
            summary: r.summary,
          }));
          setReports(mapped);
        }
      });
    }
    return () => {
      isMounted = false;
    };
  }, [previewMode]);

  // Filters
  const [reportFilter, setReportFilter] = useState<string>("ALL");
  const [reportSearch, setReportSearch] = useState<string>("");
  const [auditFamilyFilter, setAuditFamilyFilter] = useState<string>("ALL");
  const [auditSeverityFilter, setAuditSeverityFilter] = useState<string>("ALL");
  const [auditSearch, setAuditSearch] = useState<string>("");

  // Selected drawers
  const [selectedReport, setSelectedReport] = useState<OwnerReportRow | null>(null);
  const [selectedAudit, setSelectedAudit] = useState<OwnerAuditRow | null>(null);
  const [requestModalOpen, setRequestModalOpen] = useState<boolean>(false);

  // New report request form state
  const [reqType, setReqType] = useState<ReportCategoryType>("BACKTEST_SUMMARY");
  const [reqScope, setReqScope] = useState<string>("SX-STRAT-001 (NIFTY Momentum)");
  const [reqEnv, setReqEnv] = useState<"BACKTEST" | "PAPER" | "LIVE / SAMPLE" | "SYSTEM">("BACKTEST");
  const [reqPeriod, setReqPeriod] = useState<string>("Last 30 Days");

  const [feedback, setFeedback] = useState<string | null>(null);
  const feedbackTimerRef = React.useRef<any>(null);

  const showFeedback = (msg: string) => {
    if (feedbackTimerRef.current) clearTimeout(feedbackTimerRef.current);
    setFeedback(msg);
    feedbackTimerRef.current = setTimeout(() => setFeedback(null), 4500);
  };

  const handleCopy = (text: string, label: string = "Reference") => {
    try {
      navigator.clipboard.writeText(text);
      showFeedback(`Copied ${label}: ${text}`);
    } catch {
      showFeedback(`Copied ${label}: ${text}`);
    }
  };

  const handleSimulateExport = (rep: OwnerReportRow, format: "CSV" | "JSON" | "PDF") => {
    showFeedback(`SIMULATED EXPORT REQUEST: ${rep.reportId} exported as ${format}. (DEV PREVIEW / SAMPLE — Prototype demonstration only)`);
  };

  const handleRequestReportSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const res = requestReportGenerationSimulated(reqType, reqScope, reqEnv, reqPeriod, "OWNER-001");
    if (res.success) {
      setReports(getStoredOwnerReports());
      setRequestModalOpen(false);
      showFeedback(res.message);
    }
  };

  // Filtered reports
  const filteredReports = useMemo(() => {
    return reports.filter((r) => {
      if (reportFilter !== "ALL" && r.reportType !== reportFilter) return false;
      if (reportSearch.trim()) {
        const q = reportSearch.toLowerCase();
        return (
          r.reportId.toLowerCase().includes(q) ||
          r.title.toLowerCase().includes(q) ||
          r.scope.toLowerCase().includes(q) ||
          r.period.toLowerCase().includes(q) ||
          (r.strategyId && r.strategyId.toLowerCase().includes(q))
        );
      }
      return true;
    });
  }, [reports, reportFilter, reportSearch]);

  // Filtered audit events
  const filteredAuditEvents = useMemo(() => {
    return auditEvents.filter((a) => {
      if (auditFamilyFilter !== "ALL" && a.eventFamily !== auditFamilyFilter) return false;
      if (auditSeverityFilter !== "ALL" && a.severity !== auditSeverityFilter) return false;
      if (auditSearch.trim()) {
        const q = auditSearch.toLowerCase();
        return (
          a.eventId.toLowerCase().includes(q) ||
          a.actor.toLowerCase().includes(q) ||
          a.eventFamily.toLowerCase().includes(q) ||
          a.eventType.toLowerCase().includes(q) ||
          a.entity.toLowerCase().includes(q) ||
          a.details.toLowerCase().includes(q) ||
          (a.reason && a.reason.toLowerCase().includes(q))
        );
      }
      return true;
    });
  }, [auditEvents, auditFamilyFilter, auditSeverityFilter, auditSearch]);

  return (
    <>
      {/* Header */}
      <div className="v3-screen-head">
        <div>
          <h2 className="v3-screen-title">Reports &amp; Audit Oversight</h2>
          <p className="v3-screen-sub">
            Institutional Evidence &amp; Prototype D16 Audit Projection · DEV PREVIEW / SAMPLE
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {activeTab === "reports" && (
            <button
              type="button"
              className="v3-btn primary mini"
              onClick={() => setRequestModalOpen(true)}
              id="open-request-report-modal-btn"
            >
              <Icon name="plus" size={13} />
              <span>+ SIMULATED REPORT REQUEST</span>
            </button>
          )}
          <TruthChip
            kind="REAL"
            title="Authoritative D16 Audit Ledger (Backend SQLite)"
          />
        </div>
      </div>

      {/* Observation & Boundary Banner */}
      <div
        className="security-notice-box"
        id="reports-audit-boundary-banner"
        style={{
          marginBottom: 16,
          borderColor: "rgba(56, 189, 248, 0.3)",
          background: "rgba(56, 189, 248, 0.05)",
        }}
      >
        <span className="sec-notice-icon" style={{ fontSize: 18 }}>🛡️</span>
        <div>
          <div style={{ fontWeight: 600, color: "var(--v3-sky-text)", fontSize: 12, marginBottom: 2 }}>
            AUTHORITATIVE D16 AUDIT LEDGER · IMMUTABLE JOURNAL OBSERVATION
          </div>
          <span style={{ fontSize: 11.5, color: "var(--v3-ink-2)" }}>
            This surface displays the authoritative projection of the AlgoFortis D16 audit schema. Journal persistence (SQLite WAL + synchronous=FULL) and cryptographic evidence verification are provided by the backend audit authority. The Owner UI exposes <strong>no mutation controls</strong> (pure read-only observation).
          </span>
        </div>
      </div>

      {feedback && (
        <div
          className="v3-feedback-banner ok"
          role="status"
          id="reports-audit-feedback-banner"
          style={{ marginBottom: 14 }}
        >
          ✓ {feedback}
        </div>
      )}

      {/* Tab Navigation */}
      <div className="v3-tabs" role="tablist" aria-label="Reports and Audit Tabs" style={{ marginBottom: 16 }}>
        <button
          role="tab"
          aria-selected={activeTab === "reports"}
          className={`v3-tab ${activeTab === "reports" ? "active" : ""}`}
          onClick={() => setActiveTab("reports")}
          id="tab-reports-inventory"
        >
          Institutional Reports ({reports.length})
        </button>
        <button
          role="tab"
          aria-selected={activeTab === "audit"}
          className={`v3-tab ${activeTab === "audit" ? "active" : ""}`}
          onClick={() => setActiveTab("audit")}
          id="tab-audit-ledger"
        >
          D16 Audit Journal &amp; Event Ledger ({auditEvents.length})
        </button>
      </div>

      {/* ════════════════════════════════════════════════════════════
         TAB 1: INSTITUTIONAL REPORTS INVENTORY
         ════════════════════════════════════════════════════════════ */}
      {activeTab === "reports" && (
        <Panel
          label="Institutional Reports &amp; Evidence Packages"
          meta={`${filteredReports.length} of ${reports.length} reports`}
          className="v3-sp12"
          id="reports-inventory-panel"
        >
          {/* Filter Bar */}
          <div style={{ display: "flex", gap: 10, marginBottom: 14, flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {(["ALL", "BACKTEST_SUMMARY", "PAPER_PERFORMANCE", "PORTFOLIO_EXPOSURE", "EXECUTION_QUALITY", "STRATEGY_CONFORMANCE", "RISK_REJECTIONS", "PAPER_RECONCILIATION", "DATASET_PROVENANCE", "ACCESS_ENTITLEMENT", "SYSTEM_AUDIT_LOG"] as const).map((cat) => {
                const label =
                  cat === "ALL"
                    ? "All"
                    : cat === "BACKTEST_SUMMARY"
                    ? "Backtests"
                    : cat === "PAPER_PERFORMANCE"
                    ? "Paper Sessions"
                    : cat === "PORTFOLIO_EXPOSURE"
                    ? "Portfolios"
                    : cat === "EXECUTION_QUALITY"
                    ? "Execution"
                    : cat === "STRATEGY_CONFORMANCE"
                    ? "Conformance"
                    : cat === "RISK_REJECTIONS"
                    ? "Risk Rejections"
                    : cat === "PAPER_RECONCILIATION"
                    ? "Reconciliation"
                    : cat === "DATASET_PROVENANCE"
                    ? "Datasets"
                    : cat === "ACCESS_ENTITLEMENT"
                    ? "Access"
                    : "System Audit";

                return (
                  <button
                    key={cat}
                    type="button"
                    className={`v3-btn mini ${reportFilter === cat ? "primary" : "ghost"}`}
                    onClick={() => setReportFilter(cat)}
                    id={`filter-rep-${cat.toLowerCase()}`}
                  >
                    {label}
                  </button>
                );
              })}
            </div>

            <div style={{ minWidth: 240, maxWidth: 320, flex: 1 }}>
              <input
                type="search"
                className="v3-input mini"
                placeholder="Search reports by ID, scope, period..."
                value={reportSearch}
                onChange={(e) => setReportSearch(e.target.value)}
                id="report-search-input"
              />
            </div>
          </div>

          {/* Reports Table */}
          <div className="v3-table-wrap">
            <table className="v3-table" id="reports-inventory-table">
              <thead>
                <tr>
                  <th style={{ whiteSpace: "nowrap" }}>REPORT ID</th>
                  <th style={{ whiteSpace: "nowrap" }}>REPORT TYPE / TITLE</th>
                  <th style={{ whiteSpace: "nowrap" }}>TARGET SCOPE</th>
                  <th style={{ whiteSpace: "nowrap" }}>ENV</th>
                  <th style={{ whiteSpace: "nowrap" }}>PERIOD</th>
                  <th style={{ whiteSpace: "nowrap" }}>GENERATED (UTC)</th>
                  <th style={{ whiteSpace: "nowrap" }}>STATUS</th>
                  <th style={{ whiteSpace: "nowrap" }}>FORMAT</th>
                  <th style={{ textAlign: "right", whiteSpace: "nowrap" }}>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {filteredReports.length === 0 ? (
                  <tr>
                    <td colSpan={9} style={{ textAlign: "center", padding: "28px", color: "var(--v3-ink-dim)" }}>
                      {reports.length === 0 ? "No reports yet" : "No reports match the selected filter."}
                    </td>
                  </tr>
                ) : (
                  filteredReports.map((r) => (
                    <tr key={r.id} className="v3-table-row" id={`report-row-${r.id}`}>
                      <td>
                        <button
                          type="button"
                          className="v3-table-code-btn"
                          onClick={() => handleCopy(r.reportId, "Report ID")}
                          id={`copy-repid-btn-${r.id}`}
                          title="Click to copy Report ID"
                        >
                          <span className="v3-mono font-bold" style={{ whiteSpace: "nowrap" }}>{r.reportId}</span>
                          <Icon name="copy" size={12} className="v3-dim" />
                        </button>
                      </td>
                      <td>
                        <div className="v3-cell-main font-semibold">{r.title}</div>
                        <div className="v3-cell-sub" style={{ fontSize: 10 }}>{r.reportType}</div>
                      </td>
                      <td>
                        <span className="v3-mono font-semibold" style={{ fontSize: 11 }}>{r.scope}</span>
                      </td>
                      <td>
                        <span className="v3-mono text-xs" style={{ whiteSpace: "nowrap" }}>{r.environment}</span>
                      </td>
                      <td>
                        <span className="v3-dim text-xs" style={{ whiteSpace: "nowrap" }}>{r.period}</span>
                      </td>
                      <td>
                        <span className="v3-mono text-xs" style={{ whiteSpace: "nowrap" }}>{r.generatedAt.split(" ")[0]}</span>
                      </td>
                      <td>
                        <span className={`v3-status-badge ${r.status.toLowerCase()}`} id={`badge-rep-status-${r.id}`}>
                          <Dot tone={STATUS_TONE[r.status] ?? "ok"} />
                          <span>{r.status}</span>
                        </span>
                      </td>
                      <td>
                        <span className="v3-mono text-xs v3-dim">{r.format}</span>
                      </td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        <div style={{ display: "inline-flex", gap: 5, justifyContent: "flex-end" }}>
                          <button
                            type="button"
                            className="v3-btn ghost mini"
                            onClick={() => setSelectedReport(r)}
                            id={`inspect-report-btn-${r.id}`}
                            title="Inspect full report evidence and metrics"
                          >
                            Inspect
                          </button>
                          <button
                            type="button"
                            className="v3-btn ghost mini"
                            onClick={() => handleSimulateExport(r, "CSV")}
                            id={`export-csv-btn-${r.id}`}
                            title="Simulate CSV export"
                          >
                            CSV
                          </button>
                          <button
                            type="button"
                            className="v3-btn ghost mini"
                            onClick={() => handleSimulateExport(r, "JSON")}
                            id={`export-json-btn-${r.id}`}
                            title="Simulate JSON export"
                          >
                            JSON
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {/* ════════════════════════════════════════════════════════════
         TAB 2: D16 AUDIT JOURNAL & EVENT LEDGER (PROTOTYPE PROJECTION)
         ════════════════════════════════════════════════════════════ */}
      {activeTab === "audit" && (
        <Panel
          label={
            auditIntegration.source === "BACKEND"
              ? "D16 Versioned Audit & Event Journal (Real Backend Projection · Read-Only)"
              : "D16 Versioned Audit & Event Journal (Prototype Projection · Read-Only)"
          }
          meta={
            auditIntegration.source === "BACKEND"
              ? `${filteredAuditEvents.length} of ${auditEvents.length} journal events (REAL BACKEND)`
              : `${filteredAuditEvents.length} of ${auditEvents.length} journal events (DEV PREVIEW)`
          }
          className="v3-sp12"
          id="audit-ledger-panel"
        >
          {/* Read-Only Notice Box */}
          <div
            style={{
              padding: "10px 14px",
              background: "var(--v3-surface-2)",
              borderRadius: 8,
              fontSize: 11,
              color: "var(--v3-ink-2)",
              lineHeight: 1.45,
              marginBottom: 14,
            }}
            id="audit-immutability-notice"
          >
            {auditIntegration.source === "BACKEND" ? (
              <span>
                ⚡ <strong>Real Backend Projection:</strong> Events below are queried from the engine SQLite WAL audit store. The Owner UI exposes zero mutation controls. Cryptographic immutability and durability are properties of the engine SQLite WAL store.
              </span>
            ) : (
              <span>
                🔒 <strong>Prototype Notice:</strong> Events below are prototype sample rows demonstrating the D16 schema taxonomy. The Owner UI exposes zero mutation controls. Cryptographic immutability and durability are properties of the engine SQLite WAL store, not this browser session.
              </span>
            )}
          </div>

          {/* Audit Filters Bar */}
          <div style={{ display: "flex", gap: 10, marginBottom: 14, flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
              <span className="v3-dim text-xs">Family:</span>
              <select
                className="v3-select mini"
                value={auditFamilyFilter}
                onChange={(e) => setAuditFamilyFilter(e.target.value)}
                id="audit-family-filter-select"
                style={{ minWidth: 150 }}
              >
                <option value="ALL">All Families</option>
                <option value="RISK_DECISION">Risk Decision (E6)</option>
                <option value="FILL">Fills & Executions (E9)</option>
                <option value="ORDER_LIFECYCLE">Order Lifecycle (E8)</option>
                <option value="PROTECTIVE_LIFECYCLE">Protective Lifecycle (E13)</option>
                <option value="ACCOUNTING_INTEGRITY">Accounting Integrity (E16)</option>
                <option value="PHASE9_MUTATION">Phase 9 Mutation (E22)</option>
                <option value="FEED_CONNECTIVITY">Feed Connectivity (E2)</option>
                <option value="SESSION">Session (E1)</option>
              </select>

              <span className="v3-dim text-xs" style={{ marginLeft: 6 }}>Severity:</span>
              <select
                className="v3-select mini"
                value={auditSeverityFilter}
                onChange={(e) => setAuditSeverityFilter(e.target.value)}
                id="audit-severity-filter-select"
                style={{ minWidth: 110 }}
              >
                <option value="ALL">All Severities</option>
                <option value="CRITICAL">Critical</option>
                <option value="WARNING">Warning</option>
                <option value="INFO">Info</option>
              </select>
            </div>

            <div style={{ minWidth: 240, maxWidth: 320, flex: 1 }}>
              <input
                type="search"
                className="v3-input mini"
                placeholder="Search audit events by ID, actor, details..."
                value={auditSearch}
                onChange={(e) => setAuditSearch(e.target.value)}
                id="audit-search-input"
              />
            </div>
          </div>

          {/* Audit Events Table */}
          <div className="v3-table-wrap">
            <table className="v3-table" id="audit-events-table">
              <thead>
                <tr>
                  <th style={{ whiteSpace: "nowrap" }}>EVENT ID</th>
                  <th style={{ whiteSpace: "nowrap" }}>TIMESTAMP (UTC)</th>
                  <th style={{ whiteSpace: "nowrap" }}>ACTOR</th>
                  <th style={{ whiteSpace: "nowrap" }}>FAMILY / TYPE</th>
                  <th style={{ whiteSpace: "nowrap" }}>SEVERITY</th>
                  <th style={{ whiteSpace: "nowrap" }}>STATUS</th>
                  <th style={{ whiteSpace: "nowrap" }}>TARGET ENTITY</th>
                  <th style={{ whiteSpace: "nowrap" }}>DETAILS</th>
                  <th style={{ textAlign: "right", whiteSpace: "nowrap" }}>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {filteredAuditEvents.length === 0 ? (
                  <tr>
                    <td colSpan={9} style={{ textAlign: "center", padding: "28px", color: "var(--v3-ink-dim)" }}>
                      {auditEvents.length === 0 ? "No audit events yet" : "No audit events match the selected filter."}
                    </td>
                  </tr>
                ) : (
                  filteredAuditEvents.map((a) => (
                    <tr key={a.id} className="v3-table-row" id={`audit-row-${a.id}`}>
                      <td>
                        <button
                          type="button"
                          className="v3-table-code-btn"
                          onClick={() => handleCopy(a.eventId, "Event ID")}
                          id={`copy-eventid-btn-${a.id}`}
                          title="Click to copy Event ID"
                        >
                          <span className="v3-mono font-bold" style={{ whiteSpace: "nowrap" }}>{a.eventId}</span>
                          <Icon name="copy" size={12} className="v3-dim" />
                        </button>
                      </td>
                      <td>
                        <span className="v3-mono text-xs" style={{ whiteSpace: "nowrap" }}>{a.timestamp.split(" ")[1]}</span>
                      </td>
                      <td>
                        <span className="v3-mono font-semibold text-xs" style={{ whiteSpace: "nowrap" }}>{a.actor}</span>
                      </td>
                      <td>
                        <div className="v3-cell-main font-semibold" style={{ fontSize: 11 }}>{a.eventFamily}</div>
                        <div className="v3-cell-sub" style={{ fontSize: 9.5 }}>{a.eventType}</div>
                      </td>
                      <td>
                        <span className={`v3-status-badge ${a.severity.toLowerCase()}`} id={`badge-severity-${a.id}`}>
                          <Dot tone={SEVERITY_TONE[a.severity] ?? "ok"} />
                          <span>{a.severity}</span>
                        </span>
                      </td>
                      <td>
                        <span className={`v3-status-badge ${a.status.toLowerCase()}`} id={`badge-audit-status-${a.id}`}>
                          <Dot tone={STATUS_TONE[a.status] ?? "ok"} />
                          <span>{a.status}</span>
                        </span>
                      </td>
                      <td>
                        <span className="v3-mono text-xs font-semibold" style={{ whiteSpace: "nowrap" }}>{a.entity}</span>
                      </td>
                      <td>
                        <div className="v3-dim" style={{ fontSize: 11, maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={a.details}>
                          {a.details}
                        </div>
                      </td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        <button
                          type="button"
                          className="v3-btn ghost mini"
                          onClick={() => setSelectedAudit(a)}
                          id={`inspect-audit-btn-${a.id}`}
                          title="Inspect audit event details and provenance"
                        >
                          Inspect
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </Panel>
      )}

      {/* ── Modal / Drawer: REPORT INSPECTION ── */}
      <Drawer
        open={selectedReport !== null}
        title={selectedReport?.reportId || ""}
        sub={selectedReport ? `${selectedReport.title} · ${selectedReport.environment} Scope (DEV PREVIEW)` : undefined}
        onClose={() => setSelectedReport(null)}
      >
        {selectedReport && (
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            {/* Identity & Scope */}
            <Panel label="Report Scope &amp; Metadata (DEV PREVIEW / SAMPLE)" id="drawer-report-metadata-panel">
              <dl style={{ margin: 0 }}>
                <KV k="Report ID" v={<span className="v3-mono font-bold" id="drawer-rep-id-val">{selectedReport.reportId}</span>} />
                <KV k="Report Category" v={<span className="v3-mono font-semibold">{selectedReport.reportType}</span>} />
                <KV k="Target Scope" v={<span className="v3-mono font-bold">{selectedReport.scope}</span>} />
                <KV k="Environment" v={<span className="v3-mono">{selectedReport.environment}</span>} />
                <KV k="Evaluation Period" v={<span className="v3-dim">{selectedReport.period}</span>} />
                <KV k="Generated Timestamp" v={<span className="v3-mono">{selectedReport.generatedAt}</span>} />
                <KV
                  k="Report Generation State"
                  v={
                    <span className={`v3-status-badge ${selectedReport.status.toLowerCase()}`} id="drawer-rep-status-val">
                      <Dot tone={STATUS_TONE[selectedReport.status] ?? "ok"} /> {selectedReport.status}
                    </span>
                  }
                />
                <KV k="Format Specification" v={<span className="v3-mono">{selectedReport.format}</span>} />
                <KV k="Sample Evidence Reference" v={<span className="v3-mono text-xs" style={{ color: "#38bdf8" }}>{selectedReport.evidenceRef}</span>} />
              </dl>
            </Panel>

            {/* Findings & Summary */}
            <Panel label="Executive Summary &amp; Findings" id="drawer-report-summary-panel">
              <p style={{ fontSize: 12.5, color: "var(--v3-ink-2)", lineHeight: 1.5, margin: 0 }}>
                {selectedReport.summary}
              </p>
            </Panel>

            {/* Evaluated Metrics */}
            <Panel label="Evaluated Sample Metrics &amp; Findings" id="drawer-report-metrics-panel">
              <div className="v3-rows">
                {Object.entries(selectedReport.metrics).map(([k, v], idx) => (
                  <div className="v3-row" key={idx}>
                    <span className="v3-row-title font-semibold">{k}</span>
                    <span className="v3-mono font-bold" style={{ color: "var(--v3-sky-text)" }}>{v}</span>
                  </div>
                ))}
              </div>
            </Panel>

            {/* Provenance & Subsystem */}
            <Panel label="Architectural Subsystem Authority" id="drawer-report-provenance-panel">
              <div style={{ fontSize: 11.5, color: "var(--v3-ink-3)", lineHeight: 1.45 }}>
                🏛️ <strong>Architectural Authority:</strong> {selectedReport.provenance} (Prototype Projection)
              </div>
            </Panel>

            {/* Actions */}
            <div style={{ display: "flex", gap: 8, marginTop: 6, flexWrap: "wrap" }}>
              <button
                type="button"
                className="v3-btn ghost mini"
                onClick={() => handleCopy(selectedReport.reportId, "Report ID")}
                id="drawer-copy-repid-btn"
              >
                <Icon name="copy" size={13} /> Copy Report ID
              </button>
              <button
                type="button"
                className="v3-btn ghost mini"
                onClick={() => handleCopy(selectedReport.evidenceRef, "Evidence Reference")}
                id="drawer-copy-evref-btn"
              >
                <Icon name="copy" size={13} /> Copy Evidence Ref
              </button>
              <button
                type="button"
                className="v3-btn primary mini"
                onClick={() => handleSimulateExport(selectedReport, "CSV")}
                id="drawer-sim-export-csv-btn"
              >
                Simulate Export CSV
              </button>
              <button
                type="button"
                className="v3-btn primary mini"
                onClick={() => handleSimulateExport(selectedReport, "JSON")}
                id="drawer-sim-export-json-btn"
              >
                Simulate Export JSON
              </button>
            </div>
          </div>
        )}
      </Drawer>

      {/* ── Modal / Drawer: AUDIT EVENT INSPECTION ── */}
      <Drawer
        open={selectedAudit !== null}
        title={selectedAudit?.eventId || ""}
        sub={selectedAudit ? `${selectedAudit.eventFamily} · ${selectedAudit.eventType} (DEV PREVIEW)` : undefined}
        onClose={() => setSelectedAudit(null)}
      >
        {selectedAudit && (
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            {/* Event Overview */}
            <Panel label="D16 Event Identity &amp; Classification (Prototype Projection)" id="drawer-audit-overview-panel">
              <dl style={{ margin: 0 }}>
                <KV k="Event ID" v={<span className="v3-mono font-bold" id="drawer-audit-eventid-val">{selectedAudit.eventId}</span>} />
                <KV k="Timestamp (UTC)" v={<span className="v3-mono font-semibold">{selectedAudit.timestamp}</span>} />
                <KV k="Actor" v={<span className="v3-mono font-bold" style={{ color: "#38bdf8" }}>{selectedAudit.actor} ({selectedAudit.actorType})</span>} />
                <KV k="Event Family (D16)" v={<span className="v3-mono font-semibold">{selectedAudit.eventFamily}</span>} />
                <KV k="Event Type" v={<span className="v3-mono">{selectedAudit.eventType}</span>} />
                <KV
                  k="Severity"
                  v={
                    <span className={`v3-status-badge ${selectedAudit.severity.toLowerCase()}`} id="drawer-audit-severity-val">
                      <Dot tone={SEVERITY_TONE[selectedAudit.severity] ?? "ok"} /> {selectedAudit.severity}
                    </span>
                  }
                />
                <KV
                  k="Event Result / Status"
                  v={
                    <span className={`v3-status-badge ${selectedAudit.status.toLowerCase()}`} id="drawer-audit-status-val">
                      <Dot tone={STATUS_TONE[selectedAudit.status] ?? "ok"} /> {selectedAudit.status}
                    </span>
                  }
                />
                <KV k="Target Entity" v={<span className="v3-mono font-bold">{selectedAudit.entity}</span>} />
                {selectedAudit.strategyId && <KV k="Strategy Ref" v={<span className="v3-mono">{selectedAudit.strategyId}</span>} />}
                {selectedAudit.orderId && <KV k="Order Ref" v={<span className="v3-mono">{selectedAudit.orderId}</span>} />}
                {selectedAudit.sessionId && <KV k="Session Ref" v={<span className="v3-mono">{selectedAudit.sessionId}</span>} />}
                {selectedAudit.accountId && <KV k="Account / User Ref" v={<span className="v3-mono">{selectedAudit.accountId}</span>} />}
              </dl>
            </Panel>

            {/* Event Details & Reason */}
            <Panel label="Audit Narrative &amp; Rejection Reason" id="drawer-audit-narrative-panel">
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div>
                  <div className="v3-region-note font-semibold" style={{ marginBottom: 4 }}>Event Description:</div>
                  <p style={{ fontSize: 12.5, color: "var(--v3-ink-2)", lineHeight: 1.5, margin: 0 }}>
                    {selectedAudit.details}
                  </p>
                </div>
                {selectedAudit.reason && (
                  <div style={{ padding: "8px 10px", background: "rgba(244, 63, 94, 0.1)", borderRadius: 6, border: "1px solid rgba(244, 63, 94, 0.25)" }}>
                    <div style={{ fontSize: 11, fontWeight: 650, color: "var(--sx-rose)", marginBottom: 2 }}>
                      Failure / Rejection Cause:
                    </div>
                    <span style={{ fontSize: 11.5, color: "var(--v3-ink-2)" }}>{selectedAudit.reason}</span>
                  </div>
                )}
              </div>
            </Panel>

            {/* Architectural Provenance (Step 8B distinction) */}
            <Panel label="Target Schema &amp; Storage Architecture" id="drawer-audit-crypto-panel">
              <dl style={{ margin: 0 }}>
                <KV k="Sample WAL Reference" v={<span className="v3-mono text-xs">{selectedAudit.evidenceRef}</span>} />
                <KV k="Target Envelope Schema" v={<span className="v3-mono text-xs">algofortis-audit-envelope/v2 (Architectural Contract)</span>} />
                <KV k="Target Storage Architecture" v={<span className="v3-dim text-xs">SQLite WAL + synchronous=FULL (Backend Authority)</span>} />
              </dl>
            </Panel>

            <div
              style={{
                padding: "10px 14px",
                background: "var(--v3-surface-2)",
                borderRadius: 8,
                fontSize: 11,
                color: "var(--v3-ink-2)",
                lineHeight: 1.45,
              }}
            >
              🔒 <strong>Immutability Boundary:</strong> Owner UI provides zero mutation controls (read-only inspection). Authoritative cryptographic tamper-evidence and persistence are enforced by the engine audit store upon backend integration.
            </div>

            {/* Cross-Surface Links */}
            <div style={{ display: "flex", gap: 8, marginTop: 4, flexWrap: "wrap" }}>
              <button
                type="button"
                className="v3-btn ghost mini"
                onClick={() => handleCopy(selectedAudit.eventId, "Event ID")}
                id="drawer-copy-eventid-btn"
              >
                <Icon name="copy" size={13} /> Copy Event ID
              </button>
              {selectedAudit.strategyId && go && (
                <button
                  type="button"
                  className="v3-btn ghost mini"
                  onClick={() => {
                    setSelectedAudit(null);
                    go("strategies");
                  }}
                  id="drawer-nav-strategy-btn"
                >
                  View Strategy in Step 4 →
                </button>
              )}
              {selectedAudit.orderId && go && (
                <button
                  type="button"
                  className="v3-btn ghost mini"
                  onClick={() => {
                    setSelectedAudit(null);
                    go("orders");
                  }}
                  id="drawer-nav-order-btn"
                >
                  View Order in Step 7 →
                </button>
              )}
              {selectedAudit.sessionId && go && (
                <button
                  type="button"
                  className="v3-btn ghost mini"
                  onClick={() => {
                    setSelectedAudit(null);
                    go("paper");
                  }}
                  id="drawer-nav-paper-btn"
                >
                  View Session in Step 6 →
                </button>
              )}
              {selectedAudit.accountId && go && (
                <button
                  type="button"
                  className="v3-btn ghost mini"
                  onClick={() => {
                    setSelectedAudit(null);
                    go("access-registry");
                  }}
                  id="drawer-nav-access-btn"
                >
                  View Access in Step 3 →
                </button>
              )}
            </div>
          </div>
        )}
      </Drawer>

      {/* ── Modal / Drawer: SIMULATED REPORT REQUEST ── */}
      <Drawer
        open={requestModalOpen}
        title="Simulated Report Request"
        sub="Generate an interactive prototype report snapshot (DEV PREVIEW / SAMPLE)"
        onClose={() => setRequestModalOpen(false)}
      >
        <form onSubmit={handleRequestReportSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div>
            <label className="v3-field-label" htmlFor="req-type">Report Category *</label>
            <select
              id="req-type"
              className="v3-select"
              value={reqType}
              onChange={(e) => setReqType(e.target.value as ReportCategoryType)}
            >
              <option value="BACKTEST_SUMMARY">Backtest Run Summary (EVIDENCE PACK)</option>
              <option value="PAPER_PERFORMANCE">Paper Trading Performance &amp; Fills (CSV)</option>
              <option value="PORTFOLIO_EXPOSURE">Portfolio Capital &amp; Margin Audit (JSON)</option>
              <option value="EXECUTION_QUALITY">Orders &amp; Execution Quality Report (CSV)</option>
              <option value="STRATEGY_CONFORMANCE">Strategy Conformance &amp; AST Scan (EVIDENCE PACK)</option>
              <option value="RISK_REJECTIONS">Pre-Trade Risk Rejections Audit (CSV)</option>
              <option value="PAPER_RECONCILIATION">Reconciliation &amp; Mismatch Analysis (JSON)</option>
              <option value="DATASET_PROVENANCE">Dataset Ingestion &amp; Calendar Integrity (EVIDENCE PACK)</option>
              <option value="ACCESS_ENTITLEMENT">Access Registry &amp; Entitlement Audit (CSV)</option>
              <option value="SYSTEM_AUDIT_LOG">System D16 Audit Ledger Snapshot (EVIDENCE PACK)</option>
            </select>
          </div>

          <div>
            <label className="v3-field-label" htmlFor="req-scope">Target Scope / Entity *</label>
            <input
              id="req-scope"
              type="text"
              className="v3-input"
              value={reqScope}
              onChange={(e) => setReqScope(e.target.value)}
              placeholder="e.g. SX-STRAT-001 or PORT-LIVE-PRIMARY"
              required
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label className="v3-field-label" htmlFor="req-env">Environment</label>
              <select
                id="req-env"
                className="v3-select"
                value={reqEnv}
                onChange={(e) => setReqEnv(e.target.value as any)}
              >
                <option value="BACKTEST">BACKTEST</option>
                <option value="PAPER">PAPER</option>
                <option value="LIVE / SAMPLE">LIVE / SAMPLE</option>
                <option value="SYSTEM">SYSTEM</option>
              </select>
            </div>
            <div>
              <label className="v3-field-label" htmlFor="req-period">Evaluation Period</label>
              <input
                id="req-period"
                type="text"
                className="v3-input"
                value={reqPeriod}
                onChange={(e) => setReqPeriod(e.target.value)}
                placeholder="e.g. Last 30 Days"
              />
            </div>
          </div>

          <div
            style={{
              padding: "10px 12px",
              background: "var(--v3-surface-2)",
              borderRadius: 6,
              fontSize: 11,
              color: "var(--v3-ink-3)",
              lineHeight: 1.4,
            }}
          >
            ⚠️ <strong>Disclaimer:</strong> This is a <strong>SIMULATED REPORT REQUEST</strong> for prototype demonstration. It creates a local evidence snapshot without triggering production backend pipelines.
          </div>

          <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
            <button
              type="submit"
              className="v3-btn primary"
              style={{ flex: 1 }}
              id="submit-sim-report-btn"
            >
              GENERATE SIMULATED REPORT
            </button>
            <button
              type="button"
              className="v3-btn ghost"
              onClick={() => setRequestModalOpen(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      </Drawer>
    </>
  );
};
