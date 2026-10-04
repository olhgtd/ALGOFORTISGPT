/**
 * AlgoFortis Dashboard V3 — Owner Users & Service Entitlement Domain
 */
import type { Truth } from "../../shared/data/sharedTypes";
import type { AccessRecord, ServiceTermType, CustomServiceTerm, AccessStatus, ServiceEntitlementStatus, AccountAccessStatus } from "./access";
import { getServiceTermLabel, computeServiceExpiry } from "./access";
import { getStoredAccessRecords, saveStoredAccessRecords } from "./access";
import { STORAGE_KEYS, prototypeFixtureStorage, safeGetJson, safeSetJson } from "../../shared/data/storage";

const localStorage = prototypeFixtureStorage;

export interface UserRow {
  id: string; name: string; sxId: string; plan: string;
  status: "ACTIVE" | "SUSPENDED" | "ONBOARDING";
  strategies: number; connectors: number; lastActive: string; sessions: number;
}
export const USERS: UserRow[] = [];

export interface OwnerUser {
  id: string;
  sxId: string;
  name: string;
  email: string;
  phone: string;
  emailMasked: string;
  phoneMasked: string;
  accountStatus: "ACTIVE" | "SUSPENDED" | "INVITED";
  accessStatus: AccessStatus;
  accessIdRef: string;
  serviceTermLabel?: string;
  serviceStatus?: ServiceEntitlementStatus;
  serviceExpiresAt?: string | null;
  plan: string;
  role: string;
  lastActive: string;
  lastSession: string;
  strategiesCount: number;
  paperSessionsCount: number;
  connectorsCount: number;
  sessionsCount: number;
}

export const DEFAULT_OWNER_USERS: OwnerUser[] = [];

const ACCESS_REGISTRY_KEY = STORAGE_KEYS.ACCESS_REGISTRY;
const OWNER_USERS_KEY = STORAGE_KEYS.OWNER_USERS;


export function getStoredOwnerUsers(): OwnerUser[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(OWNER_USERS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveStoredOwnerUsers(users: OwnerUser[]): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(OWNER_USERS_KEY, JSON.stringify(users));
  } catch { }
}


export function extendServiceEntitlement(
  targetIdOrSxId: string,
  termType: ServiceTermType,
  customTerm?: CustomServiceTerm,
  actor: string = "OWNER-001"
): { success: boolean; message: string; error?: string } {
  const records = getStoredAccessRecords();
  const now = new Date();
  const nowStr = now.toISOString().replace("T", " ").slice(0, 19) + " UTC";
  let changed = false;
  let recordName = "";

  const updated = records.map((r) => {
    const match =
      (r.sxId && r.sxId.toUpperCase() === targetIdOrSxId.toUpperCase()) ||
      (r.accessId && r.accessId.toUpperCase() === targetIdOrSxId.toUpperCase()) ||
      r.id === targetIdOrSxId;
    if (match) {
      changed = true;
      recordName = r.displayName;

      if (r.serviceTermType === "LIFETIME") {
        return r;
      }

      // If service is not started, simply change configured term
      if (r.serviceStatus === "NOT_STARTED" || !r.serviceExpiresAt) {
        const newLabel = getServiceTermLabel(termType, customTerm);
        return {
          ...r,
          serviceTermType: termType,
          serviceTermCustom: customTerm,
          serviceTermLabel: newLabel,
          history: [
            ...r.history,
            { time: nowStr, action: "SERVICE_TERM_UPDATED", actor: `${actor} (Configured term updated to ${newLabel})` },
          ],
        };
      }

      // Extension begins from CURRENT service expiry (OD-AUTH-21)
      const currentExpiryDate = new Date(r.serviceExpiresAt.replace(" UTC", "Z"));
      const newExpiryDate = computeServiceExpiry(currentExpiryDate, termType, customTerm);
      const newExpiresAtStr = newExpiryDate ? newExpiryDate.toISOString().replace("T", " ").slice(0, 19) + " UTC" : null;
      const extensionLabel = getServiceTermLabel(termType, customTerm);

      return {
        ...r,
        serviceExpiresAt: newExpiresAtStr,
        serviceStatus: "ACTIVE" as ServiceEntitlementStatus,
        history: [
          ...r.history,
          {
            time: nowStr,
            action: "SERVICE_ENTITLEMENT_EXTENDED",
            actor: `${actor} (Extended +${extensionLabel} from ${r.serviceExpiresAt} -> ${newExpiresAtStr})`,
          },
        ],
      };
    }
    return r;
  });

  if (!changed) return { success: false, message: "Record not found", error: "Record not found" };

  saveStoredAccessRecords(updated);
  return { success: true, message: `Successfully extended service entitlement for ${recordName}.` };
}

