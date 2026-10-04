/**
 * AlgoFortis Dashboard V3 — Access Registry & Token Issuance Domain
 */
import type { Truth } from "../../shared/data/sharedTypes";
import type { OwnerUser } from "./users";
import { getStoredOwnerUsers, saveStoredOwnerUsers } from "./users";
import { STORAGE_KEYS, prototypeFixtureStorage, safeGetJson, safeSetJson } from "../../shared/data/storage";

const localStorage = prototypeFixtureStorage;

const ACCESS_REGISTRY_KEY = STORAGE_KEYS.ACCESS_REGISTRY;

export type ActivationStatus =
  | "DRAFT"
  | "INVITED"
  | "REDEEMED"
  | "EXPIRED"
  | "REVOKED";

export type AccountAccessStatus =
  | "PENDING"
  | "ACTIVE"
  | "SUSPENDED"
  | "REVOKED";

export type AccessStatus =
  | "DRAFT"
  | "INVITED"
  | "REDEEMED"
  | "ACTIVE"
  | "EXPIRED"
  | "REVOKED"
  | "SUSPENDED";

export interface ActivationIssuance {
  id: string; // e.g. "iss-acc01-1"
  code: string | null; // DEV SAMPLE plaintext code or null
  issuedAt: string;
  expiresAt: string | null;
  status: ActivationStatus;
  revokedAt?: string | null;
  redeemedAt?: string | null;
  actor?: string;
  notes?: string;
}

export type ServiceEntitlementStatus = "NOT_STARTED" | "ACTIVE" | "EXPIRED";
export type ServiceTermType = "1_MONTH" | "3_MONTHS" | "6_MONTHS" | "12_MONTHS" | "LIFETIME" | "CUSTOM";

export interface CustomServiceTerm {
  value: number;
  unit: "DAYS" | "MONTHS";
}

export interface AccessRecord {
  id: string;
  sxId: string; // Permanent account ID, e.g. "SX-U-8K4P-92QX" (never consumed/redeemed)
  accessId: string; // Legacy alias pointing to sxId for backwards compatibility
  activationCode: string | null; // Active unconsumed 24h code (or null if redeemed/draft/revoked)
  activationStatus: ActivationStatus; // DRAFT | INVITED | REDEEMED | EXPIRED | REVOKED
  accountStatus: AccountAccessStatus; // PENDING | ACTIVE | SUSPENDED | REVOKED
  status: AccessStatus; // Legacy / composite status for compatibility
  displayName: string;
  email: string;
  phone: string;
  emailMasked: string;
  phoneMasked: string;
  createdAt: string;
  expiresAt: string | null; // Active activation code expiration (24h)
  redeemedAt: string | null; // First redemption timestamp
  serviceTermType: ServiceTermType;
  serviceTermCustom?: CustomServiceTerm;
  serviceTermLabel: string; // e.g. "1 Month", "3 Months", "6 Months", "12 Months", "Lifetime", "45 Days"
  serviceStatus: ServiceEntitlementStatus; // NOT_STARTED | ACTIVE | EXPIRED
  serviceStartedAt: string | null; // Timestamp of successful first activation (null before activation)
  serviceExpiresAt: string | null; // Authoritative UTC expiration timestamp (null for lifetime / NOT_STARTED)
  notes: string;
  role: string;
  plan: string;
  createdBy: string; // e.g. "OWNER-001"
  history: { time: string; action: string; actor: string }[];
  activationHistory: ActivationIssuance[];
}

export const maskEmail = (email: string): string => {
  if (!email || !email.includes("@")) return email;
  const [user, domain] = email.split("@");
  if (user.length <= 2) return `${user[0]}*@${domain}`;
  return `${user.slice(0, 2)}${"*".repeat(Math.min(user.length - 2, 5))}@${domain}`;
};

export const maskPhone = (phone: string): string => {
  if (!phone) return phone;
  const clean = phone.trim();
  if (clean.length < 8) return clean;
  const prefix = clean.slice(0, 6);
  const suffix = clean.slice(-3);
  return `${prefix} •••• ${suffix}`;
};

