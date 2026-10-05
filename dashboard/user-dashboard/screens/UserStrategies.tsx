import React, { useEffect, useMemo, useState } from "react";
import {
  createUserDeployment,
  pauseUserDeployment,
  requestStrategyPromotion,
  resumeUserDeployment,
  stopUserDeployment,
  submitUserStrategy,
  type UserDeployment,
} from "../../shared/services/integrationClient";
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
  submitStrategyAction?: typeof submitUserStrategy;
  requestPromotionAction?: typeof requestStrategyPromotion;
  createDeploymentAction?: typeof createUserDeployment;
  pauseDeploymentAction?: typeof pauseUserDeployment;
  resumeDeploymentAction?: typeof resumeUserDeployment;
  stopDeploymentAction?: typeof stopUserDeployment;
}

interface DeploymentDraft {
  connectionId: string;
  instrument: string;
  timeframe: string;
  riskRef: string;
}

const readinessLabel = (gate: { ready: boolean; code: string; reason: string } | undefined, live = false) => {
  if (!gate) return { label: "UNKNOWN", detail: "Readiness authority unavailable." };
  if (gate.ready) return {
    label: live ? "ELIGIBLE · DISARMED" : "READY",
    detail: gate.reason || gate.code,
  };
  return { label: gate.code || "BLOCKED", detail: gate.reason || "Not eligible." };
};

const modeOf = (deployment: UserDeployment) => String(deployment.executionMode ?? deployment.execution_mode ?? "").toUpperCase();
const statusOf = (deployment: UserDeployment) => String(deployment.status || "").toUpperCase();
const terminalDeployment = (status: string) => ["STOPPED", "COMPLETED", "CANCELLED", "ARCHIVED"].includes(status);
const pauseableDeployment = (status: string) => ["DEPLOYED", "RUNNING", "ACTIVE"].includes(status);
const resumableDeployment = (status: string) => status === "PAUSED";

const controlGrid: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))",
  gap: 8,
};

