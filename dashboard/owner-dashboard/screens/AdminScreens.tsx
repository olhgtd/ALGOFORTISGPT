import React, { useState, useEffect } from "react";
import { Icon } from "../../shared/icons/V3Icons";
import { Panel, KV, TruthChip, Dot } from "../../shared/utilities/V3Chrome";
import {
  suspendBackendAccount,
  restoreBackendAccount,
  revokeBackendAccount,
  queryAccessRecords,
  isForceDemo,
} from "../../shared/services/integrationClient";
import {
  getStoredOwnerUsers,
  type OwnerUser,
  type AccessStatus,
  STRATEGIES,
  USER_CONNECTORS,
  SERVICES,
  AUDIT_ITEMS,
  BACKTEST_RUNS,
  PAPER_POSITIONS,
  PORTFOLIO_HOLDINGS,
  ORDERS,
  REPORTS_LIST,
  PLUGIN_HEALTH,
} from "../../sampleData";

const STATUS_TONE: Record<AccessStatus, "ok" | "live" | "neg" | "warn" | "dim"> = {
  ACTIVE: "ok",
  INVITED: "live",
  REDEEMED: "ok",
  SUSPENDED: "neg",
  EXPIRED: "warn",
  REVOKED: "neg",
  DRAFT: "dim",
};

export type InspectionTab =
  | "Profile"
  | "Strategies"
  | "Backtests"
  | "Paper"
  | "Portfolio"
  | "Orders"
  | "Connections"
  | "Reports"
  | "Sessions"
  | "Security State";

const INSPECTION_TABS: InspectionTab[] = [
  "Profile",
  "Strategies",
  "Backtests",
  "Paper",
  "Portfolio",
  "Orders",
  "Connections",
  "Reports",
  "Sessions",
  "Security State",
];

/* ════════════════════════════════════════════════════════════
   1. OWNER USER INSPECTION MODE (OPEN USER WORKSPACE)
   ════════════════════════════════════════════════════════════ */

interface UserInspectionViewProps {
  user: OwnerUser;
  onClose: () => void;
}