export function addCalendarMonths(date: Date, months: number): Date {
  const d = new Date(date.getTime());
  const origDay = d.getUTCDate();
  const origHours = d.getUTCHours();
  const origMinutes = d.getUTCMinutes();
  const origSeconds = d.getUTCSeconds();
  const origMs = d.getUTCMilliseconds();

  d.setUTCDate(1);
  d.setUTCMonth(d.getUTCMonth() + months);

  const year = d.getUTCFullYear();
  const month = d.getUTCMonth();
  const maxDaysInTargetMonth = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();

  const clampedDay = Math.min(origDay, maxDaysInTargetMonth);
  d.setUTCDate(clampedDay);
  d.setUTCHours(origHours, origMinutes, origSeconds, origMs);
  return d;
}

export function computeServiceExpiry(
  startDate: Date,
  termType: ServiceTermType,
  customTerm?: CustomServiceTerm
): Date | null {
  if (termType === "LIFETIME") return null;

  if (termType === "CUSTOM" && customTerm) {
    if (customTerm.unit === "DAYS") {
      return new Date(startDate.getTime() + customTerm.value * 86400000);
    }
    return addCalendarMonths(startDate, customTerm.value);
  }

  let monthsToAdd = 1;
  if (termType === "3_MONTHS") monthsToAdd = 3;
  else if (termType === "6_MONTHS") monthsToAdd = 6;
  else if (termType === "12_MONTHS") monthsToAdd = 12;

  return addCalendarMonths(startDate, monthsToAdd);
}

export function getServiceTermLabel(termType: ServiceTermType, customTerm?: CustomServiceTerm): string {
  switch (termType) {
    case "1_MONTH": return "1 Month";
    case "3_MONTHS": return "3 Months";
    case "6_MONTHS": return "6 Months";
    case "12_MONTHS": return "12 Months";
    case "LIFETIME": return "Lifetime";
    case "CUSTOM":
      if (!customTerm) return "Custom";
      return `${customTerm.value} ${customTerm.unit === "DAYS" ? (customTerm.value === 1 ? "Day" : "Days") : (customTerm.value === 1 ? "Month" : "Months")}`;
    default: return "3 Months";
  }
}

export const DEFAULT_ACCESS_REGISTRY: AccessRecord[] = [];


