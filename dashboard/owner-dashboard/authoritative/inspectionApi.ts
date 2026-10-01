import { ownerFetch } from "./api";

export type InspectionTabName =
  | "Profile"
  | "Strategies"
  | "Backtests"
  | "Paper"
  | "Portfolio"
  | "Orders"
  | "Connections"
  | "Reports"
  | "Sessions"
  | "Security State";

export interface InspectionSurface {
  authority_state: "AVAILABLE" | "STALE" | "UNKNOWN" | "UNAVAILABLE";
  source: string;
  trust: string;
  as_of_utc: string;
  data: unknown;
  error?: string;
}

export interface OwnerUserInspectionSnapshot {
  source: "BACKEND";
  trust: string;
  as_of_utc: string;
  user_id: string;
  sx_id?: string | null;
  live_state: "READ_ONLY/DISARMED";
  tabs: Record<InspectionTabName, InspectionSurface>;
}

export async function queryOwnerUserInspection(identifier: string): Promise<OwnerUserInspectionSnapshot> {
  return ownerFetch<OwnerUserInspectionSnapshot>(
    `/api/v1/owner/admin/users/${encodeURIComponent(identifier)}/inspection`,
  );
}
