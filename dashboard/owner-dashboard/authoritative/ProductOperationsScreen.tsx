import React, { useEffect, useState } from "react";
import { Panel, TruthChip } from "../../shared/utilities/V3Chrome";
import {
  loadOwnerProductOps,
  type OwnerProductOpsSurfaceData,
} from "../data/productOps";

export interface ProductOperationsScreenProps {
  loadData?: () => Promise<OwnerProductOpsSurfaceData>;
}

const unavailable: OwnerProductOpsSurfaceData = { state: "UNAVAILABLE", data: null, asOf: null };

export const ProductOperationsScreen: React.FC<ProductOperationsScreenProps> = ({
  loadData = loadOwnerProductOps,
}) => {
  const [surface, setSurface] = useState<OwnerProductOpsSurfaceData | null>(null);

  useEffect(() => {
    let active = true;
    setSurface(null);
    loadData()
      .then((next) => { if (active) setSurface(next); })
      .catch(() => { if (active) setSurface(unavailable); });
    return () => { active = false; };
  }, [loadData]);

  const data = surface?.state === "AVAILABLE" ? surface.data : null;
  const requestCounts = data?.privacy_requests ?? [];

  return (
    <section className="v3-page" data-testid="product-operations-surface">
      <div className="v3-page-head">
        <div>
          <div className="v3-eyebrow">PRODUCT & PRIVACY OPERATIONS</div>
          <h1>Product Operations</h1>
          <p>Read-only operational, privacy, backup and policy evidence. This surface has no trading or broker-mutation authority.</p>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
          <TruthChip kind={surface?.state === "AVAILABLE" ? "REAL" : "DISABLED"} title={surface?.state ?? "LOADING"} />
          <span className="v3-chip disabled">{data?.live_state ?? "READ_ONLY/DISARMED"}</span>
          <span className="v3-chip disabled">{data?.ai_authority ?? "RESEARCH_SHADOW_ONLY"}</span>
        </div>
      </div>

      {!surface && <Panel label="ProductOps authority"><p>LOADING</p></Panel>}
      {surface && surface.state !== "AVAILABLE" && (
        <Panel label="ProductOps authority">
          <p><strong>UNAVAILABLE</strong></p>
          <p>Authoritative Product Operations read model is unavailable. No zero, success status, policy, incident, or request status is inferred.</p>
        </Panel>
      )}

      {data && (
        <>
          <div className="v3-grid-4">
            <Panel label="Incidents"><strong>{data.unresolved_incidents}</strong><p>Unresolved operational/privacy incidents</p></Panel>
            <Panel label="Alert Health"><strong>{data.alert_health}</strong><p>Independent notification-channel health</p></Panel>
            <Panel label="Policy Health"><strong>{data.stale_policy_count}</strong><p>Missing/stale privacy policy count</p></Panel>
            <Panel label="Backup"><strong>{data.backup_status}</strong><p>Central privacy backup evidence</p></Panel>
          </div>

          <div className="v3-grid-2">
            <Panel label="Privacy Workflow">
              {requestCounts.length === 0 ? <p>No authoritative privacy workflow rows.</p> : (
                <div style={{ display: "grid", gap: 8 }}>
                  {requestCounts.map(([status, count]) => (
                    <div key={status} style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
                      <span>{status}</span><strong>{count}</strong>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
            <Panel label="Recovery & Runbooks">
              <div style={{ display: "grid", gap: 8 }}>
                <div><span>Restore</span> <strong>{data.restore_status}</strong></div>
                <div><span>Rollback</span> <strong>{data.rollback_status}</strong></div>
                <div><span>Runbooks</span> <strong>{data.runbook_status ?? "UNAVAILABLE"}</strong></div>
                <div><span>Live state</span> <strong>{data.live_state}</strong></div>
              </div>
            </Panel>
          </div>

          <Panel label="Active Privacy Policies">
            {data.active_policy_versions.length === 0
              ? <p>No authoritative active policy versions.</p>
              : <ul>{data.active_policy_versions.map((policy) => <li key={policy}>{policy}</li>)}</ul>}
          </Panel>
        </>
      )}
    </section>
  );
};
