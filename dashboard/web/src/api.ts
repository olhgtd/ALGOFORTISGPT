/**
 * SentinelX Control Center – API Client
 *
 * Every request goes through authenticated session headers.
 * The client never fabricates evidence; it only deserializes
 * authoritative backend DTOs.
 */
import type {
  AuditEntry,
  ChartPayload,
  HealthPayload,
  OverviewPayload,
  PortfolioSummary,
  SecurityStatusPayload,
  SettingsProposal,
  StrategyArchiveResult,
  StrategyQualityResult,
  StrategyRegistryResponse,
  StrategySubmitResult,
} from "./contracts";
import {
  getSessionToken,
  setSessionToken,
  clearSessionToken,
} from "../../shared/services/sessionStore";

export { getSessionToken, setSessionToken, clearSessionToken };

const base = "/api/v1";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getSessionToken();
  const result = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  if (!result.ok) {
    let detail = `${result.status}`;
    try {
      const bodyText = await result.text();
      if (bodyText) detail = `${result.status} ${bodyText.slice(0, 400)}`;
    } catch {
      /* fail-closed: surface status code only */
    }
    throw new Error(`AlgoFortis request failed (${detail})`);
  }
  return result.json() as Promise<T>;
}

export interface AuthoritativeUserResponse {
  user_id: string;
  sx_id?: string;
  role: "OWNER" | "USER";
  lifecycle: string;
  account_status?: string;
  activation_status?: string;
  service_status?: string;
  service_started_at?: string | null;
  service_expires_at?: string | null;
  service_term_type?: string | null;
  custom_term_value?: number | null;
  display_name: string;
  namespace: string;
  workspace_eligibility?: {
    user: boolean;
    owner: boolean;
  };
  effective_access?: boolean;
}

export const api = {
  health: () => request<HealthPayload>("/health".replace("/api/v1", "")),
  currentUser: () => request<AuthoritativeUserResponse>("/users/current"),
  accessRecords: () => request<{ source: string; trust: string; as_of_utc: string; total_count: number; records: any[] }>("/integration/access/records"),
  overview: () => request<OverviewPayload>("/overview"),
  securityStatus: () => request<SecurityStatusPayload>("/security/status"),
  webauthnAuthenticationOptions: (identifier?: string) =>
    request<{ challenge_id: string; publicKey: PublicKeyCredentialRequestOptions }>(
      "/auth/webauthn/authentication/options",
      { method: "POST", body: JSON.stringify({ identifier: identifier?.trim() || undefined }) }
    ),
  webauthnAuthenticationComplete: (challenge_id: string, response: Record<string, unknown>) =>
    request<{ access_token: string; expires_at_utc: string; credential_id?: string; role: "OWNER" | "USER"; subject: string; sx_id: string }>(
      "/auth/webauthn/authentication/complete",
      { method: "POST", body: JSON.stringify({ challenge_id, response }) }
    ),
  webauthnRegistrationOptions: (rp_id: string) =>
    request<{ challenge_id: string; publicKey: PublicKeyCredentialCreationOptions }>(
      "/auth/webauthn/registration/options",
      { method: "POST", body: JSON.stringify({ rp_id }) }
    ),
  webauthnRegistrationComplete: (challenge_id: string, label: string, is_backup_hardware: boolean, response: Record<string, unknown>) =>
    request<{ credential_id: string; registered: boolean }>(
      "/auth/webauthn/registration/complete",
      { method: "POST", body: JSON.stringify({ challenge_id, label, is_backup_hardware, response }) }
    ),
  redeemUserActivation: (identifier: string, activation_code: string) =>
    request<{ challenge_id: string; publicKey: PublicKeyCredentialCreationOptions }>(
      "/auth/webauthn/activation/redeem", { method: "POST", body: JSON.stringify({ identifier, activation_code }) }),
  completeUserActivation: (challenge_id: string, label: string, response: Record<string, unknown>) =>
    request<{ registered: boolean; authentication_required: boolean }>(
      "/auth/webauthn/activation/complete", { method: "POST", body: JSON.stringify({ challenge_id, label, response }) }),
  bootstrapRegistrationOptions: (bootstrapToken: string) =>
    request<{ challenge_id: string; publicKey: PublicKeyCredentialCreationOptions }>(
      "/auth/webauthn/bootstrap-registration/options",
      { method: "POST", headers: { "x-sentinelx-bootstrap": bootstrapToken }, body: JSON.stringify({}) }
    ),
  bootstrapRegistrationComplete: (bootstrap_token: string, challenge_id: string, label: string, response: Record<string, unknown>) =>
    request<{ credential_id: string; registered: boolean; security_setup: string }>(
      "/auth/webauthn/bootstrap-registration/complete",
      { method: "POST", body: JSON.stringify({ bootstrap_token, challenge_id, label, is_backup_hardware: false, response }) }
    ),
  localOwnerSetup: (data: {
    display_name: string;
    email: string;
    bootstrap_token: string;
    password: string;
    confirm_password: string;
  }) =>
    request<{
      access_token: string;
      expires_at_utc: string;
      subject: string;
      role: "OWNER" | "USER";
      sx_id: string;
    }>("/auth/local/setup", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  localLogin: (data: { email: string; password: string }) =>
    request<{
      access_token: string;
      expires_at_utc: string;
      subject: string;
      role: "OWNER" | "USER";
      sx_id: string;
    }>("/auth/local/login", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  chart: (instrument: string, timeframe: string, mode: string, opts?: { start_date?: string; end_date?: string; limit?: number }) => {
    const params = new URLSearchParams({ instrument, timeframe, mode });
    if (opts?.start_date) params.set("start_date", opts.start_date);
    if (opts?.end_date) params.set("end_date", opts.end_date);
    if (opts?.limit) params.set("limit", String(opts.limit));
    return request<ChartPayload>(`/market/chart?${params.toString()}`);
  },
  timeframes: (instrument: string, mode: string) =>
    request<{ timeframes: string[] }>(
      `/market/timeframes?instrument=${encodeURIComponent(instrument)}&mode=${mode}`
    ),
  quality: (versionId: string) =>
    request<StrategyQualityResult>(`/strategies/${encodeURIComponent(versionId)}/quality`),
  strategiesRegistry: () =>
    request<StrategyRegistryResponse>("/strategies"),
  submitStrategy: (source: string, protective_policy_identity: string | null) =>
    request<StrategySubmitResult>("/strategies", {
      method: "POST",
      body: JSON.stringify({ source, protective_policy_identity }),
    }),
  archiveStrategy: (versionId: string) =>
    request<StrategyArchiveResult>(
      `/strategies/${encodeURIComponent(versionId)}/archive`,
      { method: "POST", body: JSON.stringify({}) }
    ),
  portfolio: () => request<PortfolioSummary>("/portfolio"),
  audit: () => request<{ entries: AuditEntry[] }>("/audit/events"),
  settingsProposal: (proposal: SettingsProposal) =>
    request<{ accepted: boolean; diff: string }>(
      "/settings/propose",
      { method: "POST", body: JSON.stringify(proposal) }
    ),
  safeMode: (enabled: boolean) =>
    request<{ enabled: boolean }>(
      "/settings/safe-mode",
      { method: "POST", body: JSON.stringify({ enabled }) }
    ),
  revokeSession: () =>
    request<{ revoked: boolean }>("/security/sessions/revoke", { method: "POST" }),
};