export function getStoredAccessRecords(): AccessRecord[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(ACCESS_REGISTRY_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveStoredAccessRecords(records: AccessRecord[]): void {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(ACCESS_REGISTRY_KEY, JSON.stringify(records));
  } catch { }
}


export interface AccessValidationResult {
  valid: boolean;
  status?: AccessStatus;
  record?: AccessRecord;
  reason?: "NOT_FOUND" | "EXPIRED" | "REVOKED" | "ALREADY_REDEEMED" | "SUSPENDED" | "DRAFT_NOT_ISSUED" | "VALID";
  message: string;
}

export function validateAccessId(rawCode: string): AccessValidationResult {
  const code = (rawCode || "").trim().toUpperCase();
  if (!code) {
    return {
      valid: false,
      reason: "NOT_FOUND",
      message: "This AlgoFortis installation is invite-only. Contact your AlgoFortis administrator.",
    };
  }

  const records = getStoredAccessRecords();
  const match = records.find((r) => r.accessId.toUpperCase() === code);

  if (!match) {
    return {
      valid: false,
      reason: "NOT_FOUND",
      message: "This AlgoFortis installation is invite-only. Contact your AlgoFortis administrator.",
    };
  }

  if (match.status === "REVOKED") {
    return {
      valid: false,
      status: "REVOKED",
      record: match,
      reason: "REVOKED",
      message: "Access authorization has been revoked by AlgoFortis administration.",
    };
  }

  if (match.status === "EXPIRED") {
    return {
      valid: false,
      status: "EXPIRED",
      record: match,
      reason: "EXPIRED",
      message: "Access authorization token has expired. Contact your administrator for a new token.",
    };
  }

  if (match.status === "REDEEMED" || match.status === "ACTIVE") {
    return {
      valid: false,
      status: match.status,
      record: match,
      reason: "ALREADY_REDEEMED",
      message: "Access ID has already been redeemed for an active account. Please sign in as a returning user.",
    };
  }

  if (match.status === "SUSPENDED") {
    return {
      valid: false,
      status: "SUSPENDED",
      record: match,
      reason: "SUSPENDED",
      message: "Access record is currently suspended pending administrative review.",
    };
  }

  if (match.status === "DRAFT") {
    return {
      valid: false,
      status: "DRAFT",
      record: match,
      reason: "DRAFT_NOT_ISSUED",
      message: "This AlgoFortis installation is invite-only. Contact your AlgoFortis administrator.",
    };
  }

  return {
    valid: true,
    status: "INVITED",
    record: match,
    reason: "VALID",
    message: "Valid owner-issued access token verified.",
  };
}

export function redeemAccessId(
  rawCode: string,
  enteredEmail: string,
  enteredPhone: string
): { success: boolean; error?: string; user?: OwnerUser } {
  const code = (rawCode || "").trim().toUpperCase();
  const validation = validateAccessId(code);

  if (!validation.valid || !validation.record) {
    return { success: false, error: validation.message };
  }

  const record = validation.record;
  const normEmail = enteredEmail.trim().toLowerCase();
  const normRecordEmail = record.email.trim().toLowerCase();

  // Validate email binding
  if (normEmail !== normRecordEmail) {
    return {
      success: false,
      error: "Identity verification failed: entered email does not match Owner authorization record.",
    };
  }

  // Validate phone binding (loose normalization ignoring spaces, dashes)
  const cleanEnteredPhone = enteredPhone.replace(/[\s\-()]/g, "");
  const cleanRecordPhone = record.phone.replace(/[\s\-()]/g, "");

  if (cleanEnteredPhone !== cleanRecordPhone) {
    return {
      success: false,
      error: "Identity verification failed: entered phone number does not match Owner authorization record.",
    };
  }

  // Transition status: INVITED -> REDEEMED -> ACTIVE
  const records = getStoredAccessRecords();
  const now = new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC";

  const updatedRecords = records.map((r) => {
    if (r.id === record.id) {
      return {
        ...r,
        status: "REDEEMED" as AccessStatus,
        redeemedAt: now,
        history: [
          ...r.history,
          { time: now, action: "ACCESS_TOKEN_REDEEMED", actor: `${record.displayName} (Identity Verified)` },
        ],
      };
    }
    return r;
  });

  saveStoredAccessRecords(updatedRecords);

  // Add / Activate in Owner Users
  const users = getStoredOwnerUsers();
  const foundUser = users.find((u) => u.accessIdRef === record.accessId || u.email.toLowerCase() === normEmail);
  let resolvedUser: OwnerUser;

  if (!foundUser) {
    resolvedUser = {
      id: `ou-${Date.now()}`,
      sxId: `SX-${Math.floor(1000 + Math.random() * 9000)}-QUANT`,
      name: record.displayName,
      email: record.email,
      phone: record.phone,
      emailMasked: record.emailMasked,
      phoneMasked: record.phoneMasked,
      accountStatus: "ACTIVE",
      accessStatus: "ACTIVE",
      accessIdRef: record.accessId,
      plan: record.plan || "Quant Professional",
      role: record.role || "Quant Trader",
      lastActive: "Active Now",
      lastSession: now,
      strategiesCount: 2,
      paperSessionsCount: 1,
      connectorsCount: 1,
      sessionsCount: 1,
    };
    users.unshift(resolvedUser);
  } else {
    foundUser.accountStatus = "ACTIVE";
    foundUser.accessStatus = "ACTIVE";
    foundUser.lastActive = "Active Now";
    foundUser.lastSession = now;
    resolvedUser = foundUser;
  }

  saveStoredOwnerUsers(users);

  return { success: true, user: resolvedUser };
}

export function generatePrototypeAlgoFortisId(): string {
  const chars = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ";
  const part1 = Array.from({ length: 4 }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
  const part2 = Array.from({ length: 4 }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
  return `SX-U-${part1}-${part2}`;
}

export function generatePrototypeActivationCode(): string {
  const chars = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ";
  const part1 = Array.from({ length: 4 }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
  const part2 = Array.from({ length: 4 }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
  const part3 = Array.from({ length: 4 }, () => chars[Math.floor(Math.random() * chars.length)]).join("");
  return `SX-ACT-${part1}-${part2}-${part3}`;
}

export const generateRandomAccessId = generatePrototypeAlgoFortisId;

export function createNewAccessRecord(data: {
  displayName: string;
  email: string;
  phone: string;
  sxId?: string;
  accessId?: string;
  activationCode?: string;
  serviceTermType?: ServiceTermType;
  serviceTermCustom?: CustomServiceTerm;
  role?: string;
  plan?: string;
  notes?: string;
}): AccessRecord {
  const records = getStoredAccessRecords();
  const sxId = data.sxId || data.accessId || generatePrototypeAlgoFortisId();
  const activationCode = data.activationCode || generatePrototypeActivationCode();
  const now = new Date();
  const nowStr = now.toISOString().replace("T", " ").slice(0, 19) + " UTC";
  // Fixed 24 hours expiry for V1 activation code
  const expDate = new Date(now.getTime() + 24 * 60 * 60 * 1000);
  const expiresAt = expDate.toISOString().replace("T", " ").slice(0, 19) + " UTC";

  const termType: ServiceTermType = data.serviceTermType || "3_MONTHS";
  const customTerm = data.serviceTermCustom;
  const termLabel = getServiceTermLabel(termType, customTerm);

  const newRecord: AccessRecord = {
    id: `acc-${Date.now()}`,
    sxId,
    accessId: sxId,
    activationCode,
    activationStatus: "INVITED",
    accountStatus: "PENDING",
    status: "INVITED",
    displayName: data.displayName.trim(),
    email: data.email.trim(),
    phone: data.phone.trim(),
    emailMasked: maskEmail(data.email.trim()),
    phoneMasked: maskPhone(data.phone.trim()),
    createdAt: nowStr,
    expiresAt,
    redeemedAt: null,
    serviceTermType: termType,
    serviceTermCustom: customTerm,
    serviceTermLabel: termLabel,
    serviceStatus: "NOT_STARTED", // Service clock begins ONLY on successful first activation (OD-AUTH-19)
    serviceStartedAt: null,
    serviceExpiresAt: null,
    notes: data.notes || "Owner-created access record",
    role: data.role || "Quant Trader",
    plan: data.plan || "Quant Professional",
    createdBy: "OWNER-001",
    history: [
      { time: nowStr, action: "ACCESS_RECORD_CREATED", actor: `OWNER-001 (Provisioned ${sxId} with ${termLabel} Service Term)` },
      { time: nowStr, action: "ACTIVATION_CODE_ISSUED", actor: `OWNER-001 -> ${maskEmail(data.email.trim())} (24h Code: ${activationCode})` },
    ],
    activationHistory: [
      {
        id: `iss-${Date.now()}-1`,
        code: activationCode,
        issuedAt: nowStr,
        expiresAt,
        status: "INVITED",
        actor: "OWNER-001",
        notes: "Initial 24-hour activation issuance",
      },
    ],
  };

  records.unshift(newRecord);
  saveStoredAccessRecords(records);
  return newRecord;
}


export function simulateFirstActivation(
  targetIdOrSxId: string
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
      if (r.activationStatus !== "INVITED") {
        return r;
      }
      changed = true;
      recordName = r.displayName;

      const expiryDate = computeServiceExpiry(now, r.serviceTermType || "3_MONTHS", r.serviceTermCustom);
      const expiresAtStr = expiryDate ? expiryDate.toISOString().replace("T", " ").slice(0, 19) + " UTC" : null;

      const updatedHistory = (r.activationHistory || []).map((iss) => {
        if (iss.status === "INVITED") {
          return { ...iss, status: "REDEEMED" as ActivationStatus, redeemedAt: nowStr };
        }
        return iss;
      });

      return {
        ...r,
        activationCode: null,
        activationStatus: "REDEEMED" as ActivationStatus,
        accountStatus: "ACTIVE" as AccountAccessStatus,
        status: "ACTIVE" as AccessStatus,
        redeemedAt: nowStr,
        serviceStatus: "ACTIVE" as ServiceEntitlementStatus,
        serviceStartedAt: nowStr,
        serviceExpiresAt: expiresAtStr,
        activationHistory: updatedHistory,
        history: [
          ...r.history,
          {
            time: nowStr,
            action: "SIMULATED_FIRST_ACTIVATION",
            actor: `${r.displayName} (First Activation Complete · Service Clock Started: ${r.serviceTermLabel} -> ${expiresAtStr || "Never"})`,
          },
        ],
      };
    }
    return r;
  });

  if (!changed) return { success: false, message: "Record cannot be activated or not found", error: "Record cannot be activated" };

  saveStoredAccessRecords(updated);
  return { success: true, message: `Simulated first activation for ${recordName}. Service clock started!` };
}


export function reissueActivationCode(targetIdOrSxId: string): { success: boolean; newCode?: string; error?: string } {
  const records = getStoredAccessRecords();
  const now = new Date();
  const nowStr = now.toISOString().replace("T", " ").slice(0, 19) + " UTC";
  const expDate = new Date(now.getTime() + 24 * 60 * 60 * 1000);
  const expiresAt = expDate.toISOString().replace("T", " ").slice(0, 19) + " UTC";
  let changed = false;
  let newCode = "";
  let errorMsg: string | undefined = undefined;

  const updated = records.map((r) => {
    const match =
      (r.sxId && r.sxId.toUpperCase() === targetIdOrSxId.toUpperCase()) ||
      (r.accessId && r.accessId.toUpperCase() === targetIdOrSxId.toUpperCase()) ||
      r.id === targetIdOrSxId;
    if (match) {
      // INVARIANT GUARDS:
      if (r.accountStatus === "REVOKED") {
        errorMsg = "Cannot reissue activation for a Revoked Account. Restore account access first.";
        return r;
      }
      if (r.accountStatus === "SUSPENDED") {
        errorMsg = "Cannot reissue activation for a Suspended Account. Restore account access first.";
        return r;
      }

      changed = true;
      newCode = generatePrototypeActivationCode();

      // Preserve historical issuance evidence by updating existing unconsumed issuance to EXPIRED or keeping previous status
      const updatedHistory: ActivationIssuance[] = (r.activationHistory || []).map((iss) => {
        if (iss.status === "INVITED") {
          return { ...iss, status: "EXPIRED" as ActivationStatus };
        }
        return iss;
      });

      // Append new issuance
      updatedHistory.push({
        id: `iss-${Date.now()}-${updatedHistory.length + 1}`,
        code: newCode,
        issuedAt: nowStr,
        expiresAt,
        status: "INVITED",
        actor: "OWNER-001",
        notes: "Reissued 24h activation code",
      });

      return {
        ...r,
        activationCode: newCode,
        activationStatus: "INVITED" as ActivationStatus,
        status: "INVITED" as AccessStatus,
        expiresAt,
        // Account status remains PENDING / unchanged - NEVER silently converted
        accountStatus: r.accountStatus,
        activationHistory: updatedHistory,
        history: [
          ...r.history,
          { time: nowStr, action: "ACTIVATION_REISSUED", actor: `OWNER-001 (New 24h code issued: ${newCode})` },
        ],
      };
    }
    return r;
  });

  if (errorMsg) {
    return { success: false, error: errorMsg };
  }

  if (changed) {
    saveStoredAccessRecords(updated);
    return { success: true, newCode };
  }
  return { success: false, error: "Record not found" };
}

export function revokeActivationCode(targetIdOrSxId: string): boolean {
  const records = getStoredAccessRecords();
  const nowStr = new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC";
  let changed = false;

  const updated = records.map((r) => {
    const match =
      (r.sxId && r.sxId.toUpperCase() === targetIdOrSxId.toUpperCase()) ||
      (r.accessId && r.accessId.toUpperCase() === targetIdOrSxId.toUpperCase()) ||
      r.id === targetIdOrSxId;
    if (match) {
      changed = true;
      const updatedHistory: ActivationIssuance[] = (r.activationHistory || []).map((iss, idx) => {
        if (idx === (r.activationHistory || []).length - 1 || iss.status === "INVITED") {
          return { ...iss, status: "REVOKED" as ActivationStatus, revokedAt: nowStr };
        }
        return iss;
      });

      return {
        ...r,
        activationStatus: "REVOKED" as ActivationStatus,
        // Account status remains PENDING / unchanged (only activation invitation was revoked)
        activationHistory: updatedHistory,
        history: [
          ...r.history,
          { time: nowStr, action: "ACTIVATION_REVOKED", actor: "OWNER-001 (Activation invitation revoked)" },
        ],
      };
    }
    return r;
  });

  if (changed) saveStoredAccessRecords(updated);
  return changed;
}

export function revokeAccountAccess(targetIdOrSxId: string): boolean {
  const records = getStoredAccessRecords();
  const nowStr = new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC";
  let changed = false;

  const updated = records.map((r) => {
    const match =
      (r.sxId && r.sxId.toUpperCase() === targetIdOrSxId.toUpperCase()) ||
      (r.accessId && r.accessId.toUpperCase() === targetIdOrSxId.toUpperCase()) ||
      r.id === targetIdOrSxId;
    if (match) {
      changed = true;
      const updatedHistory: ActivationIssuance[] = (r.activationHistory || []).map((iss) => {
        if (iss.status === "INVITED") {
          return { ...iss, status: "REVOKED" as ActivationStatus, revokedAt: nowStr };
        }
        return iss;
      });

      return {
        ...r,
        accountStatus: "REVOKED" as AccountAccessStatus,
        activationStatus: r.activationStatus === "INVITED" ? ("REVOKED" as ActivationStatus) : r.activationStatus,
        status: "REVOKED" as AccessStatus,
        activationHistory: updatedHistory,
        history: [
          ...r.history,
          { time: nowStr, action: "ACCOUNT_REVOKED", actor: "OWNER-001 (Account access revoked permanently)" },
        ],
      };
    }
    return r;
  });

  if (changed) saveStoredAccessRecords(updated);
  return changed;
}

export const revokeAccessRecord = revokeAccountAccess;


export function suspendAccessRecord(accessId: string): boolean {
  const records = getStoredAccessRecords();
  const now = new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC";
  let changed = false;

  const updated = records.map((r) => {
    const match =
      (r.sxId && r.sxId.toUpperCase() === accessId.toUpperCase()) ||
      (r.accessId && r.accessId.toUpperCase() === accessId.toUpperCase()) ||
      r.id === accessId;
    if (match) {
      changed = true;
      return {
        ...r,
        accountStatus: "SUSPENDED" as AccountAccessStatus,
        status: "SUSPENDED" as AccessStatus,
        history: [...r.history, { time: now, action: "ACCOUNT_SUSPENDED", actor: "OWNER-001 (Temporary Suspension)" }],
      };
    }
    return r;
  });

  if (changed) saveStoredAccessRecords(updated);
  return changed;
}

export function restoreAccessRecord(accessId: string): boolean {
  const records = getStoredAccessRecords();
  const now = new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC";
  let changed = false;

  const updated = records.map((r) => {
    const match =
      (r.sxId && r.sxId.toUpperCase() === accessId.toUpperCase()) ||
      (r.accessId && r.accessId.toUpperCase() === accessId.toUpperCase()) ||
      r.id === accessId;
    if (match) {
      changed = true;
      const restoredAccountStatus: AccountAccessStatus = r.redeemedAt ? "ACTIVE" : "PENDING";
      const restoredStatus: AccessStatus = r.redeemedAt ? "ACTIVE" : (r.activationStatus === "INVITED" ? "INVITED" : "DRAFT");
      return {
        ...r,
        accountStatus: restoredAccountStatus,
        status: restoredStatus,
        history: [...r.history, { time: now, action: "ACCOUNT_RESTORED", actor: "OWNER-001 (Restored from Suspension)" }],
      };
    }
    return r;
  });

  if (changed) saveStoredAccessRecords(updated);
  return changed;
}

export function deleteDraftAccessRecord(accessId: string): boolean {
  const records = getStoredAccessRecords();
  const target = records.find(
    (r) =>
      (r.sxId && r.sxId.toUpperCase() === accessId.toUpperCase()) ||
      (r.accessId && r.accessId.toUpperCase() === accessId.toUpperCase()) ||
      r.id === accessId
  );
  if (!target || target.activationStatus !== "DRAFT") return false;

  const updated = records.filter(
    (r) =>
      r.sxId.toUpperCase() !== accessId.toUpperCase() &&
      r.accessId?.toUpperCase() !== accessId.toUpperCase() &&
      r.id !== accessId
  );
  saveStoredAccessRecords(updated);
  return true;
}

