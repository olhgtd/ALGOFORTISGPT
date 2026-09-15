import React, { useState, useMemo, useEffect } from "react";
import { Icon } from "../../shared/icons/V3Icons";
import { Panel, Drawer, KV, TruthChip, Dot } from "../../shared/utilities/V3Chrome";
import {
  getStoredOwnerSessions,
  revokeOwnerSessionSimulated,
  revokeAllOwnerSessionsSimulated,
  getStoredOwnerDevices,
  revokeOwnerDeviceSimulated,
  revokeAllUserDevicesSimulated,
  getStoredOwnerSettings,
  updateOwnerSetting,
  getStoredAccessRecords,
  getStoredOwnerUsers,
  getStoredOwnerAuditEvents,
  INITIAL_RATE_LIMIT_POLICIES,
  INITIAL_SYSTEM_SUBSYSTEMS,
  type OwnerSessionRow,
  type OwnerDeviceRow,
  type OwnerRecoveryPosture,
  type RateLimitPolicyItem,
  type SystemHealthSubsystem,
  type OwnerSettingsState,
} from "../../sampleData";
import {
  queryPersistenceHealth,
  queryOwnerSessions,
  revokeBackendSession,
  revokeAllBackendUserSessions,
  queryOwnerDevices,
  revokeBackendDevice,
  revokeAllBackendUserDevices,
  querySecurityStatus,
  proposeServerSetting,
  confirmServerSetting,
  queryServerSettings,
  type IntegrationResult,
  type IntegrationSource,
  type BackendPersistenceHealth,
  type OwnerSecurityStatusPayload,
} from "../../shared/services/integrationClient";

export interface AdminSecuritySystemSettingsScreenProps {
  initialTab?: "security" | "system" | "settings";
  go?: (screenId: string) => void;
}

const TONE_MAP: Record<string, "ok" | "warn" | "neg" | "dim" | "live"> = {
  OPERATIONAL: "ok",
  ACTIVE: "ok",
  HEALTHY: "ok",
  TRUSTED_REGISTERED: "ok",
  FAIL_CLOSED: "ok",
  DEGRADED: "warn",
  LOW: "warn",
  WARNING: "warn",
  STRONG_WARNING: "warn",
  NOT_CONNECTED: "warn",
  CRITICAL: "neg",
  PERSISTENT_CRITICAL: "neg",
  REVOKED: "neg",
  EXPIRED: "dim",
  PROTOTYPE_PROJECTION: "dim",
  NONE: "neg",
};

const SERVER_SETTING_DEFS: { key: string; label: string; hint: string }[] = [
  { key: "stale_threshold_seconds", label: "Stale Threshold (seconds)", hint: "Market-data staleness boundary" },
  { key: "retention_policy_days", label: "Retention Policy (days)", hint: "Evidence retention window" },
];

/** F-18: server-authoritative settings are PROPOSEd then CONFIRMed; success only on re-read VERIFIED. */
const ServerAuthoritativeSettingsPanel: React.FC = () => {
  const [effective, setEffective] = useState<Record<string, unknown> | null>(null);
  const [source, setSource] = useState<"BACKEND" | "UNAVAILABLE">("UNAVAILABLE");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const refresh = async () => {
    const res = await queryServerSettings();
    if (res.success && res.data) {
      setEffective(res.data);
      setSource("BACKEND");
    } else {
      setEffective(null);
      setSource("UNAVAILABLE");
    }
  };

  useEffect(() => { refresh(); }, []);

  const propose = async (key: string) => {
    const raw = (drafts[key] || "").trim();
    if (!raw) { setMessage(`Enter a value for ${key} first.`); return; }
    const value = Number(raw);
    if (!Number.isFinite(value)) { setMessage(`Value for ${key} must be numeric.`); return; }
    const res = await proposeServerSetting(key, value);
    if (res.success && res.data?.proposal_id) {
      setPendingId(res.data.proposal_id);
      setPendingKey(key);
      setMessage(`Proposal staged for ${key} (no effective change yet). Confirm to apply.`);
    } else {
      setMessage(`Proposal rejected by authority (no state mutated): ${res.error}`);
    }
  };

  const confirm = async () => {
    if (!pendingId) return;
    const res = await confirmServerSetting(pendingId);
    if (res.success) {
      setMessage(`${res.data?.key} applied and re-read VERIFIED (${String(res.data?.effective_value)}).`);
      setPendingId(null);
      setPendingKey(null);
      await refresh();
    } else {
      setMessage(`Confirmation failed (no success claimed): ${res.error}`);
    }
  };

  return (
    <Panel label="Server-Authoritative Settings (Backend Governed)" className="v3-sp6">
      <div style={{ padding: "8px 10px", background: "var(--v3-surface-2)", borderRadius: 6, marginBottom: 12, fontSize: 12, lineHeight: 1.4 }}>
        <strong>PROPOSE → CONFIRM → APPLY → VERIFY:</strong> proposals persist without mutating effective settings.
        Owner confirmation applies atomically and success is reported only after re-read verification.
        <span style={{ marginLeft: 8 }}><TruthChip kind={source === "BACKEND" ? "REAL" : "DISABLED"} title="Server settings provenance" /></span>
      </div>
      {source !== "BACKEND" ? (
        <div className="v3-cell-sub text-xs">Backend settings authority unavailable — no server setting can be changed from this view.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {SERVER_SETTING_DEFS.map((def) => (
            <div key={def.key} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, padding: "8px 10px", border: "1px solid var(--v3-line)", borderRadius: 6 }}>
              <div style={{ fontSize: 12 }}>
                <div><strong>{def.label}</strong> <span className="v3-cell-sub">· effective: {String(effective?.[def.key] ?? "—")}</span></div>
                <div className="v3-cell-sub text-xs">{def.hint}</div>
              </div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <input
                  aria-label={`${def.key} value`}
                  value={drafts[def.key] || ""}
                  onChange={(e) => setDrafts((d) => ({ ...d, [def.key]: e.target.value }))}
                  placeholder={String(effective?.[def.key] ?? "")}
                  style={{ width: 90 }}
                  id={`server-setting-${def.key}`}
                />
                <button type="button" className="v3-btn mini ghost" id={`propose-setting-${def.key}`} onClick={() => propose(def.key)}>
                  Propose
                </button>
              </div>
            </div>
          ))}
          {pendingId && (
            <div style={{ padding: "8px 10px", border: "1px dashed var(--v3-warn-text)", borderRadius: 6, fontSize: 12 }}>
              Pending proposal <span className="v3-mono">{pendingId}</span> for <strong>{pendingKey}</strong> — effective value unchanged until confirmed.
              <button type="button" className="v3-btn mini primary" id="confirm-setting-btn" style={{ marginLeft: 10 }} onClick={confirm}>
                Confirm & Verify
              </button>
            </div>
          )}
          {message && <div role="status" className="v3-cell-sub text-xs">{message}</div>}
        </div>
      )}
    </Panel>
  );
};

