import { ownerFetch, ownerMutationWithStepUp } from "./api";

export async function ownerConnectionAllowance(connectionId: string, allowance: "ALLOWED" | "HOLD" | "REVOKED", reason?: string) {
  return ownerMutationWithStepUp<any>({
    actionFamily: "CONNECTION_GOVERNANCE",
    resourceRef: connectionId,
    path: `/api/v1/owner/connections/${encodeURIComponent(connectionId)}/allowance`,
    body: { allowance, reason },
  });
}

export async function ownerCapabilityAllowance(
  connectionId: string,
  capability: string,
  allowance: "ALLOWED" | "HOLD" | "REVOKED",
  reason?: string,
) {
  return ownerMutationWithStepUp<any>({
    actionFamily: "CONNECTION_GOVERNANCE",
    resourceRef: connectionId,
    path: `/api/v1/owner/connections/${encodeURIComponent(connectionId)}/capabilities/${encodeURIComponent(capability)}/allowance`,
    body: { allowance, reason },
  });
}

export async function ownerDatasetApproval(datasetId: string, approval: "APPROVED" | "HOLD" | "REJECTED", reason?: string) {
  return ownerMutationWithStepUp<any>({
    actionFamily: "DATASET_GOVERNANCE",
    resourceRef: datasetId,
    path: `/api/v1/owner/datasets/${encodeURIComponent(datasetId)}/approval`,
    body: { approval, reason },
  });
}

export async function revokeOwnerSession(sessionRef: string) {
  return ownerMutationWithStepUp<any>({
    actionFamily: "SESSION_REVOKE",
    resourceRef: sessionRef,
    path: `/api/v1/owner/security/sessions/${encodeURIComponent(sessionRef)}/revoke`,
    body: {},
  });
}

export async function revokeAllOwnerUserSessions(identifier: string) {
  return ownerMutationWithStepUp<any>({
    actionFamily: "SESSION_REVOKE_ALL",
    resourceRef: identifier,
    path: `/api/v1/owner/security/users/${encodeURIComponent(identifier)}/sessions/revoke-all`,
    body: {},
  });
}

export async function revokeOwnerDevice(credentialId: string) {
  return ownerMutationWithStepUp<any>({
    actionFamily: "DEVICE_REVOKE",
    resourceRef: credentialId,
    path: `/api/v1/owner/security/devices/${encodeURIComponent(credentialId)}/revoke`,
    body: {},
  });
}

export async function revokeAllOwnerUserDevices(identifier: string) {
  return ownerMutationWithStepUp<any>({
    actionFamily: "DEVICE_REVOKE_ALL",
    resourceRef: identifier,
    path: `/api/v1/owner/security/users/${encodeURIComponent(identifier)}/devices/revoke-all`,
    body: {},
  });
}

export async function proposeOwnerSetting(key: string, proposedValue: unknown) {
  return ownerFetch<any>("/api/v1/settings/propose", {
    method: "POST",
    body: JSON.stringify({ key, proposed_value: proposedValue }),
  });
}

export async function confirmOwnerSetting(proposalId: string) {
  return ownerMutationWithStepUp<any>({
    actionFamily: "SETTINGS_APPLY",
    path: "/api/v1/settings/confirm",
    body: { proposal_id: proposalId },
  });
}