export function renewServiceEntitlement(
  targetIdOrSxId: string,
  termType: ServiceTermType,
  customTerm?: CustomServiceTerm,
  actor: string = "OWNER-001"
): { success: boolean; message: string; error?: string } {
  const records = getStoredAccessRecords();
  const now = new Date();
  const nowStr = now.toISOString().replace("T", " ").slice(0, 19) + " UTC";
  let changed = false;
  let recordName = "";

  const updated = records.map((r) => {
    const match =
      (r.sxId && r.sxId.toUpperCase() === targetIdOrSxId.toUpperCase()) ||
      (r.accessId && r.accessId.toUpperCase() === targetIdOrSxId.toUpperCase()) ||
      r.id === targetIdOrSxId;
    if (match) {
      changed = true;
      recordName = r.displayName;

      // Renewal begins from NOW (renewal timestamp) (OD-AUTH-21)
      const newExpiryDate = computeServiceExpiry(now, termType, customTerm);
      const newExpiresAtStr = newExpiryDate ? newExpiryDate.toISOString().replace("T", " ").slice(0, 19) + " UTC" : null;
      const termLabel = getServiceTermLabel(termType, customTerm);

      return {
        ...r,
        serviceTermType: termType,
        serviceTermCustom: customTerm,
        serviceTermLabel: termLabel,
        serviceStatus: "ACTIVE" as ServiceEntitlementStatus,
        serviceStartedAt: nowStr,
        serviceExpiresAt: newExpiresAtStr,
        history: [
          ...r.history,
          {
            time: nowStr,
            action: "SERVICE_ENTITLEMENT_RENEWED",
            actor: `${actor} (Renewed ${termLabel} term starting ${nowStr} -> ${newExpiresAtStr})`,
          },
        ],
      };
    }
    return r;
  });

  if (!changed) return { success: false, message: "Record not found", error: "Record not found" };

  saveStoredAccessRecords(updated);
  return { success: true, message: `Successfully renewed service entitlement for ${recordName}.` };
}

export function convertToLifetimeEntitlement(
  targetIdOrSxId: string,
  actor: string = "OWNER-001"
): { success: boolean; message: string; error?: string } {
  const records = getStoredAccessRecords();
  const nowStr = new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC";
  let changed = false;
  let recordName = "";

  const updated = records.map((r) => {
    const match =
      (r.sxId && r.sxId.toUpperCase() === targetIdOrSxId.toUpperCase()) ||
      (r.accessId && r.accessId.toUpperCase() === targetIdOrSxId.toUpperCase()) ||
      r.id === targetIdOrSxId;
    if (match) {
      changed = true;
      recordName = r.displayName;
      return {
        ...r,
        serviceTermType: "LIFETIME" as ServiceTermType,
        serviceTermCustom: undefined,
        serviceTermLabel: "Lifetime",
        serviceStatus: r.accountStatus === "PENDING" ? ("NOT_STARTED" as ServiceEntitlementStatus) : ("ACTIVE" as ServiceEntitlementStatus),
        serviceExpiresAt: null,
        history: [
          ...r.history,
          { time: nowStr, action: "CONVERTED_TO_LIFETIME", actor: `${actor} (Granted Lifetime Entitlement)` },
        ],
      };
    }
    return r;
  });

  if (!changed) return { success: false, message: "Record not found", error: "Record not found" };

  saveStoredAccessRecords(updated);
  return { success: true, message: `Successfully converted ${recordName} to Lifetime entitlement.` };
}


