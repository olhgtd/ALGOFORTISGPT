import { getApiBaseUrl, isBackendEnabled } from "../../shared/services/integrationClient";
import { getSessionToken } from "../../shared/services/sessionStore";
import type { AuthorityState } from "../authority";

const TIMEOUT_MS = 10000;

export interface OwnerAuthoritySurface {
  authority_state: AuthorityState;
  source?: string;
  trust?: string;
  as_of_utc?: string;
  error?: string;
  [key: string]: unknown;
}

export interface OwnerAuthoritySnapshot {
  source: "BACKEND";
  trust: string;
  live_state: "READ_ONLY/DISARMED";
  broker_mutation: string;
  surfaces: {
    health: OwnerAuthoritySurface;
    access: OwnerAuthoritySurface;
    strategies: OwnerAuthoritySurface;
    connections: OwnerAuthoritySurface;
    datasets: OwnerAuthoritySurface;
    security: OwnerAuthoritySurface;
    ai: OwnerAuthoritySurface;
  };
  incidents: Array<Record<string, unknown>>;
}

function authHeaders(stepUpGrant?: string): Record<string, string> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getSessionToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (stepUpGrant) headers["X-AlgoFortis-Step-Up"] = stepUpGrant;
  return headers;
}

export async function ownerFetch<T>(
  path: string,
  options: RequestInit = {},
  stepUpGrant?: string,
): Promise<T> {
  if (!isBackendEnabled()) throw new Error("BACKEND_AUTHORITY_UNAVAILABLE");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...options,
      headers: { ...authHeaders(stepUpGrant), ...(options.headers || {}) },
      signal: controller.signal,
    });
    let payload: any = null;
    try { payload = await response.json(); } catch { payload = null; }
    if (!response.ok) {
      const detail = payload?.detail || payload?.error || `HTTP_${response.status}`;
      throw new Error(String(detail));
    }
    return payload as T;
  } finally {
    clearTimeout(timer);
  }
}

export async function queryOwnerAuthority(): Promise<OwnerAuthoritySnapshot> {
  return ownerFetch<OwnerAuthoritySnapshot>("/api/v1/owner/admin/authority");
}

export async function queryOwnerAI(): Promise<any> {
  return ownerFetch<any>("/api/v1/owner/admin/ai");
}

export async function queryOwnerIncidents(limit = 100): Promise<any> {
  return ownerFetch<any>(`/api/v1/owner/admin/incidents?limit=${Math.max(1, Math.min(limit, 500))}`);
}

export async function queryOwnerBacktests(): Promise<any> {
  return ownerFetch<any>("/api/v1/backtests?limit=200&offset=0");
}

export async function queryOwnerPaperSessions(): Promise<any> {
  return ownerFetch<any>("/api/v1/paper/sessions?limit=200&offset=0");
}

export async function queryOwnerOrdersPortfolio(mode: "PAPER" | "BACKTEST" | "LIVE" | "SHADOW" = "PAPER"): Promise<any> {
  return ownerFetch<any>(`/api/v1/owner/orders-portfolio?mode=${mode}`);
}

export async function queryOwnerReports(): Promise<any> {
  return ownerFetch<any>("/api/v1/owner/reports?limit=200&offset=0");
}

export async function queryOwnerAudit(): Promise<any> {
  return ownerFetch<any>("/api/v1/integration/audit/events?limit=200&offset=0");
}

export async function queryOwnerSessions(): Promise<any> {
  return ownerFetch<any>("/api/v1/owner/security/sessions");
}

export async function queryOwnerDevices(): Promise<any> {
  return ownerFetch<any>("/api/v1/owner/security/devices");
}

export async function queryServerSettings(): Promise<any> {
  return ownerFetch<any>("/api/v1/settings");
}

function base64Url(bytes: ArrayBuffer | null): string | null {
  if (!bytes) return null;
  const value = new Uint8Array(bytes);
  let binary = "";
  value.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function toArrayBuffer(value: string): ArrayBuffer {
  const padded = value.replaceAll("-", "+").replaceAll("_", "/") + "=".repeat((4 - (value.length % 4)) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0)).buffer;
}

async function obtainStepUpGrant(actionFamily: string, resourceRef?: string | null): Promise<string> {
  if (typeof window === "undefined" || !window.PublicKeyCredential) {
    throw new Error("WEBAUTHN_STEP_UP_UNAVAILABLE");
  }
  const issued = await ownerFetch<any>("/api/v1/owner/admin/step-up/options", {
    method: "POST",
    body: JSON.stringify({ action_family: actionFamily, resource_ref: resourceRef || null }),
  });
  const publicKey = issued.publicKey as PublicKeyCredentialRequestOptions;
  publicKey.challenge = toArrayBuffer(publicKey.challenge as unknown as string);
  publicKey.allowCredentials = publicKey.allowCredentials?.map((credential) => ({
    ...credential,
    id: toArrayBuffer(credential.id as unknown as string),
  }));
  const assertion = await navigator.credentials.get({ publicKey }) as PublicKeyCredential | null;
  if (!assertion) throw new Error("WEBAUTHN_STEP_UP_CANCELLED");
  const response = assertion.response as AuthenticatorAssertionResponse;
  const completed = await ownerFetch<any>("/api/v1/owner/admin/step-up/complete", {
    method: "POST",
    body: JSON.stringify({
      challenge_id: issued.challenge_id,
      action_family: actionFamily,
      resource_ref: resourceRef || null,
      response: {
        id: assertion.id,
        rawId: base64Url(assertion.rawId),
        type: assertion.type,
        response: {
          authenticatorData: base64Url(response.authenticatorData),
          clientDataJSON: base64Url(response.clientDataJSON),
          signature: base64Url(response.signature),
          userHandle: base64Url(response.userHandle),
        },
      },
    }),
  });
  if (!completed.step_up_grant) throw new Error("WEBAUTHN_STEP_UP_NOT_CONFIRMED");
  return String(completed.step_up_grant);
}

