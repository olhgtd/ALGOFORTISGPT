import {
  getApiBaseUrl,
  isBackendEnabled,
  type MarketCandle,
  type MarketChartMode,
} from "../../shared/services/integrationClient";
import { getSessionToken } from "../../shared/services/sessionStore";

export type UserMarketChartState =
  | "LOADING"
  | "AVAILABLE"
  | "STALE"
  | "NO_DATA"
  | "DATA_PROVIDER_NOT_CONFIGURED"
  | "BACKEND_UNAVAILABLE"
  | "ERROR";

export interface UserMarketChartResult {
  state: UserMarketChartState;
  instrument: string;
  timeframe: string;
  mode: MarketChartMode;
  candles: MarketCandle[];
  detail?: string;
}

export interface UserMarketChartRequest {
  instrument: string;
  timeframe: string;
  mode: MarketChartMode;
  start_date?: string;
  end_date?: string;
  limit?: number;
}

const empty = (
  state: UserMarketChartState,
  request: Pick<UserMarketChartRequest, "instrument" | "timeframe" | "mode">,
  detail?: string,
): UserMarketChartResult => ({
  state,
  instrument: request.instrument,
  timeframe: request.timeframe,
  mode: request.mode,
  candles: [],
  ...(detail ? { detail } : {}),
});

export function parseUserMarketChartPayload(
  payload: any,
  request: Pick<UserMarketChartRequest, "instrument" | "timeframe" | "mode">,
): UserMarketChartResult {
  const rawState = String(payload?.candles?.state ?? "");
  const values: MarketCandle[] = Array.isArray(payload?.candles?.value) ? payload.candles.value : [];
  const instrument = typeof payload?.instrument === "string" && payload.instrument ? payload.instrument : request.instrument;
  const timeframe = typeof payload?.timeframe === "string" && payload.timeframe ? payload.timeframe : request.timeframe;

  if ((rawState === "AVAILABLE" || rawState === "STALE") && values.length > 0) {
    return {
      state: rawState,
      instrument,
      timeframe,
      mode: request.mode,
      candles: values,
      ...(rawState === "STALE" ? { detail: "Canonical market data is stale." } : {}),
    };
  }
  if (rawState === "DATA_PROVIDER_NOT_CONFIGURED") {
    return empty("DATA_PROVIDER_NOT_CONFIGURED", request);
  }
  if (rawState === "NO_DATA" || rawState === "DATA_INVALID" || values.length === 0) {
    return empty("NO_DATA", request, rawState === "DATA_INVALID" ? "Invalid canonical chart evidence." : undefined);
  }
  return empty("ERROR", request, rawState || "Unknown canonical chart state");
}

export async function queryUserMarketChart(params: UserMarketChartRequest): Promise<UserMarketChartResult> {
  if (!isBackendEnabled()) return empty("BACKEND_UNAVAILABLE", params, "Backend authority unavailable");

  const query = new URLSearchParams({ instrument: params.instrument, timeframe: params.timeframe, mode: params.mode });
  if (params.start_date) query.set("start_date", params.start_date);
  if (params.end_date) query.set("end_date", params.end_date);
  if (params.limit) query.set("limit", String(params.limit));

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 2500);
  try {
    const token = getSessionToken();
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await fetch(`${getApiBaseUrl()}/api/v1/market/chart?${query.toString()}`, {
      headers,
      signal: controller.signal,
    });
    if (!response.ok) return empty("BACKEND_UNAVAILABLE", params, `HTTP ${response.status}`);
    const payload = await response.json();
    return parseUserMarketChartPayload(payload, params);
  } catch {
    return empty("BACKEND_UNAVAILABLE", params, "Canonical market request failed");
  } finally {
    window.clearTimeout(timeout);
  }
}