export const AdminSecuritySystemSettingsScreen: React.FC<AdminSecuritySystemSettingsScreenProps> = ({
  initialTab = "security",
  go,
}) => {
  const [activeTab, setActiveTab] = useState<"security" | "system" | "settings">(initialTab);

  useEffect(() => {
    if (initialTab) {
      setActiveTab(initialTab);
    }
  }, [initialTab]);

  // Handle Tab Switch
  const switchTab = (tab: "security" | "system" | "settings") => {
    setActiveTab(tab);
    if (go) go(tab);
  };

  // State collections
  const [sessions, setSessions] = useState<OwnerSessionRow[]>(() => getStoredOwnerSessions());
  const [devices, setDevices] = useState<OwnerDeviceRow[]>(() => getStoredOwnerDevices());
  const [settings, setSettings] = useState<OwnerSettingsState>(() => getStoredOwnerSettings());
  const [simulatedFeedback, setSimulatedFeedback] = useState<string | null>(null);

  // Search & Filter state
  const [sessionSearch, setSessionSearch] = useState<string>("");
  const [sessionStatusFilter, setSessionStatusFilter] = useState<string>("ALL");
  const [deviceSearch, setDeviceSearch] = useState<string>("");
  const [deviceStatusFilter, setDeviceStatusFilter] = useState<string>("ALL");
  const [inspectingDevice, setInspectingDevice] = useState<OwnerDeviceRow | null>(null);
  const [persistenceIntegration, setPersistenceIntegration] = useState<IntegrationResult<BackendPersistenceHealth>>({
    data: {
      adapterReachable: false,
      databaseConnected: false,
      schemaVersion: null,
      journalMode: "UNKNOWN",
      auditStoreOperational: false,
      auditEventCount: 0,
      subsystems: {},
    },
    source: "SAMPLE_FALLBACK",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: true,
  });

  const [securityStatusIntegration, setSecurityStatusIntegration] = useState<IntegrationResult<OwnerSecurityStatusPayload>>({
    data: {
      password_authentication: "FORBIDDEN",
      webauthn: "UNKNOWN",
      webauthn_enrollment: "UNKNOWN",
      normal_mtls: "UNKNOWN",
      break_glass: "UNKNOWN",
      owner_authenticators_ready: false,
      normal_mtls_required: true,
    },
    source: "SAMPLE_FALLBACK",
    trust: "UNKNOWN",
    asOf: new Date().toISOString(),
    isFallback: true,
  });

  const [sessionsSource, setSessionsSource] = useState<IntegrationSource>("UNAVAILABLE");

  useEffect(() => {
    let isMounted = true;
    queryPersistenceHealth().then((res) => {
      if (isMounted) {
        setPersistenceIntegration(res);
      }
    });
    querySecurityStatus().then((res) => {
      if (isMounted) {
        setSecurityStatusIntegration(res);
      }
    });
    queryOwnerSessions().then((res) => {
      if (isMounted) {
        setSessionsSource(res.source);
        if (res.source === "BACKEND") {
          setSessions(res.data || []);
        } else if (res.data && res.data.length > 0) {
          setSessions(res.data);
        }
      }
    });
    queryOwnerDevices().then((res) => {
      if (isMounted) {
        if (res.source === "BACKEND") {
          setDevices(res.data || []);
        } else if (res.data && res.data.length > 0) {
          setDevices(res.data);
        }
      }
    });
    return () => {
      isMounted = false;
    };
  }, []);

  // Single sources of truth
  const accessRecords = useMemo(() => getStoredAccessRecords(), []);
  const ownerUsers = useMemo(() => getStoredOwnerUsers(), []);
  const auditEvents = useMemo(() => getStoredOwnerAuditEvents(), []);

  // Entitlement metrics derived from canonical Access Registry
  const activeEntitlementsCount = useMemo(
    () => accessRecords.filter((r) => r.serviceStatus === "ACTIVE").length,
    [accessRecords]
  );
  const expiredEntitlementsCount = useMemo(
    () => accessRecords.filter((r) => r.serviceStatus === "EXPIRED").length,
    [accessRecords]
  );
  const unactivatedAccountsCount = useMemo(
    () => accessRecords.filter((r) => r.serviceStatus === "NOT_STARTED" || r.accountStatus === "PENDING").length,
    [accessRecords]
  );

  // Active devices and sessions count
  const activeSessions = useMemo(() => sessions.filter((s) => s.status === "ACTIVE"), [sessions]);
  const activeDevices = useMemo(() => devices.filter((d) => d.status === "TRUSTED_REGISTERED"), [devices]);

  // Derived Recovery Posture for accounts
  const recoveryPostures: OwnerRecoveryPosture[] = useMemo(() => {
    return [
      {
        sxId: "SX-U-ROOT-0001",
        userName: "Root Super Owner",
        role: "SUPER_OWNER",
        codesConfigured: true,
        codesRemaining: 8,
        readinessStatus: "HEALTHY",
        lastRegeneratedAt: "2026-06-01 09:00:00 UTC",
        primaryEmail: "owner@algofortis.internal",
        primaryEmailVerified: true,
        secondaryPhone: "+91 98200 *****",
        secondaryPhoneVerified: true,
        recoveryAssuranceState: "ACTIVE_SAMPLE",
        recoveryAssuranceExpiresIn: "08:42 remaining (SAMPLE)",
        warningLevel: "NONE",
      },
      {
        sxId: "SX-U-7M2W-51PQ",
        userName: "Vikram Malhotra",
        role: "Lead Strategist",
        codesConfigured: true,
        codesRemaining: 5,
        readinessStatus: "HEALTHY",
        lastRegeneratedAt: "2026-08-25 10:15:00 UTC",
        primaryEmail: "vikram@algofortis.internal",
        primaryEmailVerified: true,
        secondaryPhone: "+91 98111 *****",
        secondaryPhoneVerified: true,
        recoveryAssuranceState: "INACTIVE",
        warningLevel: "NONE",
      },
      {
        sxId: "SX-U-8K4P-92QX",
        userName: "Aarav Mehta",
        role: "Quant Trader",
        codesConfigured: true,
        codesRemaining: 2,
        readinessStatus: "LOW",
        lastRegeneratedAt: "2026-08-30 08:30:00 UTC",
        primaryEmail: "aarav@algofortis.internal",
        primaryEmailVerified: true,
        secondaryPhone: "Not Configured",
        secondaryPhoneVerified: false,
        recoveryAssuranceState: "INACTIVE",
        warningLevel: "WARNING",
      },
      {
        sxId: "SX-U-3N9D-88KX",
        userName: "Dev Test Rig",
        role: "Starter",
        codesConfigured: true,
        codesRemaining: 0,
        readinessStatus: "NONE",
        lastRegeneratedAt: "2026-07-01 08:00:00 UTC",
        primaryEmail: "dev-test@algofortis.internal",
        primaryEmailVerified: true,
        secondaryPhone: "Not Configured",
        secondaryPhoneVerified: false,
        recoveryAssuranceState: "INACTIVE",
        warningLevel: "PERSISTENT_CRITICAL",
      },
    ];
  }, []);

  // Filtered Sessions
  const filteredSessions = useMemo(() => {
    return sessions.filter((s) => {
      if (sessionStatusFilter !== "ALL" && s.status !== sessionStatusFilter) return false;
      if (!sessionSearch) return true;
      const q = sessionSearch.toLowerCase();
      return (
        s.sessionRef.toLowerCase().includes(q) ||
        s.sxId.toLowerCase().includes(q) ||
        s.userName.toLowerCase().includes(q) ||
        s.deviceName.toLowerCase().includes(q) ||
        s.authMethod.toLowerCase().includes(q)
      );
    });
  }, [sessions, sessionStatusFilter, sessionSearch]);

  // Filtered Devices
  const filteredDevices = useMemo(() => {
    return devices.filter((d) => {
      if (deviceStatusFilter !== "ALL" && d.status !== deviceStatusFilter) return false;
      if (!deviceSearch) return true;
      const q = deviceSearch.toLowerCase();
      return (
        d.deviceId.toLowerCase().includes(q) ||
        d.sxId.toLowerCase().includes(q) ||
        d.userName.toLowerCase().includes(q) ||
        d.deviceName.toLowerCase().includes(q) ||
        d.authenticatorType.toLowerCase().includes(q)
      );
    });
  }, [devices, deviceStatusFilter, deviceSearch]);

  // Session Revocation Handler
  const handleRevokeSession = async (sessionId: string) => {
    const target = sessions.find((s) => s.id === sessionId || s.sessionRef === sessionId);
    const ref = target ? (target.sessionRef || target.id) : sessionId;
    const res = await revokeBackendSession(ref);
    if (res.success) {
      const updated = await queryOwnerSessions();
      setSessions(updated.data);
      setSimulatedFeedback(`Session "${ref}" revoked successfully on Authoritative Backend.`);
    } else {
      const simRes = revokeOwnerSessionSimulated(sessionId);
      setSessions(getStoredOwnerSessions());
      setDevices(getStoredOwnerDevices());
      setSimulatedFeedback(simRes.message);
    }
  };

  const handleRevokeAllSessions = async (sxId: string) => {
    const res = await revokeAllBackendUserSessions(sxId);
    if (res.success) {
      const updated = await queryOwnerSessions();
      setSessions(updated.data);
      setSimulatedFeedback(`All sessions for "${sxId}" revoked (${res.data?.revoked_count ?? 0} sessions) on Backend Authority.`);
    } else {
      const simRes = revokeAllOwnerSessionsSimulated(sxId);
      setSessions(getStoredOwnerSessions());
      setDevices(getStoredOwnerDevices());
      setSimulatedFeedback(simRes.message);
    }
  };

  // Device Revocation Handler
  const handleRevokeDevice = async (deviceId: string) => {
    const target = devices.find((d) => d.id === deviceId || d.deviceId === deviceId);
    const credId = target ? (target.id || target.deviceId) : deviceId;
    const res = await revokeBackendDevice(credId);
    if (res.success) {
      const updated = await queryOwnerDevices();
      setDevices(updated.data);
      setSimulatedFeedback(`Device / Credential "${credId}" revoked terminally on Authoritative Backend.`);
    } else {
      const simRes = revokeOwnerDeviceSimulated(deviceId);
      setDevices(getStoredOwnerDevices());
      setSessions(getStoredOwnerSessions());
      setSimulatedFeedback(simRes.message);
    }
  };

  // Settings change handler
  const handleSettingChange = <K extends keyof OwnerSettingsState>(key: K, val: OwnerSettingsState[K]) => {
    updateOwnerSetting(key, val);
    setSettings(getStoredOwnerSettings());
    setSimulatedFeedback(`Presentation setting "${String(key)}" updated to "${String(val)}" (Local State).`);
  };

  // Clear feedback banner
  useEffect(() => {
    if (!simulatedFeedback) return;
    const timer = setTimeout(() => setSimulatedFeedback(null), 7000);
    return () => clearTimeout(timer);
  }, [simulatedFeedback]);

  // Recent security-relevant events projection from Step 8 audit store
  const securityAuditEvents = useMemo(() => {
    return auditEvents.slice(0, 5);
  }, [auditEvents]);

  return (
    <div className="v3-screen-container" id="owner-security-system-screen">
      {/* ── Screen Header ── */}
      <div className="v3-screen-head">
        <div>
          <h2 className="v3-screen-title">Security Authority, System Health &amp; Settings</h2>
          <p className="v3-screen-sub">
            Authoritative V1 security posture · subsystem architecture · fail-closed governance · system settings
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <TruthChip
            kind="REAL"
            title="Authoritative Security Authority & Subsystems (Backend SQLite)"
          />
        </div>
      </div>

      {/* ── Three-Level Authority Boundary Banner ── */}
      <div
        className="owner-inspection-banner"
        id="security-system-boundary-banner"
        style={{ marginBottom: 16, borderLeft: "3px solid #38bdf8" }}
      >
        <div className="banner-top-row">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="inspection-pulse-dot" style={{ color: "#38bdf8" }}>●</span>
            <span className="inspection-banner-title">
              OWNER SECURITY / SYSTEM OBSERVATION &amp; GOVERNANCE
            </span>
          </div>
          <span
            className="v3-mono text-xs"
            style={{
              color: "#38bdf8",
              background: "rgba(56, 189, 248, 0.1)",
              padding: "2px 8px",
              borderRadius: 4,
              border: "1px solid rgba(56, 189, 248, 0.3)",
            }}
          >
            AUTHORITATIVE RUNTIME
          </span>
        </div>
        <p className="banner-disclaimer" style={{ margin: "6px 0 0 0" }}>
          <strong>Three-Level Authority Model:</strong> (1) <em>Frontend Prototype</em> (DEV PREVIEW / SAMPLE, local state, simulated security requests); (2) <em>Frozen Security Contract</em> (<code>AUTH_ACCESS_CONTRACT_V1.md</code> behavioral semantics); (3) <em>Future Backend Authority</em> (Session store, WebAuthn passkey authority, recovery verification, rate-limit enforcement, server-time service entitlement enforcement). <strong>Backend integration is currently DEFERRED / NOT CONNECTED.</strong> All credentials, password hashes, and passkey private keys remain completely sealed.
        </p>
      </div>

      {/* ── Simulated Action Feedback Banner ── */}
      {simulatedFeedback && (
        <div
          className="v3-callout info"
          id="simulated-action-feedback-banner"
          style={{
            marginBottom: 16,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "rgba(56, 189, 248, 0.08)",
            border: "1px solid rgba(56, 189, 248, 0.3)",
            padding: "10px 14px",
            borderRadius: 6,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#38bdf8" }}>
            <Icon name="shield" size={14} />
            <span>{simulatedFeedback}</span>
          </div>
          <button
            type="button"
            className="v3-btn ghost mini"
            onClick={() => setSimulatedFeedback(null)}
            style={{ fontSize: 11, padding: "2px 6px" }}
          >
            ✕ Dismiss
          </button>
        </div>
      )}

      {/* ── Screen Navigation Tabs ── */}
      <div className="v3-tabs" role="tablist" aria-label="Security, System & Settings Tabs" style={{ marginBottom: 16 }}>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "security"}
          className={`v3-tab ${activeTab === "security" ? "active" : ""}`}
          onClick={() => switchTab("security")}
          id="tab-owner-security"
        >
          <Icon name="shield" size={13} style={{ marginRight: 6 }} /> Security Authority
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "system"}
          className={`v3-tab ${activeTab === "system" ? "active" : ""}`}
          onClick={() => switchTab("system")}
          id="tab-owner-system"
        >
          <Icon name="activity" size={13} style={{ marginRight: 6 }} /> System Health
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "settings"}
          className={`v3-tab ${activeTab === "settings" ? "active" : ""}`}
          onClick={() => switchTab("settings")}
          id="tab-owner-settings"
        >
          <Icon name="layers" size={13} style={{ marginRight: 6 }} /> System Settings
        </button>
      </div>

      {/* ════════════════════════════════════════════════════════════
          TAB 1: SECURITY AUTHORITY & SESSIONS
          ════════════════════════════════════════════════════════════ */}
      {activeTab === "security" && (
        <div className="v3-grid">
          {/* 1.1 Security Posture Overview Cards */}
          <Panel label="Institutional Security Posture (Frozen V1 Contract)" className="v3-sp12">
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
                gap: 12,
                padding: "4px 0",
              }}
            >
              <div className="v3-card" style={{ padding: "12px 14px", background: "var(--v3-surface-2)", borderRadius: 6 }}>
                <div className="v3-dim text-xs">AUTHENTICATION POLICY</div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
                  <Dot tone="ok" />
                  <strong style={{ fontSize: 13.5 }}>Password / Passkey / Platform Auth</strong>
                </div>
                <div className="v3-dim text-xs" style={{ marginTop: 4 }}>Frozen V1 behavioral contract · Credential storage: FUTURE BACKEND AUTHORITY</div>
              </div>

              <div className="v3-card" style={{ padding: "12px 14px", background: "var(--v3-surface-2)", borderRadius: 6 }}>
                <div className="v3-dim text-xs">SESSION SECURITY</div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
                  <Dot tone="ok" />
                  <strong style={{ fontSize: 13.5 }}>{activeSessions.length} Active Sessions</strong>
                </div>
                <div className="v3-dim text-xs" style={{ marginTop: 4 }}>Session storage/token: FUTURE BACKEND AUTHORITY · Revocation governed by contract</div>
              </div>

              <div className="v3-card" style={{ padding: "12px 14px", background: "var(--v3-surface-2)", borderRadius: 6 }}>
                <div className="v3-dim text-xs">REGISTERED DEVICES</div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
                  <Dot tone="ok" />
                  <strong style={{ fontSize: 13.5 }}>{activeDevices.length} Active Registered Devices</strong>
                </div>
                <div className="v3-dim text-xs" style={{ marginTop: 4 }}>Max 3 active/user quota (OD-AUTH-07)</div>
              </div>

              <div className="v3-card" style={{ padding: "12px 14px", background: "var(--v3-surface-2)", borderRadius: 6 }}>
                <div className="v3-dim text-xs">RECOVERY / VERIFICATION PATHS</div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
                  <Dot tone="ok" />
                  <strong style={{ fontSize: 13.5 }}>Multi-Path Recovery Protocol</strong>
                </div>
                <div className="v3-dim text-xs" style={{ marginTop: 4 }}>Verified email · Phone · 8x Codes · Trusted device/passkey · Owner</div>
              </div>

              <div className="v3-card" style={{ padding: "12px 14px", background: "var(--v3-surface-2)", borderRadius: 6 }}>
                <div className="v3-dim text-xs">RATE LIMIT / ABUSE MITIGATION</div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
                  <Dot tone="ok" />
                  <strong style={{ fontSize: 13.5 }}>Flow-Isolated Rate Limits</strong>
                </div>
                <div className="v3-dim text-xs" style={{ marginTop: 4 }}>Password/Activation: 5 attempts (Frozen) · Global limiter deferred to backend</div>
              </div>

              <div className="v3-card" style={{ padding: "12px 14px", background: "var(--v3-surface-2)", borderRadius: 6 }}>
                <div className="v3-dim text-xs">SUPER OWNER AUTHORITY (V1)</div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 4 }}>
                  <Dot tone="ok" />
                  <strong style={{ fontSize: 13.5 }}>Single Super Owner (Accepted SPOF)</strong>
                </div>
                <div className="v3-dim text-xs" style={{ marginTop: 4 }}>SAMPLE ACTOR REF: OWNER-001 · Zero impersonation · No risk bypass</div>
              </div>
            </div>
          </Panel>

          {/* 1.2 Active Authorized Sessions Inventory */}
          <Panel label={`Active Authorized Sessions Inventory (${sessions.length})`} className="v3-sp12">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input
                  type="text"
                  className="v3-input mini"
                  placeholder="Search sessions (Ref, User, SX-ID)..."
                  value={sessionSearch}
                  onChange={(e) => setSessionSearch(e.target.value)}
                  id="session-search-input"
                  style={{ width: 240 }}
                />
                <div className="v3-filter-group">
                  {["ALL", "ACTIVE", "EXPIRED", "REVOKED"].map((st) => (
                    <button
                      key={st}
                      type="button"
                      className={`v3-filter-btn ${sessionStatusFilter === st ? "active" : ""}`}
                      onClick={() => setSessionStatusFilter(st)}
                      id={`filter-session-${st.toLowerCase()}`}
                    >
                      {st}
                    </button>
                  ))}
                </div>
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  type="button"
                  className="v3-btn danger-ghost mini"
                  onClick={() => handleRevokeAllSessions("SX-U-ROOT-0001")}
                  id="revoke-all-owner-sessions-btn"
                  title="Simulate revoking all other sessions for Super Owner in local prototype state"
                >
                  Revoke Other Owner Sessions (Simulated)
                </button>
              </div>
            </div>

            <div className="v3-table-wrap">
              <table className="v3-table" id="owner-sessions-table">
                <thead>
                  <tr>
                    <th>SESSION REF</th>
                    <th>USER / ACCOUNT ID</th>
                    <th>DEVICE &amp; CLIENT</th>
                    <th>AUTH METHOD</th>
                    <th>LOCATION / IP</th>
                    <th>CREATED / LAST ACTIVE</th>
                    <th>CONTEXT</th>
                    <th>STATUS</th>
                    <th style={{ textAlign: "right" }}>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredSessions.length === 0 ? (
                    <tr>
                      <td colSpan={9} style={{ textAlign: "center", padding: "28px", color: "var(--v3-ink-dim)" }}>
                        {sessions.length === 0 ? "No active sessions yet" : "No sessions match the selected filter."}
                      </td>
                    </tr>
                  ) : (
                    filteredSessions.map((s) => (
                    <tr key={s.id} className="v3-table-row">
                      <td>
                        <span className="v3-mono font-bold" style={{ color: "#38bdf8" }}>{s.sessionRef}</span>
                        {s.isCurrent && (
                          <span className="v3-profit-badge" style={{ marginLeft: 6, fontSize: 9.5 }}>CURRENT</span>
                        )}
                      </td>
                      <td>
                        <div className="v3-cell-main font-semibold">{s.userName}</div>
                        <div className="v3-cell-sub v3-mono">{s.sxId} · {s.role}</div>
                      </td>
                      <td>
                        <div className="v3-cell-main">{s.deviceName}</div>
                        <div className="v3-cell-sub">{s.clientType}</div>
                      </td>
                      <td>
                        <span className="v3-mono text-xs" style={{ background: "var(--v3-surface-2)", padding: "2px 6px", borderRadius: 4 }}>
                          {s.authMethod}
                        </span>
                      </td>
                      <td>
                        <div className="v3-cell-main">{s.location}</div>
                        <div className="v3-cell-sub v3-mono">{s.ipMasked}</div>
                      </td>
                      <td>
                        <div className="v3-cell-main">{s.lastActive}</div>
                        <div className="v3-cell-sub v3-mono">{s.createdAt}</div>
                      </td>
                      <td>
                        {s.context === "RECOVERY_ASSURANCE_WINDOW" ? (
                          <span className="v3-status-badge warn" style={{ fontSize: 10 }}>
                            <Dot tone="warn" /> 10m RECOVERY WINDOW
                          </span>
                        ) : (
                          <span className="v3-dim text-xs">Standard</span>
                        )}
                      </td>
                      <td>
                        <span className={`v3-status-badge ${s.status.toLowerCase()}`}>
                          <Dot tone={TONE_MAP[s.status] ?? "ok"} /> {s.status}
                        </span>
                      </td>
                      <td style={{ textAlign: "right" }}>
                        {s.status === "ACTIVE" && !s.isCurrent ? (
                          <button
                            type="button"
                            className="v3-btn danger-ghost mini"
                            onClick={() => handleRevokeSession(s.id)}
                            id={`revoke-session-btn-${s.id}`}
                            title="Simulated security request: Revoke session in prototype state"
                          >
                            Revoke (Simulated)
                          </button>
                        ) : s.isCurrent ? (
                          <span className="v3-dim text-xs">Current Session</span>
                        ) : (
                          <span className="v3-dim text-xs">Terminated</span>
                        )}
                      </td>
                    </tr>
                  )))}
                </tbody>
              </table>
            </div>
            <div style={{ marginTop: 8, fontSize: 11.5, color: "var(--v3-ink-3)" }}>
              * Zero plaintext tokens, cookies, or secrets are exposed. Owner session revocation is a <strong>SIMULATED SECURITY REQUEST</strong> updating local prototype state.
            </div>
          </Panel>

          {/* 1.3 Registered Device Registry & Quotas */}
          <Panel label={`Registered Device Registry (${devices.length}) — Max 3 Active Devices/User (OD-AUTH-07)`} className="v3-sp12">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input
                  type="text"
                  className="v3-input mini"
                  placeholder="Search devices (ID, Platform, User)..."
                  value={deviceSearch}
                  onChange={(e) => setDeviceSearch(e.target.value)}
                  id="device-search-input"
                  style={{ width: 240 }}
                />
                <div className="v3-filter-group">
                  {["ALL", "TRUSTED_REGISTERED", "REVOKED"].map((dst) => (
                    <button
                      key={dst}
                      type="button"
                      className={`v3-filter-btn ${deviceStatusFilter === dst ? "active" : ""}`}
                      onClick={() => setDeviceStatusFilter(dst)}
                      id={`filter-device-${dst.toLowerCase()}`}
                    >
                      {dst === "TRUSTED_REGISTERED" ? "ACTIVE REGISTERED" : dst}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="v3-table-wrap">
              <table className="v3-table" id="owner-devices-table">
                <thead>
                  <tr>
                    <th>DEVICE ID</th>
                    <th>USER / ACCOUNT ID</th>
                    <th>DEVICE NAME &amp; PLATFORM</th>
                    <th>AUTHENTICATOR BINDING</th>
                    <th>REGISTERED / LAST SEEN</th>
                    <th>ACTIVE SESSIONS</th>
                    <th>STATUS</th>
                    <th style={{ textAlign: "right" }}>ACTIONS</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDevices.length === 0 ? (
                    <tr>
                      <td colSpan={8} style={{ textAlign: "center", padding: "28px", color: "var(--v3-ink-dim)" }}>
                        {devices.length === 0 ? "No registered devices yet" : "No devices match the selected filter."}
                      </td>
                    </tr>
                  ) : (
                    filteredDevices.map((d) => (
                    <tr key={d.id} className="v3-table-row">
                      <td>
                        <span className="v3-mono font-bold">{d.deviceId}</span>
                      </td>
                      <td>
                        <div className="v3-cell-main font-semibold">{d.userName}</div>
                        <div className="v3-cell-sub v3-mono">{d.sxId}</div>
                      </td>
                      <td>
                        <div className="v3-cell-main">{d.deviceName}</div>
                        <div className="v3-cell-sub">{d.platform}</div>
                      </td>
                      <td>
                        <div className="v3-cell-main">{d.authenticatorType}</div>
                        <div className="v3-cell-sub v3-mono">{d.credentialIdMasked}</div>
                      </td>
                      <td>
                        <div className="v3-cell-main">{d.lastSeen}</div>
                        <div className="v3-cell-sub v3-mono">{d.registeredAt}</div>
                      </td>
                      <td>
                        <span className="v3-mono font-bold">{d.activeSessionCount}</span>
                      </td>
                      <td>
                        <span className={`v3-status-badge ${d.status === "TRUSTED_REGISTERED" ? "ok" : "neg"}`}>
                          <Dot tone={d.status === "TRUSTED_REGISTERED" ? "ok" : "neg"} />
                          {d.status === "TRUSTED_REGISTERED" ? "TRUSTED (ACTIVE)" : "REVOKED"}
                        </span>
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <div style={{ display: "inline-flex", gap: 6, justifyContent: "flex-end" }}>
                          <button
                            type="button"
                            className="v3-btn ghost mini"
                            onClick={() => setInspectingDevice(d)}
                            id={`inspect-device-btn-${d.id}`}
                            title="Inspect device details"
                          >
                            Inspect
                          </button>
                          {d.status === "TRUSTED_REGISTERED" && (
                            <button
                              type="button"
                              className="v3-btn danger-ghost mini"
                              onClick={() => handleRevokeDevice(d.deviceId)}
                              id={`revoke-device-btn-${d.id}`}
                              title="Simulated security request: Revoke device and retain historical audit record"
                            >
                              Revoke (Simulated)
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )))}
                </tbody>
              </table>
            </div>
            <div style={{ marginTop: 8, fontSize: 11.5, color: "var(--v3-ink-3)" }}>
              * Per frozen contract <strong>OD-AUTH-07</strong>, maximum 3 active registered devices allowed per user. Silent auto-revocation is prohibited. Revoked devices are permanently preserved in historical audit state and do not consume quota.
            </div>
          </Panel>

          {/* 1.4 Recovery Security & 10-Minute Assurance Window */}
          <Panel label="Recovery &amp; Verification Paths Posture (Frozen V1 Contract)" className="v3-sp6">
            <div style={{ padding: "8px 10px", background: "var(--v3-surface-2)", borderRadius: 6, marginBottom: 12, fontSize: 12, lineHeight: 1.4 }}>
              <strong>Recovery &amp; Verification Paths:</strong> Verified email primary, optional phone secondary, 8x recovery codes independent emergency path, trusted device/passkey where appropriate, and Owner-assisted recovery final fallback. Plaintext recovery code values, verifiers, and password hashes are <em>never</em> visible.
            </div>

            <div className="v3-rows">
              {recoveryPostures.map((rp) => (
                <div className="v3-row" key={rp.sxId}>
                  <div className="v3-row-main">
                    <div className="v3-row-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span className="font-semibold">{rp.userName}</span>
                      <span className="v3-mono text-xs" style={{ color: "#38bdf8" }}>{rp.sxId}</span>
                      <span className={`v3-status-badge ${rp.readinessStatus === "HEALTHY" ? "ok" : rp.readinessStatus === "LOW" ? "warn" : "neg"}`}>
                        <Dot tone={TONE_MAP[rp.readinessStatus]} /> {rp.readinessStatus} ({rp.codesRemaining}/8 Codes)
                      </span>
                    </div>
                    <div className="v3-row-sub">
                      Primary Email: <code className="v3-mono">{rp.primaryEmail}</code> · Phone: <code className="v3-mono">{rp.secondaryPhone}</code> · Regenerated: {rp.lastRegeneratedAt}
                    </div>
                    {rp.warningLevel !== "NONE" && (
                      <div style={{ marginTop: 4, fontSize: 11, color: rp.warningLevel === "PERSISTENT_CRITICAL" ? "var(--sx-ruby)" : "var(--sx-amber)" }}>
                        {rp.warningLevel === "WARNING" && "⚠ Warning: 2 recovery codes remaining — user prompted to replenish."}
                        {rp.warningLevel === "STRONG_WARNING" && "⚠ Strong Warning: 1 recovery code remaining — urgent replenishment needed."}
                        {rp.warningLevel === "PERSISTENT_CRITICAL" && "⛔ Critical: 0 recovery codes remaining — persistent replenishment prompt active (Account NOT locked)."}
                      </div>
                    )}
                  </div>
                  {rp.recoveryAssuranceState === "ACTIVE_SAMPLE" && (
                    <span className="v3-status-badge warn" style={{ fontSize: 10, flexShrink: 0 }}>
                      <Dot tone="warn" /> ASSURANCE WINDOW: {rp.recoveryAssuranceExpiresIn}
                    </span>
                  )}
                </div>
              ))}
            </div>

            <div style={{ marginTop: 12, fontSize: 11.5, color: "var(--v3-ink-3)", lineHeight: 1.4 }}>
              * <strong>10-Minute Recovery Assurance Window (OD-AUTH-16):</strong> High-assurance recovery opens a bounded 10-minute window for password and recovery code updates. It does <em>not</em> grant elevated admin privileges.
            </div>
          </Panel>

          {/* 1.5 Rate Limiting & Flow Isolation Table */}
          <Panel label="Flow-Isolated Rate Limiting &amp; Abuse Protection (Frozen Policy)" className="v3-sp6">
            <div style={{ padding: "8px 10px", background: "var(--v3-surface-2)", borderRadius: 6, marginBottom: 12, fontSize: 12, lineHeight: 1.4 }}>
              <strong>Abuse Isolation Guarantee:</strong> Rate limit violations fail closed on the specific endpoint. An attacker brute-forcing password or recovery endpoints <em>never</em> triggers administrative account suspension (<code>accountStatus: "SUSPENDED"</code>).
            </div>

            <div className="v3-rows">
              {INITIAL_RATE_LIMIT_POLICIES.map((rl) => (
                <div className="v3-row" key={rl.id}>
                  <div className="v3-row-main">
                    <div className="v3-row-title" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span className="font-semibold">{rl.flowName}</span>
                      <span className="v3-mono text-xs v3-dim">{rl.targetEndpoint}</span>
                      <span className={`v3-status-badge ${rl.isFrozen ? "ok" : "dim"}`} style={{ fontSize: 9.5 }}>
                        <Dot tone={rl.isFrozen ? "ok" : "dim"} /> {rl.policyStatus === "FROZEN_V1_POLICY" ? "FROZEN V1" : "BACKEND DEFERRED"}
                      </span>
                    </div>
                    <div className="v3-row-sub">
                      Threshold: <strong>{rl.failureThreshold}</strong> · Cooldown: <strong>{rl.escalationCooldown}</strong>
                    </div>
                    <div className="v3-dim text-xs" style={{ marginTop: 2 }}>{rl.isolationGuarantee}</div>
                  </div>
                </div>
              ))}
            </div>

            <div style={{ marginTop: 12, fontSize: 11.5, color: "var(--v3-ink-3)" }}>
              * Technical parameters &amp; enforcement implementation for Recovery Codes, OTP, and Global Abuse / Risk Limiter are deferred to backend security design. No arbitrary thresholds or implementation technologies are invented.
            </div>
          </Panel>

          {/* 1.6 Security Events Projection & Full Audit Link */}
          <Panel label="Recent Security Events Projection (Step 8 Audit Reference)" className="v3-sp12">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <span className="v3-dim text-xs">
                Displaying compact sample projection of recent security mutations. Full tamper-evident audit journal is in Step 8.
              </span>
              {go && (
                <button
                  type="button"
                  className="v3-btn primary mini"
                  onClick={() => go("audit")}
                  id="view-full-audit-btn"
                >
                  <Icon name="file" size={12} style={{ marginRight: 4 }} /> View Full Audit Ledger →
                </button>
              )}
            </div>

            <div className="v3-table-wrap">
              <table className="v3-table">
                <thead>
                  <tr>
                    <th>EVENT ID</th>
                    <th>TIMESTAMP</th>
                    <th>FAMILY / TYPE</th>
                    <th>ACTOR</th>
                    <th>SEVERITY</th>
                    <th>DETAILS</th>
                    <th>EVIDENCE REF</th>
                  </tr>
                </thead>
                <tbody>
                  {securityAuditEvents.map((e) => (
                    <tr key={e.id}>
                      <td><span className="v3-mono font-bold">{e.eventId}</span></td>
                      <td><span className="v3-mono text-xs">{e.timestamp}</span></td>
                      <td>
                        <span className="v3-mono text-xs font-semibold">{e.eventFamily}</span>
                        <div className="v3-cell-sub">{e.eventType}</div>
                      </td>
                      <td><span className="v3-mono">{e.actor}</span></td>
                      <td>
                        <span className={`v3-status-badge ${e.severity === "CRITICAL" ? "neg" : e.severity === "WARNING" ? "warn" : "ok"}`}>
                          <Dot tone={e.severity === "CRITICAL" ? "neg" : e.severity === "WARNING" ? "warn" : "ok"} /> {e.severity}
                        </span>
                      </td>
                      <td>{e.details}</td>
                      <td><span className="v3-mono text-xs v3-dim">{e.evidenceRef}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}

      {/* ════════════════════════════════════════════════════════════
          TAB 2: SYSTEM HEALTH & SUBSYSTEM ARCHITECTURE
          ════════════════════════════════════════════════════════════ */}
      {activeTab === "system" && (
        <div className="v3-grid">
          {/* 2.1 Subsystem Architecture & Integration Health Deck */}
          <Panel label="Subsystem Health &amp; Architectural Boundaries (8 Subsystems)" className="v3-sp12">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 }}>
              {INITIAL_SYSTEM_SUBSYSTEMS.map((sub) => (
                <div
                  key={sub.id}
                  className="v3-card"
                  style={{
                    padding: "14px",
                    background: "var(--v3-surface-2)",
                    borderRadius: 6,
                    border: sub.status === "NOT_CONNECTED" ? "1px solid rgba(245, 158, 11, 0.4)" : "1px solid var(--v3-line-1)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
                    <div>
                      <span className="v3-dim text-xs">{sub.category}</span>
                      <h4 style={{ margin: "2px 0 0 0", fontSize: 14, color: "#fff", fontWeight: 600 }}>{sub.name}</h4>
                    </div>
                    <span className={`v3-status-badge ${sub.status === "OPERATIONAL" || sub.status === "FAIL_CLOSED" ? "ok" : sub.status === "NOT_CONNECTED" ? "warn" : "dim"}`}>
                      <Dot tone={sub.tone} /> {sub.currentStatusLabel}
                    </span>
                  </div>
                  <div style={{ fontSize: 12.5, color: "var(--v3-ink-2)", margin: "8px 0" }}>{sub.detail}</div>
                  <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--v3-line-1)", fontSize: 11.5 }}>
                    <div className="v3-dim">Target Architecture:</div>
                    <div className="v3-mono" style={{ color: "#38bdf8", fontSize: 11 }}>{sub.targetArchitecture}</div>
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          {/* 2.2 Persistence & Audit Authority Boundary Panel */}
          <Panel label="Persistence Authority &amp; Core Audit Health Boundary" className="v3-sp6">
            <dl style={{ margin: 0 }}>
              <KV
                k="Frontend State Authority"
                v={
                  persistenceIntegration.source === "BACKEND" && persistenceIntegration.data.databaseConnected ? (
                    <span className="v3-status-badge ok"><Dot tone="ok" /> REAL BACKEND PROJECTION (SQLite WAL)</span>
                  ) : (
                    <span className="v3-status-badge dim"><Dot tone="dim" /> BROWSER LOCAL STORAGE (PROTOTYPE)</span>
                  )
                }
              />
              <KV
                k="Target Database Architecture"
                v={
                  persistenceIntegration.source === "BACKEND" && persistenceIntegration.data.databaseConnected ? (
                    <span className="v3-mono">SQLite WAL Mode (Schema V{persistenceIntegration.data.schemaVersion ?? 7} · D16 / ACID Crash Resilience)</span>
                  ) : (
                    <span className="v3-mono">SQLite WAL Mode (D16 / ACID Crash Resilience)</span>
                  )
                }
              />
              <KV
                k="Audit Framework"
                v={<span className="v3-mono font-bold">D16 Schema &amp; Event Taxonomy (E1–E22)</span>}
              />
              <KV
                k="Cryptographic Seal Chain"
                v="SHA-256 Backlink Hash Chain (Model Specification)"
              />
              <KV
                k="Backend Wiring Status"
                v={
                  persistenceIntegration.source === "BACKEND" && persistenceIntegration.data.databaseConnected ? (
                    <span className="v3-status-badge ok"><Dot tone="ok" /> OPERATIONAL (Integration Adapter Connected)</span>
                  ) : (
                    <span className="v3-status-badge warn"><Dot tone="warn" /> NOT CONNECTED / DEFERRED</span>
                  )
                }
              />
              <KV
                k="Reports & Audit Ledger"
                v={
                  go ? (
                    <button
                      type="button"
                      className="v3-btn ghost mini"
                      onClick={() => go("reports")}
                      id="system-view-reports-btn"
                    >
                      View Reports &amp; Audit →
                    </button>
                  ) : (
                    "Available in Reports & Audit"
                  )
                }
              />
            </dl>
            <div style={{ marginTop: 12, fontSize: 11.5, color: "var(--v3-ink-3)", lineHeight: 1.4 }}>
              * <strong>Boundary Declaration:</strong> Step 9 displays system observation and health status. It does <em>not</em> duplicate the Step 8 Audit Ledger or claim browser memory has WAL durability.
            </div>
          </Panel>

          {/* 2.3 Version, Environment & Clock Telemetry */}
          <Panel label="Version, Environment &amp; Real-Time Clock Telemetry" className="v3-sp6">
            <dl style={{ margin: 0 }}>
              <KV k="Dashboard Interface" v="AlgoFortis Workstation V3 (Enterprise Workstation)" />
              <KV k="Build Environment" v={<span className="v3-mono">DEV PREVIEW / SAMPLE · Development Build</span>} />
              <KV k="Package Authority" v={<span className="v3-mono">algofortis-control-center v9.0.0</span>} />
              <KV k="Engine Interface Target" v={<span className="v3-mono">FastAPI / Python 3.12 (localhost:8000)</span>} />
              <KV k="Audit Contract Schema" v={<span className="v3-mono font-bold">D16 (Core Audit Taxonomy &amp; Envelope)</span>} />
              <KV
                k="Local UI Clock"
                v={<span className="v3-mono font-bold" style={{ color: "#38bdf8" }}>LOCAL UI CLOCK — INFORMATIONAL ONLY</span>}
              />
              <KV k="Time Authority Rule" v="Server UTC Wall-Clock Authority (OD-AUTH-24)" />
              <KV k="Active Service Entitlements" v={`${activeEntitlementsCount} Active · ${expiredEntitlementsCount} Expired · ${unactivatedAccountsCount} Pending`} />
            </dl>
            <div style={{ marginTop: 12, fontSize: 11.5, color: "var(--v3-ink-3)", lineHeight: 1.4 }}>
              * <strong>Non-Authoritative Client Clock:</strong> Browser clocks are strictly informational. All production term expirations and session timeouts are evaluated against authoritative server UTC wall-clock time.
            </div>
          </Panel>
        </div>
      )}

      {/* ════════════════════════════════════════════════════════════
          TAB 3: SYSTEM SETTINGS GOVERNANCE
          ════════════════════════════════════════════════════════════ */}
      {activeTab === "settings" && (
        <div className="v3-grid">
          {/* 3.1 Frozen V1 Policy Settings (Read-Only) */}
          <Panel label="Frozen V1 Architectural Invariants (READ-ONLY)" className="v3-sp6">
            <div style={{ padding: "8px 10px", background: "var(--v3-surface-2)", borderRadius: 6, marginBottom: 12, fontSize: 12, lineHeight: 1.4 }}>
              <strong>Frozen Governance Precedence:</strong> The policies below represent authoritative AlgoFortis V1 architecture. They are <em>strictly read-only</em> and cannot be modified via UI controls.
            </div>

            <div className="v3-rows">
              <div className="v3-row">
                <div className="v3-row-main">
                  <div className="v3-row-title font-semibold">Activation Code Expiration Window</div>
                  <div className="v3-row-sub">Fixed 24 Hours from issuance · Manual Owner-only reissuance (OD-AUTH-01)</div>
                </div>
                <span className="v3-status-badge ok" style={{ fontSize: 10 }}>FROZEN V1 POLICY</span>
              </div>

              <div className="v3-row">
                <div className="v3-row-main">
                  <div className="v3-row-title font-semibold">Maximum Active Registered Devices</div>
                  <div className="v3-row-sub">Max 3 active devices per user · No silent auto-revocation (OD-AUTH-07)</div>
                </div>
                <span className="v3-status-badge ok" style={{ fontSize: 10 }}>FROZEN V1 POLICY</span>
              </div>

              <div className="v3-row">
                <div className="v3-row-main">
                  <div className="v3-row-title font-semibold">Service Entitlement Duration Anchor</div>
                  <div className="v3-row-sub">Clock begins on first successful activation · Calendar-month UTC clamping (OD-AUTH-19, OD-AUTH-24)</div>
                </div>
                <span className="v3-status-badge ok" style={{ fontSize: 10 }}>FROZEN V1 POLICY</span>
              </div>

              <div className="v3-row">
                <div className="v3-row-main">
                  <div className="v3-row-title font-semibold">Recovery Assurance Window</div>
                  <div className="v3-row-sub">10-Minute bounded window upon high-assurance recovery (OD-AUTH-16)</div>
                </div>
                <span className="v3-status-badge ok" style={{ fontSize: 10 }}>FROZEN V1 POLICY</span>
              </div>

              <div className="v3-row">
                <div className="v3-row-main">
                  <div className="v3-row-title font-semibold">Three Independent State Axes</div>
                  <div className="v3-row-sub">ActivationStatus · AccountAccessStatus · ServiceEntitlementStatus strictly decoupled</div>
                </div>
                <span className="v3-status-badge ok" style={{ fontSize: 10 }}>FROZEN V1 POLICY</span>
              </div>

              <div className="v3-row">
                <div className="v3-row-main">
                  <div className="v3-row-title font-semibold">Single Super Owner Authority (V1)</div>
                  <div className="v3-row-sub">Single Super Owner authority (SAMPLE ACTOR REF: OWNER-001) · Zero impersonation · No risk bypass (OD-AUTH-06)</div>
                </div>
                <span className="v3-status-badge ok" style={{ fontSize: 10 }}>FROZEN V1 POLICY</span>
              </div>
            </div>
          </Panel>

          {/* 3.2 Owner Configurable Prototype Settings (Presentation / Local State) */}
          <Panel label="Owner Configurable Presentation Preferences (Local State)" className="v3-sp6">
            <div style={{ padding: "8px 10px", background: "var(--v3-surface-2)", borderRadius: 6, marginBottom: 12, fontSize: 12, lineHeight: 1.4 }}>
              <strong>Safe Presentation Preferences:</strong> These settings govern workstation UI presentation in local prototype state only. They do not alter security contracts or backend enforcement.
            </div>

            <dl style={{ margin: 0 }}>
              <div style={{ padding: "10px 0", borderBottom: "1px solid var(--v3-line-1)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div className="font-semibold" style={{ fontSize: 13 }}>Default Owner Landing Section</div>
                  <div className="v3-dim text-xs">Target view when launching Owner Control Center</div>
                </div>
                <select
                  className="v3-input mini"
                  value={settings.defaultLandingView}
                  onChange={(e) => handleSettingChange("defaultLandingView", e.target.value as any)}
                  id="setting-landing-view-select"
                  style={{ width: 160 }}
                >
                  <option value="overview">Overview</option>
                  <option value="users">Users Oversight</option>
                  <option value="system">System Health</option>
                  <option value="security">Security Authority</option>
                </select>
              </div>

              <div style={{ padding: "10px 0", borderBottom: "1px solid var(--v3-line-1)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div className="font-semibold" style={{ fontSize: 13 }}>Table Row Density</div>
                  <div className="v3-dim text-xs">Workstation display density for audit &amp; blotter tables</div>
                </div>
                <select
                  className="v3-input mini"
                  value={settings.uiDensity}
                  onChange={(e) => handleSettingChange("uiDensity", e.target.value as any)}
                  id="setting-row-density-select"
                  style={{ width: 160 }}
                >
                  <option value="comfortable">Comfortable (Default)</option>
                  <option value="compact">Compact (High-Density)</option>
                </select>
              </div>

              <div style={{ padding: "10px 0", borderBottom: "1px solid var(--v3-line-1)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div className="font-semibold" style={{ fontSize: 13 }}>UI Inactivity Warning</div>
                  <div className="v3-dim text-xs">
                    <strong>UI INACTIVITY WARNING ONLY</strong> — NOT an authentication / session timeout
                  </div>
                </div>
                <select
                  className="v3-input mini"
                  value={settings.uiInactivityWarning}
                  onChange={(e) => handleSettingChange("uiInactivityWarning", e.target.value as any)}
                  id="setting-inactivity-warning-select"
                  style={{ width: 160 }}
                >
                  <option value="15m">15 Minutes</option>
                  <option value="30m">30 Minutes</option>
                  <option value="60m">60 Minutes</option>
                  <option value="disabled">Disabled</option>
                </select>
              </div>

              <div style={{ padding: "10px 0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div className="font-semibold" style={{ fontSize: 13 }}>Critical Alert Chime (Audio)</div>
                  <div className="v3-dim text-xs">Audio notification on critical risk / security alerts</div>
                </div>
                <label className="v3-switch-label" style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={settings.audioChimeOnCriticalAlert}
                    onChange={(e) => handleSettingChange("audioChimeOnCriticalAlert", e.target.checked)}
                    id="setting-audio-chime-checkbox"
                  />
                  <span className="v3-mono text-xs">{settings.audioChimeOnCriticalAlert ? "ENABLED" : "DISABLED"}</span>
                </label>
              </div>
            </dl>
          </Panel>

          {/* 3.3 Server-Authoritative Settings (Backend Governed) */}
          <ServerAuthoritativeSettingsPanel />

          {/* 3.4 Strict Safety Boundaries Panel */}
          <Panel label="Strict Architectural Safety Boundaries (Non-Bypassable)" className="v3-sp12">
            <div style={{ padding: "12px 14px", background: "rgba(244, 63, 94, 0.06)", border: "1px solid rgba(244, 63, 94, 0.25)", borderRadius: 6 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--sx-ruby)", fontWeight: 650, fontSize: 13.5, marginBottom: 6 }}>
                <Icon name="shield" size={16} />
                <span>ARCHITECTURALLY BANNED CONTROLS &amp; RISK BYPASS RESTRICTIONS</span>
              </div>
              <p style={{ margin: "0 0 10px 0", fontSize: 12.5, color: "var(--v3-ink-2)", lineHeight: 1.4 }}>
                In accordance with the AlgoFortis V1 Governance Contract and institutional safety rules, the following controls are <strong>strictly omitted</strong> and cannot be exposed:
              </p>
              <ul style={{ margin: 0, paddingLeft: 20, fontSize: 12, color: "var(--v3-ink-3)", lineHeight: 1.6 }}>
                <li><strong>No Risk Bypass:</strong> No setting can disable pre-trade margin checks, max loss boundaries, or position ceilings.</li>
                <li><strong>No Protective Runtime Disable:</strong> Live stop-loss monitors and emergency position reduction cannot be turned off.</li>
                <li><strong>No Audit Ledger Modification:</strong> Core Audit is tamper-evident and append-only; no edit/clear controls exist.</li>
                <li><strong>No Authentication Bypass:</strong> WebAuthn and credential verification cannot be globally toggled off.</li>
                <li><strong>No Secret Reveal Controls:</strong> Passwords, private keys, TOTP seeds, and recovery code values are never accessible.</li>
              </ul>
            </div>
          </Panel>
        </div>
      )}

      {/* ── Device Inspection Drawer ── */}
      {inspectingDevice && (
        <Drawer
          open={Boolean(inspectingDevice)}
          title={`Device Inspection · ${inspectingDevice.deviceId}`}
          sub="Registered Hardware Device Record · DEV PREVIEW / SAMPLE"
          onClose={() => setInspectingDevice(null)}
        >
          <div className="v3-drawer-body">
            <Panel label="Device Metadata & Binding" className="v3-sp12">
              <dl style={{ margin: 0 }}>
                <KV k="Device Identifier" v={<span className="v3-mono font-bold">{inspectingDevice.deviceId}</span>} />
                <KV k="Bound User" v={inspectingDevice.userName} />
                <KV k="Account ID" v={<span className="v3-mono">{inspectingDevice.sxId}</span>} />
                <KV k="Device Name" v={inspectingDevice.deviceName} />
                <KV k="Operating Platform" v={inspectingDevice.platform} />
                <KV k="Authenticator Type" v={inspectingDevice.authenticatorType} />
                <KV k="Credential Reference" v={<span className="v3-mono">{inspectingDevice.credentialIdMasked}</span>} />
                <KV k="Registration Date" v={inspectingDevice.registeredAt} />
                <KV k="Last Seen" v={inspectingDevice.lastSeen} />
                <KV
                  k="Trust Status"
                  v={
                    <span className={`v3-status-badge ${inspectingDevice.status === "TRUSTED_REGISTERED" ? "ok" : "neg"}`}>
                      <Dot tone={inspectingDevice.status === "TRUSTED_REGISTERED" ? "ok" : "neg"} />
                      {inspectingDevice.status === "TRUSTED_REGISTERED" ? "TRUSTED & ACTIVE" : "REVOKED"}
                    </span>
                  }
                />
                <KV k="Active Session Count" v={inspectingDevice.activeSessionCount} />
                {inspectingDevice.revokedAt && <KV k="Revocation Timestamp" v={inspectingDevice.revokedAt} />}
                {inspectingDevice.revokedReason && <KV k="Revocation Reason" v={inspectingDevice.revokedReason} />}
              </dl>
            </Panel>

            <div style={{ marginTop: 16, display: "flex", gap: 8, justifyContent: "flex-end" }}>
              {inspectingDevice.status === "TRUSTED_REGISTERED" && (
                <button
                  type="button"
                  className="v3-btn danger-ghost mini"
                  onClick={() => {
                    handleRevokeDevice(inspectingDevice.deviceId);
                    setInspectingDevice(null);
                  }}
                  id="drawer-revoke-device-btn"
                >
                  Revoke Device Registration (Simulated)
                </button>
              )}
              <button
                type="button"
                className="v3-btn ghost mini"
                onClick={() => setInspectingDevice(null)}
              >
                Close
              </button>
            </div>
          </div>
        </Drawer>
      )}
    </div>
  );
};
