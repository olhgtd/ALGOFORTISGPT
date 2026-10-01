import type { IntegrationSource, IntegrationTrust } from "../shared/services/integrationClient";

export type AuthorityState = "AVAILABLE" | "STALE" | "UNKNOWN" | "UNAVAILABLE";

export interface AuthorityEnvelope<T> {
  state: AuthorityState;
  source: IntegrationSource | string;
  trust: IntegrationTrust | string;
  asOf: string;
  data: T;
  reason?: string;
  evidenceRef?: string;
}

export function toAuthorityState(source: string, trust: string): AuthorityState {
  if (source === "UNAVAILABLE") return "UNAVAILABLE";
  if (source !== "BACKEND") return "UNKNOWN";
  if (trust === "FRESH") return "AVAILABLE";
  if (trust === "STALE") return "STALE";
  return "UNKNOWN";
}

export function toAuthorityEnvelope<T>(input: {
  source: IntegrationSource | string;
  trust: IntegrationTrust | string;
  asOf: string;
  data: T;
  error?: string;
}): AuthorityEnvelope<T> {
  return {
    state: toAuthorityState(input.source, input.trust),
    source: input.source,
    trust: input.trust,
    asOf: input.asOf,
    data: input.data,
    reason: input.error,
  };
}

/** Return a count only when the backing authority is explicitly AVAILABLE. */
export function authoritativeCount<T>(
  envelope: AuthorityEnvelope<T>,
  selector: (data: T) => number,
): number | null {
  return envelope.state === "AVAILABLE" ? selector(envelope.data) : null;
}

export function authorityDisplayValue(value: number | null): string {
  return value === null ? "—" : String(value);
}
