import { getSessionToken } from "../../shared/services/sessionStore";

export type PrivacyAuthorityState = "AVAILABLE" | "UNAVAILABLE";

export interface UserPrivacyDto {
  notice_policy_ref: string;
  notice_fingerprint: string;
  consent_state: string;
  request_statuses: [string, string][];
}

export interface UserPrivacySurfaceData {
  state: PrivacyAuthorityState;
  data: UserPrivacyDto | null;
  asOf: string | null;
}

export async function loadUserPrivacy(): Promise<UserPrivacySurfaceData> {
  const token = getSessionToken();
  if (!token) return { state: "UNAVAILABLE", data: null, asOf: null };
  try {
    const response = await fetch("/api/v1/product-ops/privacy/current", {
      headers: { authorization: `Bearer ${token}` },
    });
    if (!response.ok) return { state: "UNAVAILABLE", data: null, asOf: null };
    const data = await response.json() as UserPrivacyDto;
    return { state: "AVAILABLE", data, asOf: null };
  } catch {
    return { state: "UNAVAILABLE", data: null, asOf: null };
  }
}
