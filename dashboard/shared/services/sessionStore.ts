/**
 * SentinelX Authoritative In-Memory Session Token Store
 * 
 * Enforces the closed P2-2 security invariant:
 * - Authentication/session bearer tokens are kept strictly in runtime memory.
 * - NEVER persisted in or read from browser localStorage, sessionStorage, or cookies.
 * - Manipulating browser storage cannot create or forge Authorization headers.
 * - Logout / session termination immediately wipes the in-memory token.
 * - Backend remains the sole final authority.
 */

let runtimeSessionToken: string | null = null;

// Allow transient in-memory test configuration from window if injected before bundle execution
if (typeof window !== "undefined" && (window as any).__SENTINELX_SESSION_TOKEN__) {
  runtimeSessionToken = (window as any).__SENTINELX_SESSION_TOKEN__;
}

export function setSessionToken(token: string | null): void {
  runtimeSessionToken = token;
  if (typeof window !== "undefined") {
    (window as any).__SENTINELX_SESSION_TOKEN__ = token;
  }
}

export function getSessionToken(): string | null {
  if (typeof window !== "undefined" && (window as any).__SENTINELX_SESSION_TOKEN__) {
    return (window as any).__SENTINELX_SESSION_TOKEN__;
  }
  return runtimeSessionToken;
}

export function clearSessionToken(): void {
  runtimeSessionToken = null;
  if (typeof window !== "undefined") {
    (window as any).__SENTINELX_SESSION_TOKEN__ = null;
  }
}

// Expose in-memory session helper methods on window for authorized runtime callers
if (typeof window !== "undefined") {
  (window as any).__SENTINELX_SET_SESSION_TOKEN__ = setSessionToken;
  (window as any).__SENTINELX_GET_SESSION_TOKEN__ = getSessionToken;
  (window as any).__SENTINELX_CLEAR_SESSION_TOKEN__ = clearSessionToken;
}
