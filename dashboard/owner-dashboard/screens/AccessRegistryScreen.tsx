import React, { useState, useMemo, useEffect } from "react";
import { Icon } from "../../shared/icons/V3Icons";
import { Panel, Drawer, KV, TruthChip, Dot } from "../../shared/utilities/V3Chrome";
import {
  queryAccessRecords,
  createBackendUserAccess,
  reissueBackendActivation,
  revokeBackendActivation,
  suspendBackendAccount,
  restoreBackendAccount,
  revokeBackendAccount,
  extendBackendService,
  renewBackendService,
  convertBackendLifetime,
  deleteBackendDraft,
  isForceDemo,
  type IntegrationSource,
} from "../../shared/services/integrationClient";
import {
  getStoredAccessRecords,
  simulateFirstActivation,
  type AccessRecord,
  type AccessStatus,
  type ActivationStatus,
  type AccountAccessStatus,
  type ServiceEntitlementStatus,
  type ServiceTermType,
  type CustomServiceTerm,
  generatePrototypeSentinelxId,
  generatePrototypeActivationCode,
  maskEmail,
} from "../../sampleData";

const ACTIVATION_STATUS_TONE: Record<ActivationStatus, "ok" | "warn" | "neg" | "dim" | "live"> = {
  DRAFT: "dim",
  INVITED: "live",
  REDEEMED: "ok",
  EXPIRED: "warn",
  REVOKED: "neg",
};

const ACCOUNT_STATUS_TONE: Record<AccountAccessStatus, "ok" | "warn" | "neg" | "dim" | "live"> = {
  PENDING: "warn",
  ACTIVE: "ok",
  SUSPENDED: "neg",
  REVOKED: "neg",
};

const SERVICE_STATUS_TONE: Record<ServiceEntitlementStatus, "ok" | "warn" | "neg" | "dim" | "live"> = {
  NOT_STARTED: "dim",
  ACTIVE: "ok",
  EXPIRED: "warn",
};