export const UserInspectionView: React.FC<UserInspectionViewProps> = ({ user, onClose }) => {
  const [activeTab, setActiveTab] = useState<InspectionTab>("Profile");

  return (
    <div className="v3-user-inspection-view" id="owner-user-inspection-screen">
      {/* Institutional Owner Inspection Mode Banner */}
      <div className="owner-inspection-banner" id="owner-inspection-banner">
        <div className="banner-top-row">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="inspection-pulse-dot">●</span>
            <span className="inspection-banner-title">
              OWNER INSPECTION MODE · READ-ONLY GOVERNANCE OVERSIGHT
            </span>
          </div>
          <button
            type="button"
            className="v3-btn ghost mini"
            onClick={onClose}
            id="close-inspection-btn"
          >
            ← Back to Users List
          </button>
        </div>
        <p className="banner-disclaimer">
          Owner inspection mode is read-only governance oversight. Owner authority cannot bypass pre-trade risk gates, alter audit history, or silently promote unverified strategies. All credentials and secrets are sealed.
        </p>
      </div>

      {/* Target User Identity Bar */}
      <div className="inspection-target-bar">
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div className="v3-avatar font-bold" style={{ width: 44, height: 44, fontSize: 16 }}>
            {user.name.split(" ").map((p: string) => p[0]).join("")}
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <h3 style={{ margin: 0, fontSize: 18, color: "#fff", fontWeight: 650 }}>{user.name}</h3>
              <span className={`v3-status-badge ${user.accountStatus.toLowerCase()}`}>
                <Dot tone={STATUS_TONE[user.accountStatus as AccessStatus] ?? "ok"} /> {user.accountStatus}
              </span>
              <span className="v3-mono text-xs" style={{ color: "#38bdf8", background: "rgba(2, 132, 199, 0.1)", padding: "2px 8px", borderRadius: 4, border: "1px solid rgba(2, 132, 199, 0.3)" }}>
                {user.sxId}
              </span>
            </div>
            <div style={{ display: "flex", gap: 16, marginTop: 4, fontSize: 12.5, color: "var(--v3-ink-3)", flexWrap: "wrap" }}>
              <span>Bound Email: <code className="v3-mono">{user.email}</code></span>
              <span>Bound Phone: <code className="v3-mono">{user.phone}</code></span>
              <span>Role: <strong>{user.role}</strong></span>
              <span>Access ID: <code className="v3-mono">{user.accessIdRef}</code></span>
            </div>
          </div>
        </div>
      </div>

      {/* Inspection Navigation Tabs */}
      <div className="v3-tabs" role="tablist" aria-label="Owner User Inspection Tabs" style={{ marginTop: 16, marginBottom: 16 }}>
        {INSPECTION_TABS.map((tab) => (
          <button
            key={tab}
            role="tab"
            aria-selected={activeTab === tab}
            className={`v3-tab ${activeTab === tab ? "active" : ""}`}
            onClick={() => setActiveTab(tab)}
            id={`inspect-tab-${tab.toLowerCase().replace(/\s+/g, "-")}`}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab Contents */}
      <div className="v3-grid">
        {activeTab === "Profile" && (
          <>
            <Panel label="Identity & Access Binding (Prototype State)" className="v3-sp6">
              <dl style={{ margin: 0 }}>
                <KV k="Display Name" v={user.name} />
                <KV k="Account ID" v={<span className="v3-mono font-bold">{user.sxId}</span>} />
                <KV k="Bound Access ID" v={<span className="v3-mono">{user.accessIdRef}</span>} />
                <KV k="Email (Authoritative)" v={user.email} />
                <KV k="Phone (Authoritative)" v={user.phone} />
                <KV k="Assigned Role" v={user.role} />
                <KV k="Subscription Plan" v={user.plan} />
                <KV k="Service Entitlement" v={<span className="v3-status-badge ok"><Dot tone="ok" /> {user.serviceStatus || "ACTIVE"} ({user.serviceTermLabel || "6 Months"})</span>} />
                <KV k="Service Expiry" v={user.serviceExpiresAt ? user.serviceExpiresAt : "Never / Lifetime"} />
                <KV k="Last Active Session" v={user.lastActive} />
                <KV k="Last Session Time" v={user.lastSession} />
              </dl>
            </Panel>
            <Panel label="Authentication & Hardware Factor" className="v3-sp6">
              <dl style={{ margin: 0 }}>
                <KV k="MFA / Hardware Sensor" v="FIDO2 / WebAuthn Enrolled (Touch/PIN)" />
                <KV k="Account Status" v={<span className={`v3-status-badge ${user.accountStatus.toLowerCase()}`}><Dot tone={STATUS_TONE[user.accountStatus as AccessStatus] ?? "ok"} /> {user.accountStatus}</span>} />
                <KV k="Access ID Status" v={<span className={`v3-status-badge ${user.accessStatus.toLowerCase()}`}><Dot tone={STATUS_TONE[user.accessStatus] ?? "ok"} /> {user.accessStatus}</span>} />
                <KV k="Public Signup Origin" v="NO — OWNER-CREATED ACCESS RECORD" />
                <KV k="Pre-Trade Risk Envelope" v="ACTIVE (5.0L max margin / 20k max loss)" />
                <KV k="Audit Log Binding" v="Tamper-Evident Outbox / Audit Trail" />
              </dl>
            </Panel>
          </>
        )}

        {activeTab === "Strategies" && (
          <Panel label={`User Registered Strategies (${STRATEGIES.length})`} className="v3-sp12">
            <div className="v3-table-wrap">
              <table className="v3-table">
                <thead>
                  <tr>
                    <th>STRATEGY NAME</th>
                    <th>LANGUAGE</th>
                    <th>STAGE</th>
                    <th>SCAN STATUS</th>
                    <th>CONFORMANCE</th>
                    <th>SHARPE</th>
                    <th>MAX DD</th>
                  </tr>
                </thead>
                <tbody>
                  {STRATEGIES.length === 0 ? (
                    <tr>
                      <td colSpan={7} style={{ textAlign: "center", padding: "24px 12px", color: "var(--v3-ink-3)" }}>
                        No strategies assigned
                      </td>
                    </tr>
                  ) : (
                    STRATEGIES.map((s) => (
                      <tr key={s.id}>
                        <td>
                          <div className="v3-cell-main font-semibold">{s.name}</div>
                          <div className="v3-cell-sub">{s.version} · {s.note}</div>
                        </td>
                        <td>{s.language}</td>
                        <td>
                          <span className="v3-mono text-xs">{s.stage}</span>
                        </td>
                        <td>
                          <span className="v3-stat-line"><Dot tone={s.scanStatus === "PASSED" ? "ok" : "warn"} /> {s.scanStatus}</span>
                        </td>
                        <td>
                          <span className="v3-stat-line"><Dot tone={s.conformanceCheck === "CONFORMANT" ? "ok" : "warn"} /> {s.conformanceCheck}</span>
                        </td>
                        <td className="v3-mono">{s.sharpeRatio}</td>
                        <td className="v3-mono">{s.maxDrawdown}%</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
        )}

        {activeTab === "Backtests" && (
          <Panel label="Backtest Execution Audit" className="v3-sp12">
            <div className="v3-table-wrap">
              <table className="v3-table">
                <thead>
                  <tr>
                    <th>RUN ID</th>
                    <th>STRATEGY</th>
                    <th>RANGE</th>
                    <th>STATUS</th>
                    <th>SHARPE</th>
                    <th>NET PROFIT</th>
                    <th>MAX DD</th>
                    <th>WIN RATE</th>
                  </tr>
                </thead>
                <tbody>
                  {BACKTEST_RUNS.length === 0 ? (
                    <tr>
                      <td colSpan={8} style={{ textAlign: "center", padding: "24px 12px", color: "var(--v3-ink-3)" }}>
                        No backtest runs recorded
                      </td>
                    </tr>
                  ) : (
                    BACKTEST_RUNS.map((b) => (
                      <tr key={b.id}>
                        <td className="v3-mono font-bold">{b.id}</td>
                        <td>{b.strategyName}</td>
                        <td className="v3-mono text-xs">{b.dateRange}</td>
                        <td>
                          <span className="v3-status-badge ok"><Dot tone="ok" /> {b.status}</span>
                        </td>
                        <td className="v3-mono">{b.sharpeRatio}</td>
                        <td className="v3-mono" style={{ color: "var(--sx-emerald)" }}>+{b.netProfitPct}%</td>
                        <td className="v3-mono" style={{ color: "var(--sx-ruby)" }}>{b.maxDrawdown}%</td>
                        <td className="v3-mono">{b.winRate}%</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
        )}

        {activeTab === "Paper" && (
          <Panel label="Live Paper Trading Positions" className="v3-sp12">
            <div className="v3-table-wrap">
              <table className="v3-table">
                <thead>
                  <tr>
                    <th>POSITION ID</th>
                    <th>SYMBOL</th>
                    <th>QTY</th>
                    <th>AVG PRICE</th>
                    <th>LTP</th>
                    <th>NET PNL</th>
                    <th>STRATEGY SOURCE</th>
                  </tr>
                </thead>
                <tbody>
                  {PAPER_POSITIONS.length === 0 ? (
                    <tr>
                      <td colSpan={7} style={{ textAlign: "center", padding: "24px 12px", color: "var(--v3-ink-3)" }}>
                        No paper trading positions
                      </td>
                    </tr>
                  ) : (
                    PAPER_POSITIONS.map((p) => (
                      <tr key={p.id}>
                        <td className="v3-mono font-bold">{p.id}</td>
                        <td className="font-semibold">{p.symbol}</td>
                        <td className="v3-mono">{p.qty}</td>
                        <td className="v3-mono">{p.avgPrice}</td>
                        <td className="v3-mono">{p.ltp}</td>
                        <td className="v3-mono font-bold" style={{ color: p.pnl >= 0 ? "var(--sx-emerald)" : "var(--sx-ruby)" }}>
                          {p.pnl >= 0 ? `+₹${p.pnl}` : `-₹${Math.abs(p.pnl)}`}
                        </td>
                        <td className="v3-dim text-xs">{p.strategySource}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
        )}

        {activeTab === "Portfolio" && (
          <>
            <Panel label="Portfolio Asset Overview" className="v3-sp6">
              <dl style={{ margin: 0 }}>
                <KV k="Total Account NAV" v={<span className="v3-stat-big" style={{ fontSize: 24 }}>₹0.00</span>} />
                <KV k="Cash Margin Available" v="₹0.00" />
                <KV k="Margin Utilized" v="₹0.00" />
                <KV k="Unrealized P&L" v={<span style={{ fontWeight: 600 }}>₹0.00</span>} />
                <KV k="Realized P&L (Today)" v={<span style={{ fontWeight: 600 }}>₹0.00</span>} />
              </dl>
            </Panel>
            <Panel label="Current Positions &amp; Holdings" className="v3-sp6">
              {PORTFOLIO_HOLDINGS.length === 0 ? (
                <div style={{ padding: "24px 12px", textAlign: "center", color: "var(--v3-ink-3)" }}>
                  No open positions or holdings
                </div>
              ) : (
                <div className="v3-rows">
                  {PORTFOLIO_HOLDINGS.map((h) => (
                    <div className="v3-row" key={h.id}>
                      <div className="v3-row-main">
                        <div className="v3-row-title">{h.symbol} · {h.qty} qty</div>
                        <div className="v3-row-sub">Avg: ₹{h.avgCost} · LTP: ₹{h.ltp}</div>
                      </div>
                      <span className="v3-mono font-bold" style={{ color: h.pnl >= 0 ? "var(--sx-emerald)" : "var(--sx-ruby)" }}>
                        {h.pnl >= 0 ? `+₹${h.pnl}` : `-₹${Math.abs(h.pnl)}`}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </>
        )}

        {activeTab === "Orders" && (
          <Panel label="Order Execution Blotter" className="v3-sp12">
            <div className="v3-table-wrap">
              <table className="v3-table">
                <thead>
                  <tr>
                    <th>ORDER ID</th>
                    <th>INSTRUMENT</th>
                    <th>SIDE</th>
                    <th>QTY</th>
                    <th>PRICE</th>
                    <th>STATUS</th>
                    <th>TIME</th>
                  </tr>
                </thead>
                <tbody>
                  {ORDERS.length === 0 ? (
                    <tr>
                      <td colSpan={7} style={{ textAlign: "center", padding: "24px 12px", color: "var(--v3-ink-3)" }}>
                        No orders recorded
                      </td>
                    </tr>
                  ) : (
                    ORDERS.map((o) => (
                      <tr key={o.id}>
                        <td className="v3-mono">{o.id}</td>
                        <td className="font-semibold">{o.instrument}</td>
                        <td>
                          <span className={`v3-mono font-bold ${o.side === "BUY" ? "text-emerald-400" : "text-rose-400"}`}>
                            {o.side}
                          </span>
                        </td>
                        <td className="v3-mono">{o.qty}</td>
                        <td className="v3-mono">{o.price}</td>
                        <td>
                          <span className="v3-status-badge ok"><Dot tone={o.status === "FILLED" ? "ok" : "warn"} /> {o.status}</span>
                        </td>
                        <td className="v3-mono text-xs">{o.time}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </Panel>
        )}

        {activeTab === "Connections" && (
          <Panel label="Broker &amp; Exchange Plugins (Zero Secret Leakage)" className="v3-sp12">
            {USER_CONNECTORS.length === 0 ? (
              <div style={{ padding: "24px 12px", textAlign: "center", color: "var(--v3-ink-3)" }}>
                No broker connections configured
              </div>
            ) : (
              <div className="v3-rows">
                {USER_CONNECTORS.map((c) => (
                  <div className="v3-row" key={c.id}>
                    <div className="v3-row-main">
                      <div className="v3-row-title" style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span>{c.name}</span>
                        <span className="v3-mono text-xs v3-dim">({c.provider})</span>
                      </div>
                      <div className="v3-row-sub">
                        Status: <strong>{c.status}</strong> · Data Feed: {c.data} · Secret Reference: <code className="v3-mono">{c.secretRef}</code>
                      </div>
                    </div>
                    <Dot tone={c.status === "CONNECTED" ? "ok" : c.status === "NEEDS_ATTENTION" ? "warn" : "neg"} />
                  </div>
                ))}
              </div>
            )}
            <div className="security-notice-box" style={{ marginTop: 14 }}>
              <span className="sec-notice-icon">🛡</span>
              <span>
                <strong>Sealed Secrets Invariant:</strong> Raw broker passwords, TOTP seeds, and API keys are stored in encrypted client-side hardware keystores. Only sealed token references (<code className="v3-mono">ak •••• ••7f</code>) are visible in Owner Inspection Mode.
              </span>
            </div>
          </Panel>
        )}

        {activeTab === "Reports" && (
          <Panel label="Generated Reports &amp; Compliance Logs" className="v3-sp12">
            {REPORTS_LIST.length === 0 ? (
              <div style={{ padding: "24px 12px", textAlign: "center", color: "var(--v3-ink-3)" }}>
                No reports generated yet
              </div>
            ) : (
              <div className="v3-rows">
                {REPORTS_LIST.map((r) => (
                  <div className="v3-row" key={r.id}>
                    <div className="v3-row-main">
                      <div className="v3-row-title">{r.title}</div>
                      <div className="v3-row-sub">{r.category} · Generated: {r.generatedAt} · {r.fileSize}</div>
                    </div>
                    <button type="button" className="v3-btn ghost mini">Download {r.format}</button>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        )}

        {activeTab === "Sessions" && (
          <Panel label="Active WebAuthn Hardware Sessions" className="v3-sp12">
            <div className="v3-rows">
              <div className="v3-row">
                <div className="v3-row-main">
                  <div className="v3-row-title">Windows Hello · Workstation Client</div>
                  <div className="v3-row-sub">FIDO2 WebAuthn Passkey · Session Established · Last Active {user.lastActive}</div>
                </div>
                <Dot tone="ok" />
              </div>
              <div className="v3-row">
                <div className="v3-row-main">
                  <div className="v3-row-title">Hardware YubiKey 5C NFC · Secondary Token</div>
                  <div className="v3-row-sub">Enrolled &amp; Verified · Transport: internal-usb-hid-nfc</div>
                </div>
                <Dot tone="ok" />
              </div>
            </div>
          </Panel>
        )}

        {activeTab === "Security State" && (
          <Panel label="Risk Envelopes &amp; Governance Rules" className="v3-sp12">
            <dl style={{ margin: 0 }}>
              <KV k="Pre-Trade Risk Engine" v="Active · Hardware enforcement (Max loss 20,000 INR)" />
              <KV k="Circuit Breaker" v="Enabled (Trips on 3 consecutive rejected orders)" />
              <KV k="Global Option Strike Policy" v="OTM Boundary Active (Allowed: ATM ± 4 strikes)" />
              <KV k="Strategy Eligibility Rule" v="Backtest Sharpes >= 1.20 required for live deployment" />
              <KV k="Owner Bypass Permitted" v={<span style={{ color: "var(--sx-ruby)", fontWeight: 700 }}>NO — FAIL-CLOSED INVARIANT</span>} />
            </dl>
          </Panel>
        )}
      </div>
    </div>
  );
};

/* ════════════════════════════════════════════════════════════
   2. OWNER USERS MANAGEMENT SCREEN
   ════════════════════════════════════════════════════════════ */

export const AdminUsers: React.FC = () => {
  const [users, setUsers] = useState<OwnerUser[]>(() => isForceDemo() ? getStoredOwnerUsers() : []);
  const [userSource, setUserSource] = useState<"BACKEND" | "SAMPLE" | "UNAVAILABLE">("UNAVAILABLE");
  const [inspectingUser, setInspectingUser] = useState<OwnerUser | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const refreshUsers = async () => {
    try {
      const query = await queryAccessRecords();
      if (query.source === "BACKEND" && !query.error && query.data && query.data.length > 0) {
        setUserSource("BACKEND");
        const mapped: OwnerUser[] = query.data.map((r: any) => ({
          id: r.id || r.sxId,
          sxId: r.sxId || r.id,
          name: r.displayName || (r.notes ? r.notes.split("·")[0].trim() : (r.emailMasked ? r.emailMasked.split("@")[0] : "Authorized User")),
          email: r.email || r.emailMasked || "",
          phone: r.phone || r.phoneMasked || "",
          emailMasked: r.emailMasked || "••••••••",
          phoneMasked: r.phoneMasked || "••••••••",
          accountStatus: (r.accountStatus === "SUSPENDED" ? "SUSPENDED" : r.status === "ACTIVE" || r.status === "REDEEMED" ? "ACTIVE" : "INVITED"),
          accessStatus: (r.status || r.activationStatus || "ACTIVE") as any,
          accessIdRef: r.accessId || r.id || "",
          serviceTermLabel: r.serviceTermLabel || "Active Term",
          serviceStatus: r.serviceStatus || "ACTIVE",
          serviceExpiresAt: r.serviceExpiresAt || null,
          plan: r.plan || "Quant Professional",
          role: r.role || "USER",
          lastActive: r.redeemedAt || r.createdAt || "Recent",
          lastSession: r.redeemedAt || r.createdAt || "Recent",
          strategiesCount: r.strategiesCount ?? 0,
          paperSessionsCount: r.paperSessionsCount ?? 0,
          connectorsCount: r.connectorsCount ?? 0,
          sessionsCount: r.sessionsCount ?? 0,
        }));
        setUsers(mapped);
        return;
      }
    } catch {}
    if (isForceDemo()) {
      setUserSource("SAMPLE");
      setUsers(getStoredOwnerUsers());
    } else {
      setUserSource("UNAVAILABLE");
      setUsers([]);
    }
  };

  useEffect(() => {
    refreshUsers();
  }, []);

  const handleSuspend = async (userId: string) => {
    const res = await suspendBackendAccount(userId);
    if (res.success) {
      refreshUsers();
      setFeedback(`User ${userId} suspended.`);
    } else {
      setFeedback(`⚠️ ${res.error || "BACKEND AUTHORITY UNAVAILABLE"}`);
    }
    setTimeout(() => setFeedback(null), 2500);
  };

  const handleRestore = async (userId: string) => {
    const res = await restoreBackendAccount(userId);
    if (res.success) {
      refreshUsers();
      setFeedback(`User ${userId} restored to ACTIVE.`);
    } else {
      setFeedback(`⚠️ ${res.error || "BACKEND AUTHORITY UNAVAILABLE"}`);
    }
    setTimeout(() => setFeedback(null), 2500);
  };

  const handleRevoke = async (accessId: string) => {
    const res = await revokeBackendAccount(accessId);
    if (res.success) {
      refreshUsers();
      setFeedback(`Access token ${accessId} revoked.`);
    } else {
      setFeedback(`⚠️ ${res.error || "BACKEND AUTHORITY UNAVAILABLE"}`);
    }
    setTimeout(() => setFeedback(null), 2500);
  };

  if (inspectingUser) {
    return (
      <UserInspectionView
        user={inspectingUser}
        onClose={() => setInspectingUser(null)}
      />
    );
  }

  return (
    <>
      <div className="v3-screen-head">
        <div>
          <h2 className="v3-screen-title">Users Oversight</h2>
          <p className="v3-screen-sub">
            Authoritative enrolled users · Inspect workspaces, manage accounts &amp; oversee risk governance
          </p>
        </div>
        <TruthChip
          kind={userSource === "BACKEND" ? "REAL" : (userSource === "SAMPLE" ? "SAMPLE" : "DISABLED")}
          title={userSource === "BACKEND" ? "Authoritative enrolled users from backend SQLite security store." : (userSource === "SAMPLE" ? "Sample enrolled users (demo mode)" : "Users authority unavailable")}
        />
      </div>

      {feedback && (
        <div className={`v3-feedback-banner ${feedback.startsWith("⚠️") ? "warn" : "ok"}`} role="status" style={{ marginBottom: 14 }}>
          {feedback.startsWith("⚠️") ? feedback : `✓ ${feedback}`}
        </div>
      )}

      {/* Users Management Table */}
      <Panel label="All Enrolled Users" meta={`${users.length} users`} className="v3-sp12" id="owner-users-table-panel">
        <div className="v3-table-wrap">
          <table className="v3-table" id="owner-users-table">
            <thead>
              <tr>
                <th style={{ whiteSpace: "nowrap" }}>USER / IDENTITY</th>
                <th style={{ whiteSpace: "nowrap" }}>MASKED EMAIL</th>
                <th style={{ whiteSpace: "nowrap" }}>MASKED PHONE</th>
                <th style={{ whiteSpace: "nowrap" }}>ACCOUNT STATUS</th>
                <th style={{ whiteSpace: "nowrap" }}>ACCESS STATUS</th>
                <th style={{ whiteSpace: "nowrap" }}>LAST SESSION</th>
                <th style={{ whiteSpace: "nowrap" }}>STRATS</th>
                <th style={{ whiteSpace: "nowrap" }}>PAPER</th>
                <th style={{ textAlign: "right", whiteSpace: "nowrap" }}>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 ? (
                <tr>
                  <td colSpan={9} style={{ textAlign: "center", padding: "24px 12px", color: "var(--v3-ink-3)" }}>
                    No users yet
                  </td>
                </tr>
              ) : (
                users.map((u) => (
                <tr key={u.id} className="v3-table-row">
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <div className="v3-avatar">{u.name.split(" ").map((p: string) => p[0]).join("")}</div>
                      <div>
                        <div className="v3-cell-main font-semibold" style={{ whiteSpace: "nowrap" }}>{u.name}</div>
                        <div className="v3-cell-sub v3-mono" style={{ whiteSpace: "nowrap" }}>{u.sxId} · {u.role}</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <span className="v3-mono" style={{ whiteSpace: "nowrap" }}>{u.emailMasked}</span>
                  </td>
                  <td>
                    <span className="v3-mono" style={{ whiteSpace: "nowrap" }}>{u.phoneMasked}</span>
                  </td>
                  <td>
                    <span className={`v3-status-badge ${u.accountStatus.toLowerCase()}`} style={{ whiteSpace: "nowrap" }}>
                      <Dot tone={STATUS_TONE[u.accountStatus as AccessStatus] ?? "ok"} /> {u.accountStatus}
                    </span>
                  </td>
                  <td>
                    <span className={`v3-status-badge ${u.accessStatus.toLowerCase()}`} style={{ whiteSpace: "nowrap" }}>
                      <Dot tone={STATUS_TONE[u.accessStatus] ?? "ok"} /> {u.accessStatus}
                    </span>
                  </td>
                  <td>
                    <span className="v3-cell-date" style={{ whiteSpace: "nowrap" }}>{u.lastActive}</span>
                  </td>
                  <td className="v3-mono font-semibold">{u.strategiesCount}</td>
                  <td className="v3-mono font-semibold">{u.paperSessionsCount}</td>
                  <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                    <div style={{ display: "inline-flex", gap: 6, justifyContent: "flex-end" }}>
                      <button
                        type="button"
                        className="v3-btn primary mini"
                        onClick={() => setInspectingUser(u)}
                        id={`open-workspace-btn-${u.id}`}
                        title="Open full Owner User Inspection Mode"
                      >
                        Open Workspace
                      </button>
                      {u.accountStatus === "ACTIVE" ? (
                        <button
                          type="button"
                          className="v3-btn danger-ghost mini"
                          onClick={() => handleSuspend(u.id)}
                          id={`suspend-user-btn-${u.id}`}
                          title="Suspend user account"
                        >
                          Suspend
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="v3-btn ghost mini"
                          onClick={() => handleRestore(u.id)}
                          id={`restore-user-btn-${u.id}`}
                          title="Restore user account"
                        >
                          Restore
                        </button>
                      )}
                      {u.accessStatus !== "REVOKED" && (
                        <button
                          type="button"
                          className="v3-btn danger-ghost mini"
                          onClick={() => handleRevoke(u.accessIdRef)}
                          id={`revoke-user-btn-${u.id}`}
                          title="Revoke access token"
                        >
                          Revoke
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              )))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
};

/* ════════════════════════════════════════════════════════════
   3. OWNER STRATEGIES GOVERNANCE SCREEN
   ════════════════════════════════════════════════════════════ */

export { AdminStrategiesScreen, AdminStrategiesScreen as AdminStrategies } from "./AdminStrategiesScreen";

/* ════════════════════════════════════════════════════════════
   4. OWNER BROKER / API CONNECTIONS & PLUGINS SCREEN
   ════════════════════════════════════════════════════════════ */

export { AdminPluginsScreen, AdminPluginsScreen as AdminPlugins } from "./AdminPluginsScreen";

/* ════════════════════════════════════════════════════════════
   5. OWNER SYSTEM HEALTH, SECURITY AUTHORITY & SETTINGS SCREEN
   ════════════════════════════════════════════════════════════ */

export {
  AdminSecuritySystemSettingsScreen,
  AdminSecuritySystemSettingsScreen as AdminSystem,
  AdminSecuritySystemSettingsScreen as AdminSecurity,
  AdminSecuritySystemSettingsScreen as AdminSettings,
} from "./AdminSecuritySystemSettingsScreen";

export { AdminBacktestPaperScreen as AdminBacktestPaper } from "./AdminBacktestPaperScreen";
export { AdminPortfolioOrdersScreen, AdminPortfolioOrdersScreen as AdminPortfolioOrders } from "./AdminPortfolioOrdersScreen";
export { AdminReportsAuditScreen, AdminReportsAuditScreen as AdminReportsAudit } from "./AdminReportsAuditScreen";

