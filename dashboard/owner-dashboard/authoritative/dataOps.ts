import { ownerFetch, ownerMutationWithStepUp } from "./api";

export interface HistoricalProviderInput {
  provider_id: string;
  name: string;
  base_url?: string | null;
  api_key?: string | null;
  supported_instruments?: string[];
  supported_timeframes?: string[];
  is_enabled?: boolean;
  provider_type?: string | null;
  is_test?: boolean;
}

export interface HistoricalSyncInput {
  instrument: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  provider_id?: string | null;
  force_refresh?: boolean;
}

export interface HistoricalScheduleInput {
  instrument: string;
  timeframe: string;
  frequency: string;
  lookback_days: number;
  provider_id?: string | null;
  is_enabled: boolean;
}

export async function listHistoricalProviders(): Promise<any> {
  return ownerFetch<any>("/api/v1/owner/historical/providers");
}

export async function configureHistoricalProvider(input: HistoricalProviderInput): Promise<any> {
  return ownerMutationWithStepUp<any>({
    actionFamily: "HISTORICAL_PROVIDER_CONFIG",
    path: "/api/v1/owner/historical/providers",
    body: input,
  });
}

export async function toggleHistoricalProvider(providerId: string, enabled: boolean): Promise<any> {
  return ownerMutationWithStepUp<any>({
    actionFamily: "HISTORICAL_PROVIDER_CONFIG",
    resourceRef: providerId,
    path: `/api/v1/owner/historical/providers/${encodeURIComponent(providerId)}/toggle`,
    body: { enabled },
  });
}

export async function runHistoricalSync(input: HistoricalSyncInput): Promise<any> {
  return ownerFetch<any>("/api/v1/owner/historical/sync/manual", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function getHistoricalSchedule(instrument?: string, timeframe?: string): Promise<any> {
  const params = new URLSearchParams();
  if (instrument) params.set("instrument", instrument);
  if (timeframe) params.set("timeframe", timeframe);
  const qs = params.toString();
  return ownerFetch<any>(`/api/v1/owner/historical/sync/schedule${qs ? `?${qs}` : ""}`);
}

export async function configureHistoricalSchedule(input: HistoricalScheduleInput): Promise<any> {
  return ownerMutationWithStepUp<any>({
    actionFamily: "HISTORICAL_SYNC_POLICY",
    path: "/api/v1/owner/historical/sync/schedule",
    body: input,
  });
}

export async function listHistoricalSyncJobs(): Promise<any> {
  return ownerFetch<any>("/api/v1/owner/historical/sync/jobs?limit=100");
}

export async function getHistoricalSyncJob(jobId: string): Promise<any> {
  return ownerFetch<any>(`/api/v1/owner/historical/sync/jobs/${encodeURIComponent(jobId)}`);
}

export async function repairHistoricalGaps(body: Record<string, unknown>): Promise<any> {
  return ownerMutationWithStepUp<any>({
    actionFamily: "HISTORICAL_DATA_REPAIR",
    path: "/api/v1/owner/historical/gaps/repair",
    body,
  });
}
