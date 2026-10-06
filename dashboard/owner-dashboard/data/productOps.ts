import { getSessionToken } from "../../shared/services/sessionStore";

export type ProductOpsAuthorityState = "AVAILABLE" | "UNAVAILABLE";

export interface ProductOpsHealthDto {
  unresolved_incidents: number;
  alert_health: string;
  privacy_requests: [string, number][];
  stale_policy_count: number;
  backup_status: string;
  restore_status: string;
  rollback_status: string;
  active_policy_versions: string[];
  runbook_status?: string | null;
  live_state: "READ_ONLY/DISARMED";
  ai_authority: "INDEPENDENT_CANDIDATE_SOURCE";
}

export interface OwnerProductOpsSurfaceData {
  state: ProductOpsAuthorityState;
  data: ProductOpsHealthDto | null;
  asOf: string | null;
}

export async function loadOwnerProductOps(): Promise<OwnerProductOpsSurfaceData> {
  const token = getSessionToken();
  if (!token) return { state: "UNAVAILABLE", data: null, asOf: null };
  try {
    const response = await fetch("/api/v1/product-ops/owner/health", {
      headers: { authorization: `Bearer ${token}` },
    });
    if (!response.ok) return { state: "UNAVAILABLE", data: null, asOf: null };
    const data = await response.json() as ProductOpsHealthDto;
    return { state: "AVAILABLE", data, asOf: null };
  } catch {
    return { state: "UNAVAILABLE", data: null, asOf: null };
  }
}
