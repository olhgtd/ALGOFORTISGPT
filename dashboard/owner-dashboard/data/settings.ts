/**
 * AlgoFortis Dashboard V3 — System Health Subsystems, Rate Limits & Settings Domain
 */
import type { Truth } from "../../shared/data/sharedTypes";
import { STORAGE_KEYS, prototypeFixtureStorage, safeGetJson, safeSetJson } from "../../shared/data/storage";

const localStorage = prototypeFixtureStorage;

export interface RateLimitPolicyItem {
  id: string;
  flowName: string;
  targetEndpoint: string;
  failureThreshold: string;
  escalationCooldown: string;
  isolationGuarantee: string;
  policyStatus: "FROZEN_V1_POLICY" | "TECHNICAL_PARAM_DEFERRED";
  isFrozen: boolean;
}

export interface SystemHealthSubsystem {
  id: string;
  name: string;
  category: "APPLICATION" | "INTEGRATION" | "PERSISTENCE" | "AUDIT" | "RISK_ENGINE" | "DATA_STREAM";
  status: "OPERATIONAL" | "DEGRADED" | "NOT_CONNECTED" | "PROTOTYPE_PROJECTION" | "FAIL_CLOSED";
  tone: "ok" | "warn" | "neg" | "dim" | "live";
  currentStatusLabel: string;
  targetArchitecture: string;
  detail: string;
  lastTelemetry: string;
  evidenceRef?: string;
}

export interface OwnerSettingsState {
  defaultLandingView: "overview" | "users" | "system" | "security";
  uiDensity: "comfortable" | "compact";
  uiInactivityWarning: "15m" | "30m" | "60m" | "disabled"; // Labeled: UI INACTIVITY WARNING ONLY — NOT an authentication/session timeout
  audioChimeOnCriticalAlert: boolean;
  clockFormat: "UTC" | "LOCAL_WALLCLOCK";
}

const OWNER_SESSIONS_KEY = STORAGE_KEYS.OWNER_SESSIONS;
const OWNER_DEVICES_KEY = STORAGE_KEYS.OWNER_DEVICES;
const OWNER_SETTINGS_KEY = STORAGE_KEYS.OWNER_SETTINGS;


export const INITIAL_RATE_LIMIT_POLICIES: RateLimitPolicyItem[] = [
  {
    id: "rl-01",
    flowName: "Password Login",
    targetEndpoint: "/api/v1/auth/password",
    failureThreshold: "5 failed attempts threshold (Frozen OD-AUTH-02)",
    escalationCooldown: "15 minutes → 1 hour → 24 hours progressive lockout",
    isolationGuarantee: "Locks password verification only. Recovery codes and passkey login remain accessible.",
    policyStatus: "FROZEN_V1_POLICY",
    isFrozen: true,
  },
  {
    id: "rl-02",
    flowName: "Activation Code Redemption",
    targetEndpoint: "/api/v1/auth/activate",
    failureThreshold: "5 failed attempts threshold (Frozen OD-AUTH-02)",
    escalationCooldown: "15 minutes → 1 hour → 24 hours progressive lockout",
    isolationGuarantee: "Locks activation endpoint only. Other users and Owner operations unaffected.",
    policyStatus: "FROZEN_V1_POLICY",
    isFrozen: true,
  },
  {
    id: "rl-03",
    flowName: "Recovery Code Submission",
    targetEndpoint: "/api/v1/auth/recover/code",
    failureThreshold: "Technical Parameter (Deferred to Backend Security Design)",
    escalationCooldown: "15 minutes → 1 hour → 24 hours progressive cooldown",
    isolationGuarantee: "Locks recovery code submission only. Normal login channels unaffected.",
    policyStatus: "TECHNICAL_PARAM_DEFERRED",
    isFrozen: false,
  },
  {
    id: "rl-04",
    flowName: "Email / Phone OTP Delivery & Verify",
    targetEndpoint: "/api/v1/auth/otp/*",
    failureThreshold: "Technical Parameter (Deferred to Backend Security Design)",
    escalationCooldown: "15 minutes → 1 hour → 24 hours progressive cooldown",
    isolationGuarantee: "Throttles verification & delivery to prevent flooding. Normal authentication unaffected.",
    policyStatus: "TECHNICAL_PARAM_DEFERRED",
    isFrozen: false,
  },
  {
    id: "rl-05",
    flowName: "Global Abuse / Risk Limiter",
    targetEndpoint: "/api/v1/* (Global / Flow Protection)",
    failureThreshold: "Technical Parameter — Deferred to Backend Security Design",
    escalationCooldown: "Technical parameters & implementation deferred to backend security design",
    isolationGuarantee: "Throttles abusive flow without modifying user account access states or triggering suspension.",
    policyStatus: "TECHNICAL_PARAM_DEFERRED",
    isFrozen: false,
  },
];