export const UserStrategies: React.FC<UserStrategiesProps> = ({
  loadData = loadStrategiesSurface,
  submitStrategyAction = submitUserStrategy,
  requestPromotionAction = requestStrategyPromotion,
  createDeploymentAction = createUserDeployment,
  pauseDeploymentAction = pauseUserDeployment,
  resumeDeploymentAction = resumeUserDeployment,
  stopDeploymentAction = stopUserDeployment,
}) => {
  const [data, setData] = useState<StrategiesSurfaceData | null>(null);
  const [source, setSource] = useState("");
  const [protectivePolicy, setProtectivePolicy] = useState("");
  const [deploymentDrafts, setDeploymentDrafts] = useState<Record<string, DeploymentDraft>>({});
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

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

  const refreshAfterMutation = async (successMessage: string) => {
    setActionMessage(successMessage);
    try {
      const next = await loadData();
      setData(next);
    } catch {
      setActionMessage(`${successMessage} Refresh unavailable; previous evidence retained.`);
    }
  };

  const submitStrategy = async () => {
    if (data?.state !== "AVAILABLE" || pendingAction || !source.trim()) return;
    setPendingAction("strategy-submit");
    setActionMessage(null);
    try {
      const result = await submitStrategyAction(source, protectivePolicy.trim() || null);
      if (!result.success) {
        setActionMessage(result.error || "Strategy submission rejected by backend authority.");
        return;
      }
      setSource("");
      await refreshAfterMutation(`Strategy submitted${result.data?.strategy_id ? ` · ${result.data.strategy_id}` : ""}.`);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "Strategy submission failed.");
    } finally {
      setPendingAction(null);
    }
  };

  const requestPromotion = async (strategyId: string) => {
    if (data?.state !== "AVAILABLE" || pendingAction) return;
    setPendingAction(`promotion:${strategyId}`);
    setActionMessage(null);
    try {
      const result = await requestPromotionAction(strategyId, {
        target_stage: "PAPER_ELIGIBLE",
        notes: "User requested Paper eligibility from canonical Strategies surface",
      });
      if (!result.success) {
        setActionMessage(result.error || "Promotion request rejected by backend authority.");
        return;
      }
      await refreshAfterMutation(`Promotion request accepted · ${strategyId}.`);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "Promotion request failed.");
    } finally {
      setPendingAction(null);
    }
  };

  const draftFor = (strategyId: string): DeploymentDraft => deploymentDrafts[strategyId] ?? {
    connectionId: "",
    instrument: "NIFTY",
    timeframe: "5m",
    riskRef: "",
  };

  const updateDraft = (strategyId: string, patch: Partial<DeploymentDraft>) => {
    setDeploymentDrafts((current) => ({
      ...current,
      [strategyId]: { ...draftFor(strategyId), ...patch },
    }));
  };

  const createDeployment = async (strategyId: string, versionId: string) => {
    if (data?.state !== "AVAILABLE" || data.deploymentsState !== "AVAILABLE" || pendingAction) return;
    const draft = draftFor(strategyId);
    if (!draft.connectionId.trim() || !draft.instrument.trim()) return;
    setPendingAction(`deployment-create:${strategyId}`);
    setActionMessage(null);
    try {
      const result = await createDeploymentAction({
        strategy_id: strategyId,
        strategy_version_id: versionId,
        connection_id: draft.connectionId.trim(),
        instrument: draft.instrument.trim(),
        timeframe: draft.timeframe.trim() || undefined,
        execution_mode: "LIVE_PAPER",
        risk_ref: draft.riskRef.trim() || undefined,
      });
      if (!result.success) {
        setActionMessage(result.error || "LIVE_PAPER deployment rejected by backend authority.");
        return;
      }
      await refreshAfterMutation(`LIVE_PAPER deployment accepted · ${strategyId}.`);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "Deployment creation failed.");
    } finally {
      setPendingAction(null);
    }
  };

  const mutateDeployment = async (
    deploymentId: string,
    action: "pause" | "resume" | "stop",
  ) => {
    if (pendingAction) return;
    setPendingAction(`deployment-${action}:${deploymentId}`);
    setActionMessage(null);
    try {
      const fn = action === "pause" ? pauseDeploymentAction : action === "resume" ? resumeDeploymentAction : stopDeploymentAction;
      const result = await fn(deploymentId);
      if (!result.success) {
        setActionMessage(result.error || `Deployment ${action} rejected by backend authority.`);
        return;
      }
      await refreshAfterMutation(`Deployment ${action} accepted · ${deploymentId}.`);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : `Deployment ${action} failed.`);
    } finally {
      setPendingAction(null);
    }
  };

  return (
    <div className="af-user-surface" data-testid="strategies-surface">
      <UserSurfaceHeader
        eyebrow="Strategy Control Plane"
        title="Strategies"
        description="Authoritative strategy lifecycle, validation readiness, and LIVE_PAPER deployment controls. Real-money Live remains locked."
        aside={<div className="af-surface-lock"><span>LIVE</span><strong>READ_ONLY / DISARMED</strong></div>}
      />

      <section className="af-surface-metrics-grid">
        <MetricCell label="Registry" value={data ? data.state : "LOADING"} />
        <MetricCell label="Strategies" value={data?.state === "AVAILABLE" ? data.strategies.length : "—"} />
        <MetricCell label="Deployments" value={deploymentCount ?? "—"} />
        <MetricCell label="Deployment authority" value={data?.deploymentsState ?? "LOADING"} />
      </section>

      {actionMessage && <div className="af-surface-inline-note" role="status">{actionMessage}</div>}

      <SurfacePanel eyebrow="Strategy Submission" title="Submit Strategy" authority={data?.state ?? "LOADING"}>
        <p className="af-surface-inline-note">Submission goes to the governed backend registry. Validation or policy rejection is shown exactly; no local/sample success is created.</p>
        <textarea
          className="v3-input"
          aria-label="Strategy source"
          value={source}
          onChange={(event) => setSource(event.target.value)}
          placeholder="Strategy source"
          rows={8}
          style={{ width: "100%", resize: "vertical" }}
        />
        <input
          className="v3-input"
          aria-label="Protective policy identity"
          value={protectivePolicy}
          onChange={(event) => setProtectivePolicy(event.target.value)}
          placeholder="Protective policy identity (optional)"
          style={{ marginTop: 8 }}
        />
        <button
          type="button"
          className="v3-button"
          style={{ marginTop: 10 }}
          disabled={data?.state !== "AVAILABLE" || Boolean(pendingAction) || !source.trim()}
          onClick={() => { void submitStrategy(); }}
        >{pendingAction === "strategy-submit" ? "Submitting…" : "Submit Strategy"}</button>
        {data?.state !== "AVAILABLE" && <p className="af-surface-inline-note">Strategy submission is disabled until registry authority is AVAILABLE.</p>}
      </SurfacePanel>

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
            const draft = draftFor(entry.strategy_id);
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

                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
                  <button
                    type="button"
                    aria-label={`Request promotion ${entry.strategy_id}`}
                    disabled={Boolean(pendingAction)}
                    onClick={() => { void requestPromotion(entry.strategy_id); }}
                  >Request Promotion</button>
                </div>

                <div className="af-deployment-section">
                  <div className="af-surface-subhead">
                    <strong>LIVE_PAPER Deployment</strong>
                    <AuthorityBadge state={data.deploymentsState} />
                  </div>
                  <p className="af-surface-inline-note">Creation is hard-pinned to LIVE_PAPER. There is no real-Live execution-mode selector on this surface.</p>
                  <div style={controlGrid}>
                    <input className="v3-input" aria-label={`Deployment connection ID ${entry.strategy_id}`} value={draft.connectionId} onChange={(event) => updateDraft(entry.strategy_id, { connectionId: event.target.value })} placeholder="Connection ID" />
                    <input className="v3-input" aria-label={`Deployment instrument ${entry.strategy_id}`} value={draft.instrument} onChange={(event) => updateDraft(entry.strategy_id, { instrument: event.target.value })} placeholder="Instrument" />
                    <input className="v3-input" aria-label={`Deployment timeframe ${entry.strategy_id}`} value={draft.timeframe} onChange={(event) => updateDraft(entry.strategy_id, { timeframe: event.target.value })} placeholder="Timeframe" />
                    <input className="v3-input" aria-label={`Deployment risk ref ${entry.strategy_id}`} value={draft.riskRef} onChange={(event) => updateDraft(entry.strategy_id, { riskRef: event.target.value })} placeholder="Risk ref (optional)" />
                  </div>
                  <button
                    type="button"
                    aria-label={`Create LIVE_PAPER deployment ${entry.strategy_id}`}
                    style={{ marginTop: 8 }}
                    disabled={data.deploymentsState !== "AVAILABLE" || Boolean(pendingAction) || !draft.connectionId.trim() || !draft.instrument.trim()}
                    onClick={() => { void createDeployment(entry.strategy_id, entry.version_id); }}
                  >Create LIVE_PAPER Deployment</button>

                  {data.deploymentsState !== "AVAILABLE" ? (
                    <p className="af-surface-inline-note">Deployment authority is {data.deploymentsState}; deployment rows are withheld and no state is inferred.</p>
                  ) : deployments.length === 0 ? (
                    <p className="af-surface-inline-note">No authoritative deployments for this strategy.</p>
                  ) : (
                    <div className="af-deployment-list">
                      {deployments.map((deployment) => {
                        const mode = modeOf(deployment);
                        const status = statusOf(deployment);
                        const liveRecord = mode === "LIVE";
                        return (
                          <div className="af-deployment-row" key={deployment.deploymentId}>
                            <div><span>Deployment</span><strong>{deployment.deploymentId}</strong></div>
                            <div><span>Status</span><strong>{displayScalar(deployment.status)}</strong></div>
                            <div><span>Mode</span><strong>{displayScalar(deployment.executionMode ?? deployment.execution_mode)}</strong></div>
                            <div><span>Instrument</span><strong>{displayScalar(deployment.instrument)}</strong></div>
                            <div><span>Block</span><strong>{displayScalar(deployment.blockReason)}</strong></div>
                            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                              {!liveRecord && pauseableDeployment(status) && <button type="button" aria-label={`Pause deployment ${deployment.deploymentId}`} disabled={Boolean(pendingAction)} onClick={() => { void mutateDeployment(deployment.deploymentId, "pause"); }}>Pause</button>}
                              {!liveRecord && resumableDeployment(status) && <button type="button" aria-label={`Resume deployment ${deployment.deploymentId}`} disabled={Boolean(pendingAction)} onClick={() => { void mutateDeployment(deployment.deploymentId, "resume"); }}>Resume</button>}
                              {!terminalDeployment(status) && <button type="button" aria-label={`Stop deployment ${deployment.deploymentId}`} disabled={Boolean(pendingAction)} onClick={() => { void mutateDeployment(deployment.deploymentId, "stop"); }}>Stop</button>}
                              {liveRecord && <span className="af-surface-inline-note">LIVE record · no resume/pause authority</span>}
                            </div>
                          </div>
                        );
                      })}
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