export function suspendOwnerUser(userId: string): boolean {
  const users = getStoredOwnerUsers();
  const records = getStoredAccessRecords();
  const now = new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC";
  let changed = false;

  const updatedUsers = users.map((u) => {
    if (u.id === userId) {
      changed = true;
      return { ...u, accountStatus: "SUSPENDED" as const, accessStatus: "SUSPENDED" as AccessStatus };
    }
    return u;
  });

  if (changed) {
    saveStoredOwnerUsers(updatedUsers);
    const target = users.find((u) => u.id === userId);
    if (target) {
      const updatedRecords = records.map((r) => {
        if (r.accessId === target.accessIdRef || r.sxId === target.accessIdRef) {
          return {
            ...r,
            accountStatus: "SUSPENDED" as AccountAccessStatus,
            status: "SUSPENDED" as AccessStatus,
            history: [...r.history, { time: now, action: "USER_SUSPENDED", actor: "OWNER-001" }],
          };
        }
        return r;
      });
      saveStoredAccessRecords(updatedRecords);
    }
  }
  return changed;
}

export function restoreOwnerUser(userId: string): boolean {
  const users = getStoredOwnerUsers();
  const records = getStoredAccessRecords();
  const now = new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC";
  let changed = false;

  const updatedUsers = users.map((u) => {
    if (u.id === userId) {
      changed = true;
      return { ...u, accountStatus: "ACTIVE" as const, accessStatus: "ACTIVE" as AccessStatus };
    }
    return u;
  });

  if (changed) {
    saveStoredOwnerUsers(updatedUsers);
    const target = users.find((u) => u.id === userId);
    if (target) {
      const updatedRecords = records.map((r) => {
        if (r.accessId === target.accessIdRef || r.sxId === target.accessIdRef) {
          const restoredAccountStatus: AccountAccessStatus = r.redeemedAt ? "ACTIVE" : "PENDING";
          const restoredStatus: AccessStatus = r.redeemedAt ? "ACTIVE" : (r.activationStatus === "INVITED" ? "INVITED" : "DRAFT");
          return {
            ...r,
            accountStatus: restoredAccountStatus,
            status: restoredStatus,
            history: [...r.history, { time: now, action: "USER_RESTORED", actor: "OWNER-001" }],
          };
        }
        return r;
      });
      saveStoredAccessRecords(updatedRecords);
    }
  }
  return changed;
}


export const INVITES: any[] = [];


export const SERVICES = [
  { name: "Trading Core", status: "OPERATIONAL" as const, detail: "Engine loop nominal · 12ms tick" },
  { name: "Risk Authority", status: "OPERATIONAL" as const, detail: "Fail-closed · all envelopes green" },
  { name: "Core Audit", status: "OPERATIONAL" as const, detail: "Chain intact · last seal 14:00 UTC" },
  { name: "Security Store", status: "OPERATIONAL" as const, detail: "WebAuthn ceremonies verified" },
  { name: "Audit Reconciliation", status: "DEGRADED" as const, detail: "12 unreconciled events — reconciliation review required" },
];

export const PLUGIN_HEALTH: any[] = [];

export const AUDIT_ITEMS: any[] = [];

export const USER_DETAIL_TABS = ["Profile", "Strategies", "Backtests", "Paper", "Portfolio", "Orders", "Broker/API Plugins", "Reports", "Sessions", "Security"] as const;
export type UserDetailTab = (typeof USER_DETAIL_TABS)[number];