export const INITIAL_SYSTEM_SUBSYSTEMS: SystemHealthSubsystem[] = [
  {
    id: "sys-01",
    name: "Frontend Application Surface",
    category: "APPLICATION",
    status: "OPERATIONAL",
    tone: "ok",
    currentStatusLabel: "OPERATIONAL · Visual-Lab V3",
    targetArchitecture: "Desktop-First Workstation Shell (DEV PREVIEW / SAMPLE)",
    detail: "Client UI render nominal · 0 uncaught console errors · Institutional dark theme #05080e",
    lastTelemetry: "2026-09-01 11:15:00 UTC",
  },
  {
    id: "sys-02",
    name: "Backend API & Engine Integration",
    category: "INTEGRATION",
    status: "NOT_CONNECTED",
    tone: "warn",
    currentStatusLabel: "BACKEND INTEGRATION DEFERRED",
    targetArchitecture: "FastAPI / Python 3.12 Engine Daemon on localhost:8000",
    detail: "Frontend-to-backend socket & REST wiring is not connected in V1 preview. Fail-closed contract active.",
    lastTelemetry: "2026-09-01 11:15:00 UTC",
  },
  {
    id: "sys-03",
    name: "Persistence & State Store Health",
    category: "PERSISTENCE",
    status: "PROTOTYPE_PROJECTION",
    tone: "dim",
    currentStatusLabel: "PROTOTYPE LOCAL STORAGE",
    targetArchitecture: "SQLite WAL Mode (D16 ACID Transaction Ledger with Crash Recovery)",
    detail: "Current browser localStorage is a prototype fixture store. Target architecture: SQLite WAL authoritative store.",
    lastTelemetry: "2026-09-01 11:15:00 UTC",
  },
  {
    id: "sys-04",
    name: "Core Audit Store Authority",
    category: "AUDIT",
    status: "PROTOTYPE_PROJECTION",
    tone: "dim",
    currentStatusLabel: "PROTOTYPE D16 PROJECTION",
    targetArchitecture: "Append-Only Immutable SQLite WAL Ledger (SHA-256 Chain + D16 Taxonomy)",
    detail: "Current UI is a prototype projection of D16 audit taxonomy. Full ledger authority in Step 8 Reports & Audit.",
    lastTelemetry: "2026-09-01 11:15:00 UTC",
  },
  {
    id: "sys-05",
    name: "Market Data & Tick Feed",
    category: "DATA_STREAM",
    status: "PROTOTYPE_PROJECTION",
    tone: "dim",
    currentStatusLabel: "PROTOTYPE SAMPLE TICK CACHE",
    targetArchitecture: "Multi-Broker WebSocket Level-2 Feed with Gap-Detection & Orderbook Builder",
    detail: "Pre-seeded historical sample ticks loaded for NIFTY / BANKNIFTY. Live WebSocket stream deferred.",
    lastTelemetry: "2026-09-01 11:15:00 UTC",
  },
  {
    id: "sys-06",
    name: "Paper Simulation Engine",
    category: "APPLICATION",
    status: "PROTOTYPE_PROJECTION",
    tone: "dim",
    currentStatusLabel: "PROTOTYPE SIMULATION STATE",
    targetArchitecture: "Deterministic Match Engine with Slippage / Margin Math",
    detail: "Client-side simulation running in isolated prototype state. Fully segregated from broker live orders.",
    lastTelemetry: "2026-09-01 11:15:00 UTC",
  },
  {
    id: "sys-07",
    name: "Protective Risk Governance",
    category: "RISK_ENGINE",
    status: "FAIL_CLOSED",
    tone: "ok",
    currentStatusLabel: "FAIL-CLOSED ARCHITECTURAL CONTRACT",
    targetArchitecture: "Kernel-Level Pre-Trade Risk Sentinel (Hard Margin / Max Loss Envelopes)",
    detail: "Risk perimeters fail closed by contract. Owner authority cannot disable live protective stops or risk gates.",
    lastTelemetry: "2026-09-01 11:15:00 UTC",
  },
  {
    id: "sys-08",
    name: "Broker / API Plugin Gateway",
    category: "INTEGRATION",
    status: "PROTOTYPE_PROJECTION",
    tone: "dim",
    currentStatusLabel: "PROTOTYPE CONNECTOR PROJECTION",
    targetArchitecture: "Multi-Broker Adapter Pool (Angel One, Zerodha Kite, Dhan, Upstox)",
    detail: "Prototype credential schema & health projection. Direct broker API authorization deferred to backend.",
    lastTelemetry: "2026-09-01 11:15:00 UTC",
  },
];

export const INITIAL_OWNER_SETTINGS: OwnerSettingsState = {
  defaultLandingView: "overview",
  uiDensity: "comfortable",
  uiInactivityWarning: "30m",
  audioChimeOnCriticalAlert: false,
  clockFormat: "UTC",
};


export function getStoredOwnerSettings(): OwnerSettingsState {
  try {
    const raw = localStorage.getItem(OWNER_SETTINGS_KEY);
    if (!raw) {
      localStorage.setItem(OWNER_SETTINGS_KEY, JSON.stringify(INITIAL_OWNER_SETTINGS));
      return INITIAL_OWNER_SETTINGS;
    }
    const parsed = JSON.parse(raw);
    return { ...INITIAL_OWNER_SETTINGS, ...parsed };
  } catch {
    return INITIAL_OWNER_SETTINGS;
  }
}

export function saveStoredOwnerSettings(settings: OwnerSettingsState): void {
  try {
    localStorage.setItem(OWNER_SETTINGS_KEY, JSON.stringify(settings));
  } catch (err) {
    console.error("Failed to save owner settings prototype state", err);
  }
}

export function updateOwnerSetting<K extends keyof OwnerSettingsState>(key: K, value: OwnerSettingsState[K]): void {
  const current = getStoredOwnerSettings();
  current[key] = value;
  saveStoredOwnerSettings(current);
}










