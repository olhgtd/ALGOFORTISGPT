import { ownerFetch, ownerMutationWithStepUp } from "./api";

export interface OwnerBacktestRequest {
  strategy_id: string;
  version_id?: string | null;
  instrument: string;
  timeframe: string;
  initial_capital: number;
  date_range: string;
  dataset_id: string;
  policy?: Record<string, unknown> | null;
}

export interface OwnerWalkForwardRequest {
  strategy_id: string;
  version_id?: string | null;
  dataset_id?: string | null;
  instrument: string;
  timeframe: string;
  is_days: number;
  oos_days: number;
  max_windows: number;
  initial_capital: number;
  policy?: Record<string, unknown> | null;
}

export async function listOwnerBacktests(): Promise<any> {
  return ownerFetch<any>("/api/v1/owner/backtests?limit=200");
}

export async function runOwnerBacktest(input: OwnerBacktestRequest): Promise<any> {
  return ownerFetch<any>("/api/v1/backtests", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function cancelOwnerBacktest(runId: string): Promise<any> {
  return ownerMutationWithStepUp<any>({
    actionFamily: "BACKTEST_ADMIN",
    resourceRef: runId,
    path: `/api/v1/owner/backtests/${encodeURIComponent(runId)}/cancel`,
    body: {},
  });
}

export async function listOwnerWalkForwardJobs(): Promise<any> {
  return ownerFetch<any>("/api/v1/owner/walkforward/jobs?limit=200");
}

export async function createOwnerWalkForwardJob(input: OwnerWalkForwardRequest): Promise<any> {
  return ownerFetch<any>("/api/v1/walkforward/jobs", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function cancelOwnerWalkForwardJob(jobId: string): Promise<any> {
  return ownerMutationWithStepUp<any>({
    actionFamily: "WALKFORWARD_ADMIN",
    resourceRef: jobId,
    path: `/api/v1/owner/walkforward/jobs/${encodeURIComponent(jobId)}/cancel`,
    body: {},
  });
}
