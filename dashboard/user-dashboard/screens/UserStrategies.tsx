import React, { useEffect, useMemo, useState } from "react";
import { loadStrategiesSurface, type StrategiesSurfaceData } from "../data/userSurfaceData";
import {
  AuthorityBadge,
  AuthorityMessage,
  MetricCell,
  SurfacePanel,
  UserSurfaceHeader,
  displayScalar,
} from "../components/UserSurfacePrimitives";

export interface UserStrategiesProps {
  loadData?: () => Promise<StrategiesSurfaceData>;
}

const readinessLabel = (gate: { ready: boolean; code: string; reason: string } | undefined, live = false) => {
  if (!gate) return { label: "UNKNOWN", detail: "Readiness authority unavailable." };
  if (gate.ready) return {
    label: live ? "ELIGIBLE · DISARMED" : "READY",
    detail: gate.reason || gate.code,
  };
  return { label: gate.code || "BLOCKED", detail: gate.reason || "Not eligible." };
};

export const UserStrategies: React.FC<UserStrategiesProps> = ({ loadData = loadStrategiesSurface }) => {
  const [data, setData] = useState<StrategiesSurfaceData | null>(null);

  useEffect(() => {
    let active = true;
    setData(null);
    loadData().then((next) => { if (active) setData(next); }).catch(() => {
      if (active) setData({ state: "UNAVAILABLE", strategies: [], deploymentsState: "UNAVAILABLE", asOf: null });
    });
    return () => { active = false; };
  }, [loadData]);

  const deploymentCount = useMemo(
    () => data?.deploymentsState === "AVAILABLE"
      ? data.strategies.reduce((sum, item) => sum + item.deployments.length, 0)
      : null,
    [data],
  );

  return (
    <div className="af-user-surface" data-testid="strategies-surface">
      <UserSurfaceHeader
        eyebrow="Strategy Control Plane"
        title="Strategies"
        description="Authoritative strategy lifecycle, validation readiness, and deployment visibility. This surface does not arm Live execution."
        aside={<div className="af-surface-lock"><span>LIVE</span><strong>READ_ONLY / DISARMED</strong></div>}
      />

      <section className="af-surface-metrics-grid">
        <MetricCell label="Registry" value={data ? data.state : "LOADING"} />
        <MetricCell label="Strategies" value={data?.state === "AVAILABLE" ? data.strategies.length : "—"} />
        <MetricCell label="Deployments" value={deploymentCount ?? "—"} />
        <MetricCell label="Deployment authority" value={data?.deploymentsState ?? "LOADING"} />
      </section>

      {!data ? (
        <AuthorityMessage state="LOADING" title="Strategy registry" unavailable="" />
      ) : data.state !== "AVAILABLE" ? (
        <AuthorityMessage
          state={data.state}
          title="Strategy registry"
          unavailable="Authoritative strategy registry is unavailable. No sample strategies are shown."
          stale="Strategy registry evidence is stale. Strategy rows and readiness are withheld until fresh backend evidence is available."
          unknown="Strategy registry trust is unknown. No lifecycle or eligibility state is inferred."
        />
      ) : data.strategies.length === 0 ? (
        <AuthorityMessage state="AVAILABLE" isEmpty title="Strategy registry" unavailable="" empty="No authoritative strategies are registered for this user." />
      ) : (
        <div className="af-strategy-list">
          {data.strategies.map(({ entry, readiness, deployments }) => {
            const gates = [
              ["Backtest", readinessLabel(readiness?.backtest)],
              ["Paper", readinessLabel(readiness?.paper)],
              ["Live Paper", readinessLabel(readiness?.livePaper)],
              ["Live", readinessLabel(readiness?.live, true)],
            ] as const;
            return (
              <SurfacePanel key={`${entry.strategy_id}-${entry.version_id}`} eyebrow="Registered Strategy" title={entry.strategy_id} authority="AVAILABLE" className="af-strategy-card">
                <div className="af-strategy-meta-grid">
                  <MetricCell label="Version" value={displayScalar(entry.version_id)} />
                  <MetricCell label="Stage" value={displayScalar(entry.stage)} />
                  <MetricCell label="Visibility" value={displayScalar(entry.visibility)} />
                  <MetricCell label="Admin status" value={displayScalar(entry.admin_status)} />
                  <MetricCell label="Protective policy" value={displayScalar(entry.protective_policy)} />
                  <MetricCell label="Archived" value={entry.archived ? "YES" : "NO"} />
                </div>

                <div className="af-readiness-grid" aria-label={`${entry.strategy_id} readiness`}>
                  {gates.map(([label, gate]) => (
                    <div className="af-readiness-cell" key={label}>
                      <span>{label}</span>
                      <strong>{gate.label}</strong>
                      <small>{gate.detail}</small>
                    </div>
                  ))}
                </div>

                <div className="af-deployment-section">
                  <div className="af-surface-subhead">
                    <strong>Deployments</strong>
                    <AuthorityBadge state={data.deploymentsState} />
                  </div>
                  {data.deploymentsState !== "AVAILABLE" ? (
                    <p className="af-surface-inline-note">Deployment authority is {data.deploymentsState}; deployment rows are withheld and no state is inferred.</p>
                  ) : deployments.length === 0 ? (
                    <p className="af-surface-inline-note">No authoritative deployments for this strategy.</p>
                  ) : (
                    <div className="af-deployment-list">
                      {deployments.map((deployment) => (
                        <div className="af-deployment-row" key={deployment.deploymentId}>
                          <div><span>Deployment</span><strong>{deployment.deploymentId}</strong></div>
                          <div><span>Status</span><strong>{displayScalar(deployment.status)}</strong></div>
                          <div><span>Mode</span><strong>{displayScalar(deployment.executionMode ?? deployment.execution_mode)}</strong></div>
                          <div><span>Instrument</span><strong>{displayScalar(deployment.instrument)}</strong></div>
                          <div><span>Block</span><strong>{displayScalar(deployment.blockReason)}</strong></div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </SurfacePanel>
            );
          })}
        </div>
      )}
    </div>
  );
};
