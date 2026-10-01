import React, { useEffect, useState } from "react";
import { loadAccountSurface, type AccountSurfaceData } from "../data/userSurfaceData";
import {
  AuthorityMessage,
  MetricCell,
  SurfacePanel,
  UserSurfaceHeader,
  displayScalar,
} from "../components/UserSurfacePrimitives";

export interface UserAccountProps {
  loadData?: () => Promise<AccountSurfaceData>;
}

export const UserAccount: React.FC<UserAccountProps> = ({ loadData = loadAccountSurface }) => {
  const [data, setData] = useState<AccountSurfaceData | null>(null);

  useEffect(() => {
    let active = true;
    setData(null);
    loadData().then((next) => { if (active) setData(next); }).catch(() => {
      if (active) setData({
        profile: { state: "UNAVAILABLE", data: null, asOf: null },
        connections: { state: "UNAVAILABLE", data: [], asOf: null },
      });
    });
    return () => { active = false; };
  }, [loadData]);

  const profile = data?.profile.state === "AVAILABLE" ? data.profile.data : null;
  const connections = data?.connections.state === "AVAILABLE" ? data.connections.data : [];

  return (
    <div className="af-user-surface" data-testid="account-surface">
      <UserSurfaceHeader
        eyebrow="Identity & Connectivity"
        title="Account"
        description="Authoritative account identity, service entitlement, workspace access, and broker-connection metadata. Secret material is never rendered here."
        aside={<div className="af-surface-lock"><span>Execution</span><strong>CONNECTION ≠ ARMED LIVE</strong></div>}
      />

      <div className="af-surface-two-col af-account-grid">
        <SurfacePanel eyebrow="Identity" title="User Profile" authority={data?.profile.state ?? "LOADING"}>
          {!data ? (
            <AuthorityMessage state="LOADING" title="User profile" unavailable="" />
          ) : data.profile.state !== "AVAILABLE" || !profile ? (
            <AuthorityMessage
              state={data.profile.state}
              title="User profile"
              unavailable="Authoritative profile is unavailable. No sample identity is shown."
              stale="User profile evidence is stale. Stale identity and entitlement values are withheld until fresh evidence is available."
              unknown="User profile authority trust is unknown. Identity and entitlement values are withheld."
            />
          ) : (
            <>
              <div className="af-account-identity">
                <div className="af-account-avatar">AF</div>
                <div>
                  <span>Authenticated user</span>
                  <h2>{profile.display_name}</h2>
                  <p>{displayScalar(profile.sx_id || profile.user_id)}</p>
                </div>
              </div>
              <div className="af-surface-metrics-grid compact">
                <MetricCell label="Role" value={displayScalar(profile.role)} />
                <MetricCell label="Lifecycle" value={displayScalar(profile.lifecycle)} />
                <MetricCell label="Account" value={displayScalar(profile.account_status)} />
                <MetricCell label="Activation" value={displayScalar(profile.activation_status)} />
                <MetricCell label="Service" value={displayScalar(profile.service_status)} />
                <MetricCell label="Effective access" value={displayScalar(profile.effective_access)} />
              </div>
            </>
          )}
        </SurfacePanel>

        <SurfacePanel eyebrow="Entitlement" title="Service & Workspace" authority={data?.profile.state ?? "LOADING"}>
          {!data || data.profile.state !== "AVAILABLE" || !profile ? (
            <AuthorityMessage
              state={data ? data.profile.state : "LOADING"}
              title="Service entitlement"
              unavailable="Service entitlement authority is unavailable."
              stale="Service entitlement evidence is stale. Expiry and workspace access are withheld until fresh evidence is available."
              unknown="Service entitlement authority trust is unknown. Access is not inferred from unknown evidence."
            />
          ) : (
            <div className="af-account-entitlement-list">
              <div><span>Service started</span><strong>{displayScalar(profile.service_started_at)}</strong></div>
              <div><span>Service expires</span><strong>{displayScalar(profile.service_expires_at)}</strong></div>
              <div><span>Service term</span><strong>{displayScalar(profile.service_term_type)}</strong></div>
              <div><span>User workspace</span><strong>{profile.workspace_eligibility ? displayScalar(profile.workspace_eligibility.user) : "—"}</strong></div>
              <div><span>Owner workspace</span><strong>{profile.workspace_eligibility ? displayScalar(profile.workspace_eligibility.owner) : "—"}</strong></div>
              <div><span>Namespace</span><strong>{displayScalar(profile.namespace)}</strong></div>
            </div>
          )}
        </SurfacePanel>
      </div>

      <SurfacePanel eyebrow="Broker Connectivity" title="Connections" authority={data?.connections.state ?? "LOADING"}>
        {!data ? (
          <AuthorityMessage state="LOADING" title="Connections" unavailable="" />
        ) : data.connections.state !== "AVAILABLE" ? (
          <AuthorityMessage
            state={data.connections.state}
            title="Connections"
            unavailable="Connection authority is unavailable. No broker connection is assumed."
            stale="Broker connection metadata is stale. Stale connectivity and capability records are withheld until fresh evidence is available."
            unknown="Broker connection authority trust is unknown. Connectivity and execution capability are not inferred."
          />
        ) : connections.length === 0 ? (
          <AuthorityMessage state="AVAILABLE" isEmpty title="Connections" unavailable="" empty="No authoritative broker connections are configured for this user." />
        ) : (
          <div className="af-account-connection-grid">
            {connections.map((connection) => (
              <article className="af-account-connection" key={connection.connectionId}>
                <div className="af-account-connection-head">
                  <div><span>{connection.provider}</span><strong>{connection.accountRef}</strong></div>
                  <span className="af-status-text">{connection.status}</span>
                </div>
                <div className="af-account-connection-facts">
                  <div><span>Health</span><strong>{displayScalar(connection.healthState)}</strong></div>
                  <div><span>Market data</span><strong>{displayScalar(connection.marketDataCapability)}</strong></div>
                  <div><span>Execution capability</span><strong>{displayScalar(connection.executionCapability)}</strong></div>
                  <div><span>Suspended</span><strong>{connection.suspended ? "YES" : "NO"}</strong></div>
                  <div><span>Last verified</span><strong>{displayScalar(connection.lastVerifiedAtUtc)}</strong></div>
                  <div><span>Connection ID</span><strong>{connection.connectionId}</strong></div>
                </div>
                {connection.suspendReason && <p className="af-account-connection-reason">{connection.suspendReason}</p>}
              </article>
            ))}
          </div>
        )}
        <p className="af-account-security-note">Connection metadata is read-only on this finished surface. Secret references, API secrets, and authentication material are never displayed. A connected broker does not arm Live execution.</p>
      </SurfacePanel>
    </div>
  );
};
