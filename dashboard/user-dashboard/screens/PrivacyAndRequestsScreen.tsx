import React, { useEffect, useState } from "react";
import { AuthorityMessage, MetricCell, SurfacePanel } from "../components/UserSurfacePrimitives";
import { loadUserPrivacy, type UserPrivacySurfaceData } from "../data/privacy";

export interface PrivacyAndRequestsScreenProps {
  loadData?: () => Promise<UserPrivacySurfaceData>;
}

const unavailable: UserPrivacySurfaceData = { state: "UNAVAILABLE", data: null, asOf: null };

export const PrivacyAndRequestsScreen: React.FC<PrivacyAndRequestsScreenProps> = ({
  loadData = loadUserPrivacy,
}) => {
  const [surface, setSurface] = useState<UserPrivacySurfaceData | null>(null);

  useEffect(() => {
    let active = true;
    setSurface(null);
    loadData()
      .then((next) => { if (active) setSurface(next); })
      .catch(() => { if (active) setSurface(unavailable); });
    return () => { active = false; };
  }, [loadData]);

  const data = surface?.state === "AVAILABLE" ? surface.data : null;

  return (
    <div data-testid="privacy-requests-surface" className="af-privacy-requests">
      <SurfacePanel eyebrow="Privacy" title="Privacy & Requests" authority={surface?.state ?? "LOADING"}>
        {!surface ? (
          <AuthorityMessage state="LOADING" title="Privacy authority" unavailable="" />
        ) : surface.state !== "AVAILABLE" || !data ? (
          <AuthorityMessage
            state="UNAVAILABLE"
            title="Privacy authority"
            unavailable="Authoritative privacy notice, consent, and request status are unavailable. No consent or request outcome is inferred."
          />
        ) : (
          <>
            <div className="af-surface-metrics-grid compact">
              <MetricCell label="Notice" value={data.notice_policy_ref || "—"} />
              <MetricCell label="Consent" value={data.consent_state || "—"} />
            </div>
            <p className="af-account-security-note">Notice fingerprint: {data.notice_fingerprint || "—"}</p>
            <div className="af-account-entitlement-list">
              {data.request_statuses.length === 0 ? (
                <div><span>Requests</span><strong>NONE REPORTED BY AUTHORITY</strong></div>
              ) : data.request_statuses.map(([requestRef, status]) => (
                <div key={requestRef}><span>{requestRef}</span><strong>{status}</strong></div>
              ))}
            </div>
          </>
        )}
        <p className="af-account-security-note">This section is a privacy read model only. It does not expose broker credentials, trading state, or Live execution authority.</p>
      </SurfacePanel>
    </div>
  );
};