export async function ownerMutationWithStepUp<T>(args: {
  actionFamily: string;
  resourceRef?: string | null;
  path: string;
  method?: "POST" | "DELETE";
  body?: unknown;
}): Promise<T> {
  const grant = await obtainStepUpGrant(args.actionFamily, args.resourceRef);
  return ownerFetch<T>(args.path, {
    method: args.method || "POST",
    body: args.body === undefined ? undefined : JSON.stringify(args.body),
  }, grant);
}

export async function createOwnerAccess(payload: Record<string, unknown>): Promise<any> {
  return ownerMutationWithStepUp({
    actionFamily: "ACCOUNT_CREATE",
    path: "/api/v1/owner/access/users",
    body: payload,
  });
}

export async function ownerAccountAction(
  identifier: string,
  action: "suspend" | "restore" | "revoke" | "reissue-activation" | "revoke-activation" | "extend-service" | "renew-service" | "convert-lifetime",
  body: Record<string, unknown> = {},
): Promise<any> {
  const family: Record<typeof action, string> = {
    "suspend": "ACCOUNT_SUSPEND",
    "restore": "ACCOUNT_RESTORE",
    "revoke": "ACCOUNT_REVOKE",
    "reissue-activation": "ACTIVATION_REISSUE",
    "revoke-activation": "ACTIVATION_REVOKE",
    "extend-service": "ENTITLEMENT_CHANGE",
    "renew-service": "ENTITLEMENT_CHANGE",
    "convert-lifetime": "ENTITLEMENT_CHANGE",
  };
  return ownerMutationWithStepUp({
    actionFamily: family[action],
    resourceRef: identifier,
    path: `/api/v1/owner/access/users/${encodeURIComponent(identifier)}/${action}`,
    body,
  });
}

export async function ownerStrategyAction(
  strategyId: string,
  action: "allowance" | "visibility" | "suspend" | "restore" | "promote",
  body: Record<string, unknown>,
): Promise<any> {
  return ownerMutationWithStepUp({
    actionFamily: "STRATEGY_GOVERNANCE",
    resourceRef: strategyId,
    path: `/api/v1/owner/strategies/${encodeURIComponent(strategyId)}/${action}`,
    body,
  });
}

export async function configureAIProvider(providerId: string, body: Record<string, unknown>): Promise<any> {
  return ownerMutationWithStepUp({
    actionFamily: "AI_PROVIDER_CONFIG",
    resourceRef: providerId,
    path: `/api/v1/owner/admin/ai/providers/${encodeURIComponent(providerId)}`,
    body,
  });
}

export async function configureAIModel(modelId: string, body: Record<string, unknown>): Promise<any> {
  return ownerMutationWithStepUp({
    actionFamily: "AI_MODEL_CONFIG",
    resourceRef: modelId,
    path: `/api/v1/owner/admin/ai/models/${encodeURIComponent(modelId)}`,
    body,
  });
}

export async function bindAIAgent(agentId: string, body: Record<string, unknown>): Promise<any> {
  return ownerMutationWithStepUp({
    actionFamily: "AI_AGENT_POLICY",
    resourceRef: agentId,
    path: `/api/v1/owner/admin/ai/agents/${encodeURIComponent(agentId)}/binding`,
    body,
  });
}

export async function setAIAgentPolicy(agentId: string, enabled: boolean): Promise<any> {
  return ownerMutationWithStepUp({
    actionFamily: "AI_AGENT_POLICY",
    resourceRef: agentId,
    path: `/api/v1/owner/admin/ai/agents/${encodeURIComponent(agentId)}/policy`,
    body: { enabled },
  });
}

export async function createAIJob(body: Record<string, unknown>): Promise<any> {
  return ownerMutationWithStepUp({
    actionFamily: "AI_JOB_START",
    path: "/api/v1/owner/admin/ai/jobs",
    body,
  });
}

export async function cancelAIJob(jobId: string): Promise<any> {
  return ownerMutationWithStepUp({
    actionFamily: "AI_JOB_CONTROL",
    resourceRef: jobId,
    path: `/api/v1/owner/admin/ai/jobs/${encodeURIComponent(jobId)}/cancel`,
    body: {},
  });
}
