import { ownerFetch, ownerMutationWithStepUp } from "./api";

export interface OwnerDeploymentCreateRequest {
  strategy_id: string;
  strategy_version_id?: string | null;
  connection_id?: string | null;
  instrument: string;
  timeframe: string;
  risk_ref?: string | null;
}

export async function listOwnerDeployments(): Promise<any> {
  return ownerFetch<any>("/api/v1/owner/deployments?limit=200");
}

export async function createOwnerDeployment(input: OwnerDeploymentCreateRequest): Promise<any> {
  return ownerFetch<any>("/api/v1/user/deployments", {
    method: "POST",
    body: JSON.stringify({ ...input, execution_mode: "LIVE_PAPER" }),
  });
}

export async function pauseOwnerDeployment(deploymentId: string): Promise<any> {
  return ownerFetch<any>(`/api/v1/owner/deployments/${encodeURIComponent(deploymentId)}/pause`, { method: "POST" });
}

export async function resumeOwnerDeployment(deploymentId: string): Promise<any> {
  return ownerMutationWithStepUp<any>({
    actionFamily: "DEPLOYMENT_CONTROL",
    resourceRef: deploymentId,
    path: `/api/v1/owner/deployments/${encodeURIComponent(deploymentId)}/resume`,
    body: {},
  });
}

export async function stopOwnerDeployment(deploymentId: string): Promise<any> {
  return ownerMutationWithStepUp<any>({
    actionFamily: "DEPLOYMENT_CONTROL",
    resourceRef: deploymentId,
    path: `/api/v1/owner/deployments/${encodeURIComponent(deploymentId)}/stop`,
    body: {},
  });
}

export async function getOwnerDeploymentRecovery(): Promise<any> {
  return ownerFetch<any>("/api/v1/owner/deployments/recovery");
}
