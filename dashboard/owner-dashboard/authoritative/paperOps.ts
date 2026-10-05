import { ownerFetch, ownerMutationWithStepUp } from "./api";

export interface OwnerPaperCreateRequest {
  strategy_id: string;
  instrument: string;
  timeframe: string;
  initial_capital: number;
  data_source_mode: string;
  date_range?: string | null;
  dataset_id?: string | null;
  policy?: Record<string, unknown> | null;
}

export async function listOwnerPaperSessions(): Promise<any> {
  return ownerFetch<any>("/api/v1/owner/paper/sessions?limit=200");
}

export async function createOwnerPaperSession(input: OwnerPaperCreateRequest): Promise<any> {
  return ownerFetch<any>("/api/v1/paper/sessions", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function startOwnerPaperSession(sessionId: string): Promise<any> {
  return ownerFetch<any>(`/api/v1/paper/sessions/${encodeURIComponent(sessionId)}/start`, { method: "POST" });
}

export async function stopOwnerPaperSession(sessionId: string): Promise<any> {
  return ownerFetch<any>(`/api/v1/paper/sessions/${encodeURIComponent(sessionId)}/stop`, { method: "POST" });
}

export async function getOwnerPaperPositions(sessionId: string): Promise<any> {
  return ownerFetch<any>(`/api/v1/paper/sessions/${encodeURIComponent(sessionId)}/positions`);
}

export async function getOwnerPaperOrders(sessionId: string): Promise<any> {
  return ownerFetch<any>(`/api/v1/paper/sessions/${encodeURIComponent(sessionId)}/orders`);
}

export async function getOwnerPaperEvents(sessionId: string): Promise<any> {
  return ownerFetch<any>(`/api/v1/paper/sessions/${encodeURIComponent(sessionId)}/events`);
}

export async function engageOwnerPaperHold(sessionId: string, reason: string): Promise<any> {
  return ownerFetch<any>(`/api/v1/owner/paper/sessions/${encodeURIComponent(sessionId)}/hold`, {
    method: "POST",
    body: JSON.stringify({ hold: true, reason }),
  });
}

export async function releaseOwnerPaperHold(sessionId: string, reason: string): Promise<any> {
  return ownerMutationWithStepUp<any>({
    actionFamily: "PAPER_HOLD_RELEASE",
    resourceRef: sessionId,
    path: `/api/v1/owner/paper/sessions/${encodeURIComponent(sessionId)}/release-hold`,
    body: { notes: reason },
  });
}