export const AccessRegistryScreen: React.FC = () => {
  const [records, setRecords] = useState<AccessRecord[]>(() => isForceDemo() ? getStoredAccessRecords() : []);
  const [registrySource, setRegistrySource] = useState<IntegrationSource>("UNAVAILABLE");
  const [selectedRecord, setSelectedRecord] = useState<AccessRecord | null>(null);
  const [filter, setFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [feedback, setFeedback] = useState<string | null>(null);

  // Create User Access Modal State
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newRole, setNewRole] = useState("Quant Trader");
  const [newNotes, setNewNotes] = useState("");
  const [serviceTermChoice, setServiceTermChoice] = useState<ServiceTermType>("3_MONTHS");
  const [customValue, setCustomValue] = useState<number>(30);
  const [customUnit, setCustomUnit] = useState<"DAYS" | "MONTHS">("DAYS");
  const [generatedSxId, setGeneratedSxId] = useState(() => generatePrototypeSentinelxId());
  const [generatedActivationCode, setGeneratedActivationCode] = useState(() => generatePrototypeActivationCode());

  // Extend / Renew state in Drawer
  const [actionTermChoice, setActionTermChoice] = useState<ServiceTermType>("3_MONTHS");
  const [actionCustomValue, setActionCustomValue] = useState<number>(30);
  const [actionCustomUnit, setActionCustomUnit] = useState<"DAYS" | "MONTHS">("DAYS");

  const feedbackTimerRef = React.useRef<any>(null);

  const showFeedback = (msg: string) => {
    if (feedbackTimerRef.current) clearTimeout(feedbackTimerRef.current);
    setFeedback(msg);
    feedbackTimerRef.current = setTimeout(() => setFeedback(null), 4000);
  };

  const refreshRecords = async () => {
    const query = await queryAccessRecords();
    setRegistrySource(query.source);
    if (query.source === "BACKEND" && !query.error) {
      const backendData = (query.data || []) as any;
      setRecords(backendData);
      if (selectedRecord) {
        const refreshedSel = backendData.find(
          (r: any) => (r.sxId && r.sxId === selectedRecord.sxId) || r.id === selectedRecord.id
        );
        setSelectedRecord(refreshedSel || null);
      }
    } else if (isForceDemo()) {
      const updated = getStoredAccessRecords();
      setRecords(updated);
      if (selectedRecord) {
        const refreshedSel = updated.find(
          (r) => (r.sxId && r.sxId === selectedRecord.sxId) || r.id === selectedRecord.id
        );
        if (refreshedSel) setSelectedRecord(refreshedSel);
      }
    } else {
      setRecords([]);
      setSelectedRecord(null);
    }
  };

  useEffect(() => {
    refreshRecords();
  }, []);

  const filtered = useMemo(() => {
    return records.filter((r) => {
      if (filter === "INVITED" && r.activationStatus !== "INVITED") return false;
      if (filter === "REDEEMED" && r.activationStatus !== "REDEEMED") return false;
      if (filter === "ACTIVE" && r.accountStatus !== "ACTIVE") return false;
      if (filter === "PENDING" && r.accountStatus !== "PENDING") return false;
      if (filter === "EXPIRED" && r.activationStatus !== "EXPIRED") return false;
      if (filter === "SERVICE_ACTIVE" && r.serviceStatus !== "ACTIVE") return false;
      if (filter === "SERVICE_EXPIRED" && r.serviceStatus !== "EXPIRED") return false;
      if (filter === "SUSPENDED" && r.accountStatus !== "SUSPENDED") return false;
      if (filter === "REVOKED" && r.accountStatus !== "REVOKED" && r.activationStatus !== "REVOKED") return false;
      if (filter === "DRAFT" && r.activationStatus !== "DRAFT") return false;

      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return (
          (r.sxId && r.sxId.toLowerCase().includes(q)) ||
          (r.accessId && r.accessId.toLowerCase().includes(q)) ||
          (r.displayName && r.displayName.toLowerCase().includes(q)) ||
          (r.email && r.email.toLowerCase().includes(q)) ||
          (r.phone && r.phone.toLowerCase().includes(q)) ||
          (r.serviceTermLabel && r.serviceTermLabel.toLowerCase().includes(q)) ||
          (r.activationCode && r.activationStatus === "INVITED" && r.activationCode.toLowerCase().includes(q)) ||
          (r.notes && r.notes.toLowerCase().includes(q))
        );
      }
      return true;
    });
  }, [records, filter, searchQuery]);

  const counts = useMemo(() => {
    const total = records.length;
    const draft = records.filter((r) => r.activationStatus === "DRAFT").length;
    const invited = records.filter((r) => r.activationStatus === "INVITED").length;
    const redeemed = records.filter((r) => r.activationStatus === "REDEEMED").length;
    const active = records.filter((r) => r.accountStatus === "ACTIVE").length;
    const pending = records.filter((r) => r.accountStatus === "PENDING").length;
    const expired = records.filter((r) => r.activationStatus === "EXPIRED").length;
    const serviceActive = records.filter((r) => r.serviceStatus === "ACTIVE").length;
    const serviceExpired = records.filter((r) => r.serviceStatus === "EXPIRED").length;
    const revoked = records.filter((r) => r.accountStatus === "REVOKED" || r.activationStatus === "REVOKED").length;
    const suspended = records.filter((r) => r.accountStatus === "SUSPENDED").length;
    return { total, draft, invited, redeemed, active, pending, expired, serviceActive, serviceExpired, revoked, suspended };
  }, [records]);

  const handleCopyId = (code: string, label: string = "ID") => {
    try {
      navigator.clipboard.writeText(code);
      showFeedback(`Copied ${label} ${code} to clipboard.`);
    } catch {
      showFeedback(`Copied ${label} ${code} to clipboard.`);
    }
  };

  const handleReissue = async (record: AccessRecord) => {
    const ident = record.sxId || record.id;
    const res = await reissueBackendActivation(ident);
    if (res.success) {
      await refreshRecords();
      showFeedback(`New 24-hour activation code issued for ${record.displayName} (${res.activationCode}).`);
    } else {
      showFeedback(`⚠️ ${res.error || "BACKEND AUTHORITY UNAVAILABLE"}`);
    }
  };

  const handleRevokeActivationCode = async (code: string) => {
    const res = await revokeBackendActivation(code);
    if (res.success) {
      await refreshRecords();
      showFeedback(`Activation invitation credential for ${code} revoked.`);
    } else {
      showFeedback(`⚠️ ${res.error || "BACKEND AUTHORITY UNAVAILABLE"}`);
    }
  };

  const handleRevokeAccount = async (code: string) => {
    const res = await revokeBackendAccount(code);
    if (res.success) {
      await refreshRecords();
      showFeedback(`Account access for ${code} permanently revoked.`);
    } else {
      showFeedback(`⚠️ ${res.error || "BACKEND AUTHORITY UNAVAILABLE"}`);
    }
  };

  const handleSuspend = async (code: string) => {
    const res = await suspendBackendAccount(code);
    if (res.success) {
      await refreshRecords();
      showFeedback(`Account access for ${code} suspended. (Service clock continues running)`);
    } else {
      showFeedback(`⚠️ ${res.error || "BACKEND AUTHORITY UNAVAILABLE"}`);
    }
  };

  const handleRestore = async (code: string) => {
    const res = await restoreBackendAccount(code);
    if (res.success) {
      await refreshRecords();
      showFeedback(`Account access for ${code} restored.`);
    } else {
      showFeedback(`⚠️ ${res.error || "BACKEND AUTHORITY UNAVAILABLE"}`);
    }
  };

  const handleDeleteDraft = async (code: string) => {
    const res = await deleteBackendDraft(code);
    if (res.success) {
      await refreshRecords();
      if (selectedRecord && (selectedRecord.sxId === code || selectedRecord.accessId === code)) {
        setSelectedRecord(null);
      }
      showFeedback(`Draft access record ${code} deleted.`);
    } else {
      showFeedback(`⚠️ ${res.error || "BACKEND AUTHORITY UNAVAILABLE"}`);
    }
  };

  const handleResendInvite = (record: AccessRecord) => {
    showFeedback(`Simulated invite notification resent to ${maskEmail(record.email)}.`);
  };

  const handleExtend = async (record: AccessRecord) => {
    const customUnit = actionTermChoice === "CUSTOM" ? actionCustomUnit : undefined;
    const customValue = actionTermChoice === "CUSTOM" ? actionCustomValue : undefined;
    const res = await extendBackendService(record.sxId || record.id, {
      serviceTermType: actionTermChoice,
      customTermValue: customValue,
      customTermUnit: customUnit,
    });
    if (res.success) {
      await refreshRecords();
      showFeedback(`Service entitlement for ${record.displayName} extended.`);
    } else {
      showFeedback(`⚠️ ${res.error || "BACKEND AUTHORITY UNAVAILABLE"}`);
    }
  };

  const handleRenew = async (record: AccessRecord) => {
    const customUnit = actionTermChoice === "CUSTOM" ? actionCustomUnit : undefined;
    const customValue = actionTermChoice === "CUSTOM" ? actionCustomValue : undefined;
    const res = await renewBackendService(record.sxId || record.id, {
      serviceTermType: actionTermChoice,
      customTermValue: customValue,
      customTermUnit: customUnit,
    });
    if (res.success) {
      await refreshRecords();
      showFeedback(`Service entitlement for ${record.displayName} renewed.`);
    } else {
      showFeedback(`⚠️ ${res.error || "BACKEND AUTHORITY UNAVAILABLE"}`);
    }
  };

  const handleConvertToLifetime = async (record: AccessRecord) => {
    const res = await convertBackendLifetime(record.sxId || record.id);
    if (res.success) {
      await refreshRecords();
      showFeedback(`Converted ${record.displayName} to Lifetime service entitlement.`);
    } else {
      showFeedback(`⚠️ ${res.error || "BACKEND AUTHORITY UNAVAILABLE"}`);
    }
  };

  const handleSimulateActivation = (record: AccessRecord) => {
    const res = simulateFirstActivation(record.sxId || record.id);
    refreshRecords();
    showFeedback(res.message);
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim() || !newEmail.trim() || !newPhone.trim()) return;

    const res = await createBackendUserAccess({
      displayName: newName,
      email: newEmail,
      phone: newPhone,
      role: newRole,
      serviceTermType: serviceTermChoice,
      customTermValue: serviceTermChoice === "CUSTOM" ? customValue : undefined,
      customTermUnit: serviceTermChoice === "CUSTOM" ? customUnit : undefined,
      isDraft: false,
      notes: newNotes || "Issued via Owner Control Center",
    });

    if (res.success) {
      await refreshRecords();
      setCreateModalOpen(false);
      const codeMsg = res.activationCode ? ` & 24h Activation Code (${res.activationCode})` : "";
      showFeedback(`New Account ID ${res.data?.sx_id || generatedSxId}${codeMsg} issued for ${newName}. Service term configured.`);

      // Reset form
      setNewName("");
      setNewEmail("");
      setNewPhone("");
      setNewNotes("");
      setServiceTermChoice("3_MONTHS");
      setCustomValue(30);
      setCustomUnit("DAYS");
      setGeneratedSxId(generatePrototypeSentinelxId());
      setGeneratedActivationCode(generatePrototypeActivationCode());
    } else {
      showFeedback(`⚠️ ${res.error || "BACKEND AUTHORITY UNAVAILABLE"}`);
    }
  };

  return (
    <>
      <div className="v3-screen-head">
        <div>
          <h2 className="v3-screen-title">Access Registry</h2>
          <p className="v3-screen-sub">Authoritative OWNER access records · Manage permanent Account IDs, 24h one-time activation codes & Service Entitlements (OD-AUTH-19)</p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button
            type="button"
            className="v3-btn primary mini"
            onClick={() => {
              setGeneratedSxId(generatePrototypeSentinelxId());
              setGeneratedActivationCode(generatePrototypeActivationCode());
              setCreateModalOpen(true);
            }}
            id="open-create-access-modal-btn"
          >
            <Icon name="plus" size={13} />
            <span>+ CREATE USER ACCESS</span>
          </button>
          <TruthChip
            kind={registrySource === "BACKEND" ? "REAL" : (registrySource === "SAMPLE_FALLBACK" ? "SAMPLE" : "DISABLED")}
            title={registrySource === "BACKEND" ? "Authoritative User Access Registry (Backend SQLite)" : (registrySource === "SAMPLE_FALLBACK" ? "Interactive Access Registry in prototype state · Production server-side authorization not yet wired." : "Access Registry Authority Unavailable")}
          />
        </div>
      </div>

      {/* Summary KPI Strip */}
      <div className="v3-grid" style={{ marginBottom: 18 }}>
        <Panel label="Access &amp; Entitlement Summary" className="v3-sp12" id="access-summary-panel">
          <div style={{ display: "flex", gap: 28, flexWrap: "wrap", alignItems: "center" }}>
            <div>
              <div className="v3-stat-big">{counts.total}</div>
              <div className="v3-region-note">Total Records</div>
            </div>
            {counts.draft > 0 && (
              <div>
                <div className="v3-stat-big" style={{ color: "var(--v3-ink-dim)" }}>{counts.draft}</div>
                <div className="v3-region-note">Drafts Pending</div>
              </div>
            )}
            <div>
              <div className="v3-stat-big" style={{ color: "#38bdf8" }}>{counts.invited}</div>
              <div className="v3-region-note">Invited / Pending Code</div>
            </div>
            <div>
              <div className="v3-stat-big" style={{ color: "var(--sx-emerald)" }}>{counts.active}</div>
              <div className="v3-region-note">Active Accounts</div>
            </div>
            <div>
              <div className="v3-stat-big" style={{ color: "var(--v3-sky-text)" }}>{counts.serviceActive}</div>
              <div className="v3-region-note">Active Entitlements</div>
            </div>
            <div>
              <div className="v3-stat-big" style={{ color: "var(--sx-amber)" }}>{counts.expired}</div>
              <div className="v3-region-note">Expired Codes</div>
            </div>
            {counts.suspended > 0 && (
              <div>
                <div className="v3-stat-big" style={{ color: "var(--sx-rose)" }}>{counts.suspended}</div>
                <div className="v3-region-note">Suspended</div>
              </div>
            )}
          </div>
        </Panel>
      </div>

      {/* Authority Banner */}
      <div
        className="security-notice-box"
        id="access-registry-authority-banner"
        style={{
          marginBottom: 16,
          borderColor: "rgba(56, 189, 248, 0.3)",
          background: "rgba(56, 189, 248, 0.05)",
        }}
      >
        <span className="sec-notice-icon" style={{ fontSize: 18 }}>🛡️</span>
        <div>
          <div style={{ fontWeight: 600, color: "var(--v3-sky-text)", fontSize: 12, marginBottom: 2 }}>
            THREE INDEPENDENT STATE AXES (OD-AUTH-02 &amp; OD-AUTH-19)
          </div>
          <span style={{ fontSize: 11.5, color: "var(--v3-ink-2)" }}>
            <strong>1. Activation Credential State</strong> (24h one-time code),{" "}
            <strong>2. Account Access State</strong> (administrative hold), and{" "}
            <strong>3. Service Entitlement State</strong> (term duration).{" "}
            Service duration begins on <strong>successful first activation</strong>, not invitation creation. Account suspension does <strong>not</strong> pause the service clock.
          </span>
        </div>
      </div>

      {feedback && (
        <div
          className="v3-feedback-banner ok"
          role="status"
          id="access-registry-feedback-banner"
          style={{ marginBottom: 14 }}
        >
          ✓ {feedback}
        </div>
      )}

      {/* Main Table Panel */}
      <Panel
        label="Owner Access &amp; Entitlement Registry"
        meta={`${filtered.length} of ${records.length} access records`}
        className="v3-sp12"
      >
        {/* Filter Controls Bar */}
        <div
          style={{
            display: "flex",
            gap: 10,
            marginBottom: 14,
            flexWrap: "wrap",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
                              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button
              type="button"
              className={`v3-btn mini ${filter === "ALL" ? "active primary" : "ghost"}`}
              onClick={() => setFilter("ALL")}
              id="filter-pill-all"
            >
              All ({counts.total})
            </button>
            <button
              type="button"
              className={`v3-btn mini ${filter === "INVITED" ? "active primary" : "ghost"}`}
              onClick={() => setFilter("INVITED")}
              id="filter-pill-invited"
            >
              Invited ({counts.invited})
            </button>
            <button
              type="button"
              className={`v3-btn mini ${filter === "REDEEMED" ? "active primary" : "ghost"}`}
              onClick={() => setFilter("REDEEMED")}
              id="filter-pill-redeemed"
            >
              Redeemed ({counts.serviceActive})
            </button>
            <button
              type="button"
              className={`v3-btn mini ${filter === "ACTIVE" ? "active primary" : "ghost"}`}
              onClick={() => setFilter("ACTIVE")}
              id="filter-pill-active"
            >
              Active ({counts.active})
            </button>
            <button
              type="button"
              className={`v3-btn mini ${filter === "PENDING" ? "active primary" : "ghost"}`}
              onClick={() => setFilter("PENDING")}
              id="filter-pill-pending"
            >
              Pending ({records.filter(r => r.accountStatus === "PENDING").length})
            </button>
            <button
              type="button"
              className={`v3-btn mini ${filter === "EXPIRED" ? "active primary" : "ghost"}`}
              onClick={() => setFilter("EXPIRED")}
              id="filter-pill-expired"
            >
              Expired ({counts.expired})
            </button>
            <button
              type="button"
              className={`v3-btn mini ${filter === "SUSPENDED" ? "active primary" : "ghost"}`}
              onClick={() => setFilter("SUSPENDED")}
              id="filter-pill-suspended"
            >
              Suspended ({counts.suspended})
            </button>
            <button
              type="button"
              className={`v3-btn mini ${filter === "REVOKED" ? "active primary" : "ghost"}`}
              onClick={() => setFilter("REVOKED")}
              id="filter-pill-revoked"
            >
              Revoked ({counts.revoked})
            </button>
            <button
              type="button"
              className={`v3-btn mini ${filter === "DRAFT" ? "active primary" : "ghost"}`}
              onClick={() => setFilter("DRAFT")}
              id="filter-pill-draft"
            >
              Draft ({counts.draft})
            </button>
          </div>

          <div style={{ minWidth: 240, maxWidth: 320, flex: 1, display: "flex", gap: 6, alignItems: "center" }}>
            <input
              type="search"
              className="v3-input mini"
              placeholder="Search by ID, name, email, term..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              id="access-registry-search-input"
            />
            {searchQuery && (
              <button
                type="button"
                className="v3-btn ghost mini"
                onClick={() => setSearchQuery("")}
                id="clear-search-btn"
              >
                Clear
              </button>
            )}
          </div>
        </div>

        {/* Access Records Table */}
        <div className="v3-table-wrap">
          <table className="v3-table" id="access-registry-table">
                        <thead>
              <tr>
                <th style={{ whiteSpace: "nowrap" }}>ACCOUNT ID</th>
                <th style={{ whiteSpace: "nowrap" }}>USER</th>
                <th style={{ whiteSpace: "nowrap" }}>BOUND EMAIL</th>
                <th style={{ whiteSpace: "nowrap" }}>ACTIVATION CODE</th>
                <th style={{ whiteSpace: "nowrap" }}>ACTIVATION STATUS</th>
                <th style={{ whiteSpace: "nowrap" }}>ACCOUNT STATUS</th>
                <th style={{ whiteSpace: "nowrap" }}>SERVICE ENTITLEMENT</th>
                <th style={{ whiteSpace: "nowrap" }}>SERVICE EXPIRY</th>
                <th style={{ textAlign: "right", whiteSpace: "nowrap" }}>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={9} style={{ textAlign: "center", padding: "28px", color: "var(--v3-ink-dim)" }}>
                    {records.length === 0 ? "No users yet" : "No access records match filter."}
                  </td>
                </tr>
              ) : (
                filtered.map((r) => {
                  const displaySxId = r.sxId || r.accessId || r.id;
                  const canReissue =
                    (r.activationStatus === "EXPIRED" || r.activationStatus === "REVOKED") &&
                    r.accountStatus !== "REVOKED" &&
                    r.accountStatus !== "SUSPENDED";

                                    return (
                    <tr key={r.id} className="v3-table-row" id={`access-row-${r.id}`}>
                      <td>
                        <button
                          type="button"
                          className="v3-table-code-btn"
                          onClick={() => handleCopyId(displaySxId, "Account ID")}
                          title="Click to copy permanent Account ID"
                          id={`copy-sxid-btn-${r.id}`}
                        >
                          <span className="v3-mono font-bold" style={{ whiteSpace: "nowrap" }}>{displaySxId}</span>
                          <Icon name="copy" size={12} className="v3-dim" />
                        </button>
                      </td>
                      <td>
                        <div className="v3-cell-main font-semibold" style={{ whiteSpace: "nowrap" }}>{r.displayName}</div>
                        <div className="v3-cell-sub" style={{ whiteSpace: "nowrap" }}>{r.role}</div>
                      </td>
                      <td>
                        <span className="v3-mono" style={{ whiteSpace: "nowrap" }}>{r.emailMasked || "NOT PROVIDED"}</span>
                      </td>
                      {/* Col 4: Activation Code */}
                      <td>
                        {r.activationCode ? (
                          <button
                            type="button"
                            className="v3-table-code-btn"
                            onClick={() => handleCopyId(r.activationCode!, "Activation Code")}
                            title="Click to copy 24h Activation Code"
                            id={`copy-code-btn-${r.id}`}
                          >
                            <span className="v3-mono text-xs font-semibold" style={{ color: "#38bdf8", whiteSpace: "nowrap" }}>
                              {r.activationCode}
                            </span>
                            <Icon name="copy" size={11} className="v3-dim" />
                          </button>
                        ) : (
                          <span className="v3-mono text-xs v3-dim" style={{ whiteSpace: "nowrap" }}>—</span>
                        )}
                      </td>
                      {/* Col 5: Activation Status */}
                      <td>
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                          <span className={`v3-status-badge ${r.activationStatus.toLowerCase()}`} style={{ whiteSpace: "nowrap" }} id={`badge-activation-${r.id}`}>
                            <Dot tone={ACTIVATION_STATUS_TONE[r.activationStatus]} />
                            <span>{r.activationStatus}</span>
                          </span>
                          <span className="v3-mono v3-dim text-xs" style={{ fontSize: 9.5 }}>
                            {r.expiresAt ? `Exp: ${r.expiresAt.split(" ")[0]}` : "—"}
                          </span>
                        </div>
                      </td>
                      {/* Col 6: Account Status */}
                      <td>
                        <span className={`v3-status-badge ${r.accountStatus.toLowerCase()}`} style={{ whiteSpace: "nowrap" }} id={`badge-account-${r.id}`}>
                          <Dot tone={ACCOUNT_STATUS_TONE[r.accountStatus]} />
                          <span>{r.accountStatus}</span>
                        </span>
                      </td>
                      {/* Col 7: Service Entitlement */}
                      <td>
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                          <span className={`v3-status-badge ${r.serviceStatus.toLowerCase()}`} style={{ whiteSpace: "nowrap" }} id={`badge-service-${r.id}`}>
                            <Dot tone={SERVICE_STATUS_TONE[r.serviceStatus]} />
                            <span>{r.serviceStatus} ({r.serviceTermLabel})</span>
                          </span>
                        </div>
                      </td>
                      {/* Col 8: Service Expiry */}
                      <td>
                        <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                          <span className="v3-mono text-xs" style={{ whiteSpace: "nowrap" }}>
                            {r.serviceTermType === "LIFETIME"
                              ? "Never / Lifetime"
                              : r.serviceExpiresAt
                              ? r.serviceExpiresAt.split(" ")[0]
                              : "Starts on activation"}
                          </span>
                        </div>
                      </td>
                      {/* Col 9: Actions */}
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        <div style={{ display: "inline-flex", gap: 5, justifyContent: "flex-end", flexWrap: "nowrap" }}>
                          <button
                            type="button"
                            className="v3-btn ghost mini"
                            onClick={() => setSelectedRecord(r)}
                            id={`details-access-btn-${r.id}`}
                            title="View access audit history and details"
                          >
                            Details
                          </button>
                          {r.activationStatus === "INVITED" && (
                            <>
                              <button
                                type="button"
                                className="v3-btn ghost mini"
                                onClick={() => handleResendInvite(r)}
                                id={`resend-access-btn-${r.id}`}
                                title="Resend invitation notification"
                              >
                                Resend
                              </button>
                              <button
                                type="button"
                                className="v3-btn danger-ghost mini"
                                onClick={() => handleRevokeActivationCode(displaySxId)}
                                id={`revoke-code-btn-${r.id}`}
                                title="Revoke one-time activation code invitation only"
                              >
                                Revoke Code
                              </button>
                            </>
                          )}
                          {canReissue && (
                            <button
                              type="button"
                              className="v3-btn ghost mini"
                              onClick={() => handleReissue(r)}
                              id={`reissue-access-btn-${r.id}`}
                              title="Reissue a new 24h activation code"
                            >
                              Reissue
                            </button>
                          )}
                          {r.accountStatus === "ACTIVE" && (
                            <button
                              type="button"
                              className="v3-btn danger-ghost mini"
                              onClick={() => handleSuspend(displaySxId)}
                              id={`suspend-access-btn-${r.id}`}
                              title="Suspend user account"
                            >
                              Suspend
                            </button>
                          )}
                          {r.accountStatus === "SUSPENDED" && (
                            <button
                              type="button"
                              className="v3-btn ghost mini"
                              onClick={() => handleRestore(displaySxId)}
                              id={`restore-access-btn-${r.id}`}
                              title="Restore suspended user account"
                            >
                              Restore
                            </button>
                          )}
                          {r.accountStatus !== "REVOKED" && r.activationStatus !== "DRAFT" && (
                            <button
                              type="button"
                              className="v3-btn danger-ghost mini"
                              onClick={() => handleRevokeAccount(displaySxId)}
                              id={`revoke-account-btn-${r.id}`}
                              title="Permanently revoke user account access"
                            >
                              Revoke Account
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* ── Modal / Drawer: CREATE USER ACCESS RECORD ── */}
      <Drawer
        open={createModalOpen}
        title="Issue User Access & Activation Code"
        sub="OD-AUTH-01 & OD-AUTH-19 · Provision permanent Account ID, 24h activation code & service entitlement term"
        onClose={() => setCreateModalOpen(false)}
      >
        <form onSubmit={handleCreateSubmit} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Identity preview */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label className="v3-field-label" htmlFor="new-sentinelx-id">Permanent Account ID</label>
              <input
                type="text"
                id="new-sentinelx-id"
                className="v3-input v3-mono font-bold"
                value={generatedSxId}
                readOnly
                style={{ background: "var(--v3-surface-2)", color: "var(--v3-ink)" }}
              />
            </div>
            <div>
              <label className="v3-field-label" htmlFor="new-activation-code">One-Time Activation Code (24h Window)</label>
              <input
                type="text"
                id="new-activation-code"
                className="v3-input v3-mono font-bold"
                value={generatedActivationCode}
                readOnly
                style={{ background: "rgba(56, 189, 248, 0.1)", color: "#38bdf8" }}
              />
            </div>
          </div>

          <div>
            <label className="v3-field-label" htmlFor="new-display-name">
              Display Name *
            </label>
            <input
              id="new-display-name"
              type="text"
              className="v3-input"
              placeholder="e.g. Vikram Malhotra"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              required
            />
          </div>

          <div>
            <label className="v3-field-label" htmlFor="new-email">
              Bound Email Address *
            </label>
            <input
              id="new-email"
              type="email"
              className="v3-input"
              placeholder="e.g. vikram.m@quantfund.internal"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              required
            />
            <span className="v3-field-hint">Activation code can only be redeemed if user enters this exact email</span>
          </div>

          <div>
            <label className="v3-field-label" htmlFor="new-phone">
              Bound Phone Number *
            </label>
            <input
              id="new-phone"
              type="tel"
              className="v3-input"
              placeholder="e.g. +91 99112 33445"
              value={newPhone}
              onChange={(e) => setNewPhone(e.target.value)}
              required
            />
          </div>

          {/* ── REQUIRED SERVICE ACCESS TERM SELECTOR (OD-AUTH-19) ── */}
          <div
            id="service-term-selector-group"
            style={{
              padding: "12px 14px",
              background: "var(--v3-surface-2)",
              borderRadius: 8,
              border: "1px solid rgba(56, 189, 248, 0.2)",
            }}
          >
            <label className="v3-field-label" style={{ color: "var(--v3-sky-text)", fontWeight: 650, marginBottom: 6 }}>
              SERVICE ACCESS TERM (OD-AUTH-19) *
            </label>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6, marginBottom: 10 }}>
              {(["1_MONTH", "3_MONTHS", "6_MONTHS", "12_MONTHS", "LIFETIME", "CUSTOM"] as ServiceTermType[]).map((term) => {
                const isSelected = serviceTermChoice === term;
                const label =
                  term === "1_MONTH"
                    ? "1 Month"
                    : term === "3_MONTHS"
                    ? "3 Months"
                    : term === "6_MONTHS"
                    ? "6 Months"
                    : term === "12_MONTHS"
                    ? "12 Months"
                    : term === "LIFETIME"
                    ? "Lifetime"
                    : "Custom";

                return (
                  <button
                    key={term}
                    type="button"
                    className={`v3-btn mini ${isSelected ? "primary" : "ghost"}`}
                    onClick={() => setServiceTermChoice(term)}
                    id={`btn-term-${term.toLowerCase()}`}
                    style={{ fontSize: 11 }}
                  >
                    {label}
                  </button>
                );
              })}
            </div>

            {/* Custom Term Inputs */}
            {serviceTermChoice === "CUSTOM" && (
              <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 8 }} id="custom-term-inputs">
                <div style={{ flex: 1 }}>
                  <label className="v3-field-label" htmlFor="custom-term-val">Duration Number</label>
                  <input
                    id="custom-term-val"
                    type="number"
                    min={1}
                    max={3650}
                    className="v3-input mini"
                    value={customValue}
                    onChange={(e) => setCustomValue(parseInt(e.target.value, 10) || 1)}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <label className="v3-field-label" htmlFor="custom-term-unit">Duration Unit</label>
                  <select
                    id="custom-term-unit"
                    className="v3-select mini"
                    value={customUnit}
                    onChange={(e) => setCustomUnit(e.target.value as "DAYS" | "MONTHS")}
                  >
                    <option value="DAYS">Days (Exact 24h periods)</option>
                    <option value="MONTHS">Months (Calendar Month arithmetic)</option>
                  </select>
                </div>
              </div>
            )}

            <div style={{ fontSize: 11, color: "var(--v3-ink-3)", lineHeight: 1.4 }}>
              ⏱️ <strong>Start Rule:</strong> Service duration begins on <strong>successful first activation</strong> (Initial service status: <code>NOT_STARTED</code>). Invitation 24-hour expiration applies only to redemption.
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label className="v3-field-label" htmlFor="new-role">
                Assigned Role / Tier
              </label>
              <select
                id="new-role"
                className="v3-select"
                value={newRole}
                onChange={(e) => setNewRole(e.target.value)}
              >
                <option value="Quant Trader">Quant Trader</option>
                <option value="Lead Strategist">Lead Strategist</option>
                <option value="Portfolio Manager">Portfolio Manager</option>
                <option value="Starter">Starter</option>
              </select>
            </div>
            <div>
              <label className="v3-field-label">Activation Code Window</label>
              <div style={{ padding: "8px 10px", background: "var(--v3-surface-2)", borderRadius: 6, fontSize: 11.5, color: "var(--v3-ink-2)" }}>
                24 hours (One-time invitation)
              </div>
            </div>
          </div>

          <div>
            <label className="v3-field-label" htmlFor="new-notes">
              Administrative Notes (Optional)
            </label>
            <textarea
              id="new-notes"
              className="v3-textarea"
              rows={2}
              placeholder="e.g. Onboarding proprietary derivatives desk member"
              value={newNotes}
              onChange={(e) => setNewNotes(e.target.value)}
            />
          </div>

          <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
            <button
              type="submit"
              className="v3-btn primary"
              style={{ flex: 1 }}
              id="submit-create-access-btn"
            >
              <span>ISSUE USER ACCESS &amp; ACTIVATION CODE</span>
            </button>
            <button
              type="button"
              className="v3-btn ghost"
              onClick={() => setCreateModalOpen(false)}
            >
              Cancel
            </button>
          </div>
        </form>
      </Drawer>

      {/* ── Modal / Drawer: ACCESS RECORD DETAILS & AUDIT ── */}
      <Drawer
        open={selectedRecord !== null}
        title={selectedRecord?.sxId || selectedRecord?.accessId || ""}
        sub={
          selectedRecord
            ? `Access Record · ${selectedRecord.displayName} (Account: ${selectedRecord.accountStatus} · Service: ${selectedRecord.serviceStatus})`
            : undefined
        }
        onClose={() => setSelectedRecord(null)}
      >
        {selectedRecord && (
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            {/* Account Profile Group */}
                        <dl style={{ margin: 0 }}>
              <KV k="Account ID" v={<span className="v3-mono font-bold" id="drawer-sxid-val">{selectedRecord.sxId || selectedRecord.accessId}</span>} />
              <KV k="Subject Display Name" v={selectedRecord.displayName} />
              <KV k="Bound Email" v={<span className="v3-mono">{selectedRecord.email || "NOT PROVIDED"}</span>} />
              <KV k="Bound Phone" v={<span className="v3-mono">{selectedRecord.phone || "NOT PROVIDED"}</span>} />
              <KV k="Role / Tier" v={selectedRecord.role} />
              <KV
                k="Account Status"
                v={
                  <span className={`v3-status-badge ${selectedRecord.accountStatus.toLowerCase()}`} id="drawer-account-status-val">
                    <Dot tone={ACCOUNT_STATUS_TONE[selectedRecord.accountStatus]} /> {selectedRecord.accountStatus}
                  </span>
                }
              />
              <KV
                k="Activation Status"
                v={
                  <span className={`v3-status-badge ${selectedRecord.activationStatus.toLowerCase()}`} id="drawer-activation-status-val">
                    <Dot tone={ACTIVATION_STATUS_TONE[selectedRecord.activationStatus]} /> {selectedRecord.activationStatus}
                  </span>
                }
              />
              <KV
                k="Activation Code (24h Window)"
                v={
                  selectedRecord.activationCode ? (
                    <span className="v3-mono font-bold" style={{ color: "#38bdf8" }} id="drawer-activation-code-val">
                      {selectedRecord.activationCode}
                    </span>
                  ) : (
                    <span className="v3-dim" id="drawer-activation-code-val">No Active Code</span>
                  )
                }
              />
              <KV k="Created By" v={selectedRecord.createdBy || "UNAVAILABLE"} />
              <KV k="Created Date" v={selectedRecord.createdAt} />
              <KV k="Activation Code Expiration" v={selectedRecord.expiresAt ? `${selectedRecord.expiresAt} (24h invitation window)` : "No Code Issued"} />
              <KV k="Redeemed Date" v={selectedRecord.redeemedAt || "Not Redeemed Yet"} />
            </dl>

            {/* ── SERVICE ACCESS ENTITLEMENT PANEL (OD-AUTH-19 to OD-AUTH-24) ── */}
            <Panel label="Service Access Entitlement (OD-AUTH-19 / OD-AUTH-24)" id="drawer-service-entitlement-panel">
              <dl style={{ margin: 0 }}>
                <KV
                  k="Service Entitlement Status"
                  v={
                    <span className={`v3-status-badge ${selectedRecord.serviceStatus.toLowerCase()}`} id="drawer-service-status-val">
                      <Dot tone={SERVICE_STATUS_TONE[selectedRecord.serviceStatus]} /> {selectedRecord.serviceStatus}
                    </span>
                  }
                />
                <KV k="Configured Service Term" v={<span className="v3-mono font-semibold" id="drawer-service-term-val">{selectedRecord.serviceTermLabel}</span>} />
                <KV
                  k="Service Started At"
                  v={
                    selectedRecord.serviceStartedAt
                      ? <span className="v3-mono font-semibold" id="drawer-service-started-val">{selectedRecord.serviceStartedAt}</span>
                      : <span className="v3-dim" id="drawer-service-started-val">Pending first activation (Starts on activation)</span>
                  }
                />
                <KV
                  k="Service Expires At"
                  v={
                    selectedRecord.serviceTermType === "LIFETIME"
                      ? <span className="v3-mono text-emerald-400 font-bold" id="drawer-service-expires-val">Never / Lifetime</span>
                      : selectedRecord.serviceExpiresAt
                      ? <span className="v3-mono font-bold text-sky-400" id="drawer-service-expires-val">{selectedRecord.serviceExpiresAt}</span>
                      : <span className="v3-dim" id="drawer-service-expires-val">Not calculated yet (Starts on activation)</span>
                  }
                />
              </dl>

              {/* Service Management Action Controls */}
              <div style={{ marginTop: 12, padding: "10px 12px", background: "var(--v3-surface-2)", borderRadius: 6 }} id="service-actions-deck">
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--v3-sky-text)", marginBottom: 8 }}>
                  OWNER SERVICE DURATION ACTIONS (INTERACTIVE PROTOTYPE)
                </div>

                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
                  <span className="v3-dim text-xs">Term:</span>
                  <select
                    className="v3-select mini"
                    value={actionTermChoice}
                    onChange={(e) => setActionTermChoice(e.target.value as ServiceTermType)}
                    id="drawer-action-term-select"
                    style={{ minWidth: 120 }}
                  >
                    <option value="1_MONTH">1 Month</option>
                    <option value="3_MONTHS">3 Months</option>
                    <option value="6_MONTHS">6 Months</option>
                    <option value="12_MONTHS">12 Months</option>
                    <option value="LIFETIME">Lifetime</option>
                    <option value="CUSTOM">Custom</option>
                  </select>

                  {actionTermChoice === "CUSTOM" && (
                    <div style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
                      <input
                        type="number"
                        min={1}
                        className="v3-input mini"
                        style={{ width: 60 }}
                        value={actionCustomValue}
                        onChange={(e) => setActionCustomValue(parseInt(e.target.value, 10) || 1)}
                        id="drawer-custom-term-val"
                      />
                      <select
                        className="v3-select mini"
                        value={actionCustomUnit}
                        onChange={(e) => setActionCustomUnit(e.target.value as "DAYS" | "MONTHS")}
                        id="drawer-custom-term-unit"
                      >
                        <option value="DAYS">Days</option>
                        <option value="MONTHS">Months</option>
                      </select>
                    </div>
                  )}
                </div>

                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  {selectedRecord.serviceStatus === "ACTIVE" && (
                    <button
                      type="button"
                      className="v3-btn primary mini"
                      onClick={() => handleExtend(selectedRecord)}
                      id="drawer-extend-service-btn"
                      title="Extend service from current expiration date"
                    >
                      Extend Term
                    </button>
                  )}
                  {selectedRecord.serviceStatus === "EXPIRED" && (
                    <button
                      type="button"
                      className="v3-btn primary mini"
                      onClick={() => handleRenew(selectedRecord)}
                      id="drawer-renew-service-btn"
                      title="Renew expired service from today"
                    >
                      Renew Service
                    </button>
                  )}
                  {selectedRecord.serviceTermType !== "LIFETIME" && (
                    <button
                      type="button"
                      className="v3-btn ghost mini"
                      onClick={() => handleConvertToLifetime(selectedRecord)}
                      id="drawer-convert-lifetime-btn"
                      title="Convert entitlement to Lifetime"
                    >
                      Grant Lifetime
                    </button>
                  )}
                  {selectedRecord.activationStatus === "INVITED" && (
                    <button
                      type="button"
                      className="v3-btn ghost mini"
                      onClick={() => handleSimulateActivation(selectedRecord)}
                      id="drawer-simulate-activation-btn"
                      title="Simulate user completing WebAuthn passkey activation"
                    >
                      Simulate First Activation
                    </button>
                  )}
                </div>
              </div>
            </Panel>

            <div
              id="drawer-governance-notice" style={{ padding: "10px 14px", background: "var(--v3-surface-2)", borderRadius: 8, fontSize: 11, color: "var(--v3-ink-2)", lineHeight: 1.45 }}>🔒 <strong>Governance Notice:</strong> Activation Credential State is strictly decoupled from Account State (OD-AUTH-23). Permanent Account ID remains immutable across renewals. Service duration begins on successful first activation.</div>

            {/* Activation Issuance History */}
            <div id="activation-history-panel">
              <div className="v3-region-title" style={{ fontSize: 13, marginBottom: 8 }} id="activation-history-heading">
                Activation Issuance History ({selectedRecord.activationHistory?.length || 0})
              </div>
              {(!selectedRecord.activationHistory || selectedRecord.activationHistory.length === 0) ? (
                <div style={{ fontSize: 11.5, color: "var(--v3-ink-3)", padding: "8px 0" }}>
                  No activation issuances recorded for draft.
                </div>
              ) : (
                <div className="v3-rows" id="activation-history-list">
                  {selectedRecord.activationHistory.map((iss, i) => (
                    <div className="v3-row" key={iss.id || i} id={`issuance-row-${iss.id || i}`}>
                      <div className="v3-row-main">
                        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                          <span className="v3-mono font-semibold" style={{ fontSize: 12 }}>
                            {iss.code || "UNISSUED DRAFT"}
                          </span>
                          <span className={`v3-status-badge ${iss.status.toLowerCase()}`} style={{ fontSize: 10 }}>
                            <Dot tone={ACTIVATION_STATUS_TONE[iss.status]} /> {iss.status}
                          </span>
                        </div>
                        <div className="v3-row-sub" style={{ fontSize: 10.5 }}>
                          Issued: {iss.issuedAt} {iss.expiresAt ? `· Expiry: ${iss.expiresAt}` : ""}
                          {iss.redeemedAt ? ` · Redeemed: ${iss.redeemedAt}` : ""}
                          {iss.revokedAt ? ` · Revoked: ${iss.revokedAt}` : ""}
                        </div>
                      </div>
                      <span className="v3-mono v3-dim" style={{ fontSize: 10 }}>{iss.actor || "OWNER-001"}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Audit Trail & Lifecycle Events */}
            <div>
              <div className="v3-region-title" style={{ fontSize: 13, marginBottom: 8 }}>
                Audit Trail &amp; Lifecycle Events
              </div>
              <div className="v3-rows">
                {selectedRecord.history.map((h, i) => (
                  <div className="v3-row" key={i}>
                    <div className="v3-row-main">
                      <div className="v3-row-title">{h.action}</div>
                      <div className="v3-row-sub">{h.actor}</div>
                    </div>
                    <span className="v3-mono v3-dim" style={{ fontSize: 10.5 }}>{h.time}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Drawer Actions */}
            <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
              <button
                type="button"
                className="v3-btn ghost mini"
                onClick={() => handleCopyId(selectedRecord.sxId || selectedRecord.accessId || selectedRecord.id, "Account ID")}
                id="drawer-copy-sxid-btn"
              >
                <Icon name="copy" size={13} /> Copy Account ID
              </button>
              {selectedRecord.activationCode && selectedRecord.activationStatus === "INVITED" && (
                <button
                  type="button"
                  className="v3-btn ghost mini"
                  onClick={() => handleCopyId(selectedRecord.activationCode!, "Activation Code")}
                  id="drawer-copy-code-btn"
                >
                  <Icon name="copy" size={13} /> Copy Activation Code
                </button>
              )}
              {selectedRecord.activationStatus === "INVITED" && (
                <>
                  <button
                    type="button"
                    className="v3-btn ghost mini"
                    onClick={() => handleResendInvite(selectedRecord)}
                    id="drawer-resend-access-btn"
                  >
                    Resend Invite
                  </button>
                  <button
                    type="button"
                    className="v3-btn danger-ghost mini"
                    onClick={() => handleRevokeActivationCode(selectedRecord.sxId || selectedRecord.accessId || selectedRecord.id)}
                    id="drawer-revoke-code-btn"
                  >
                    Revoke Code
                  </button>
                </>
              )}
              {(selectedRecord.activationStatus === "EXPIRED" || selectedRecord.activationStatus === "REVOKED") &&
                selectedRecord.accountStatus !== "REVOKED" &&
                selectedRecord.accountStatus !== "SUSPENDED" && (
                <button
                  type="button"
                  className="v3-btn ghost mini"
                  onClick={() => handleReissue(selectedRecord)}
                  id="drawer-reissue-access-btn"
                >
                  Reissue Activation
                </button>
              )}
              {selectedRecord.activationStatus === "DRAFT" && (
                <button
                  type="button"
                  className="v3-btn danger-ghost mini"
                  onClick={() => handleDeleteDraft(selectedRecord.sxId || selectedRecord.accessId || selectedRecord.id)}
                  id="drawer-delete-draft-btn"
                >
                  Delete Draft
                </button>
              )}
              {selectedRecord.accountStatus === "ACTIVE" && (
                <button
                  type="button"
                  className="v3-btn danger-ghost mini"
                  onClick={() => handleSuspend(selectedRecord.sxId || selectedRecord.accessId || selectedRecord.id)}
                  id="drawer-suspend-access-btn"
                >
                  Suspend Account
                </button>
              )}
              {selectedRecord.accountStatus === "SUSPENDED" && (
                <button
                  type="button"
                  className="v3-btn ghost mini"
                  onClick={() => handleRestore(selectedRecord.sxId || selectedRecord.accessId || selectedRecord.id)}
                  id="drawer-restore-access-btn"
                >
                  Restore Account
                </button>
              )}
              {selectedRecord.accountStatus !== "REVOKED" && selectedRecord.activationStatus !== "DRAFT" && (
                <button
                  type="button"
                  className="v3-btn danger-ghost mini"
                  onClick={() => handleRevokeAccount(selectedRecord.sxId || selectedRecord.accessId || selectedRecord.id)}
                  id="drawer-revoke-account-btn"
                >
                  Revoke Account
                </button>
              )}
            </div>
          </div>
        )}
      </Drawer>
      </>
  );
};
