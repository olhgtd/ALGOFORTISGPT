/**
 * AlgoFortis Owner Dashboard — Security Authority, Zero-Trust Sessions & Hardware Sensors
 */
import type { Truth } from "../../shared/data/sharedTypes";
import { STORAGE_KEYS, prototypeFixtureStorage, safeGetJson, safeSetJson } from "../../shared/data/storage";

const localStorage = prototypeFixtureStorage;

const OWNER_SESSIONS_KEY = STORAGE_KEYS.OWNER_SESSIONS;
const OWNER_DEVICES_KEY = STORAGE_KEYS.OWNER_DEVICES;

export type AuthMethodType = "FIDO2_WEBAUTHN" | "PASSWORD_OTP" | "RECOVERY_CEREMONY";
export type SessionStatusType = "ACTIVE" | "REVOKED" | "EXPIRED";
export type DeviceTrustStatus = "TRUSTED_REGISTERED" | "REVOKED";
export type RecoveryHealthStatus = "HEALTHY" | "LOW" | "NONE";
export type RecoveryWarningLevel = "NONE" | "WARNING" | "STRONG_WARNING" | "PERSISTENT_CRITICAL";

export interface OwnerSessionRow {
  id: string;
  sessionRef: string; // Masked session identifier (e.g. "SES-****-8821")
  sxId: string;
  userName: string;
  role: string;
  deviceRef: string;
  deviceName: string;
  ipMasked: string;
  location: string;
  authMethod: AuthMethodType;
  isCurrent: boolean;
  status: SessionStatusType;
  createdAt: string;
  lastActive: string;
  expiresAt: string;
  context: "NORMAL" | "RECOVERY_ASSURANCE_WINDOW";
  clientType: string;
}

export interface OwnerDeviceRow {
  id: string;
  deviceId: string;
  sxId: string;
  userName: string;
  deviceName: string;
  platform: string;
  authenticatorType: string;
  credentialIdMasked: string; // Masked reference (zero secrets exposed)
  registeredAt: string;
  lastSeen: string;
  status: DeviceTrustStatus;
  activeSessionCount: number;
  revokedAt?: string;
  revokedReason?: string;
}

export interface OwnerRecoveryPosture {
  sxId: string;
  userName: string;
  role: string;
  codesConfigured: boolean;
  codesRemaining: number;
  readinessStatus: RecoveryHealthStatus;
  lastRegeneratedAt: string;
  primaryEmail: string;
  primaryEmailVerified: boolean;
  secondaryPhone: string;
  secondaryPhoneVerified: boolean;
  recoveryAssuranceState: "INACTIVE" | "ACTIVE_SAMPLE";
  recoveryAssuranceExpiresIn?: string;
  warningLevel: RecoveryWarningLevel;
}

export const INITIAL_OWNER_SESSIONS: OwnerSessionRow[] = [];

export const INITIAL_OWNER_DEVICES: OwnerDeviceRow[] = [];



export function getStoredOwnerSessions(): OwnerSessionRow[] {
  try {
    const raw = localStorage.getItem(OWNER_SESSIONS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveStoredOwnerSessions(sessions: OwnerSessionRow[]): void {
  try {
    localStorage.setItem(OWNER_SESSIONS_KEY, JSON.stringify(sessions));
  } catch (err) {
    console.error("Failed to save owner sessions prototype state", err);
  }
}

export function revokeOwnerSessionSimulated(sessionId: string): { success: boolean; message: string; isSimulated: true } {
  const sessions = getStoredOwnerSessions();
  const target = sessions.find((s) => s.id === sessionId);
  if (!target) return { success: false, message: "Session not found", isSimulated: true };

  const updated = sessions.map((s) => {
    if (s.id === sessionId) {
      return { ...s, status: "REVOKED" as SessionStatusType, isCurrent: false };
    }
    return s;
  });
  saveStoredOwnerSessions(updated);

  // Decrement active session count on matching device
  const devices = getStoredOwnerDevices();
  const updatedDevices = devices.map((d) => {
    if (d.deviceId === target.deviceRef && d.activeSessionCount > 0) {
      return { ...d, activeSessionCount: Math.max(0, d.activeSessionCount - 1) };
    }
    return d;
  });
  saveStoredOwnerDevices(updatedDevices);

  return {
    success: true,
    message: `SIMULATED SECURITY REQUEST: Session ${target.sessionRef} for ${target.userName} revoked locally in prototype state. (DEV PREVIEW / SAMPLE)`,
    isSimulated: true,
  };
}

export function revokeAllOwnerSessionsSimulated(sxId: string): { success: boolean; message: string; count: number; isSimulated: true } {
  const sessions = getStoredOwnerSessions();
  let count = 0;
  const updated = sessions.map((s) => {
    if (s.sxId.toUpperCase() === sxId.toUpperCase() && s.status === "ACTIVE") {
      count++;
      return { ...s, status: "REVOKED" as SessionStatusType, isCurrent: false };
    }
    return s;
  });
  saveStoredOwnerSessions(updated);

  // Reset active session counts for devices of this user
  const devices = getStoredOwnerDevices();
  const updatedDevices = devices.map((d) => {
    if (d.sxId.toUpperCase() === sxId.toUpperCase()) {
      return { ...d, activeSessionCount: 0 };
    }
    return d;
  });
  saveStoredOwnerDevices(updatedDevices);

  return {
    success: true,
    message: `SIMULATED SECURITY REQUEST: All ${count} active session(s) for ${sxId} revoked locally in prototype state. (DEV PREVIEW / SAMPLE)`,
    count,
    isSimulated: true,
  };
}

export function getStoredOwnerDevices(): OwnerDeviceRow[] {
  try {
    const raw = localStorage.getItem(OWNER_DEVICES_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveStoredOwnerDevices(devices: OwnerDeviceRow[]): void {
  try {
    localStorage.setItem(OWNER_DEVICES_KEY, JSON.stringify(devices));
  } catch (err) {
    console.error("Failed to save owner devices prototype state", err);
  }
}

export function revokeOwnerDeviceSimulated(deviceId: string, reason: string = "Owner administrative device revocation"): { success: boolean; message: string; isSimulated: true } {
  const devices = getStoredOwnerDevices();
  const nowStr = new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC";
  const target = devices.find((d) => d.deviceId === deviceId || d.id === deviceId);
  if (!target) return { success: false, message: "Device not found", isSimulated: true };

  const updated = devices.map((d) => {
    if (d.deviceId === target.deviceId) {
      return {
        ...d,
        status: "REVOKED" as DeviceTrustStatus,
        activeSessionCount: 0,
        revokedAt: nowStr,
        revokedReason: reason,
      };
    }
    return d;
  });
  saveStoredOwnerDevices(updated);

  // Terminate any active sessions on this revoked device
  const sessions = getStoredOwnerSessions();
  const updatedSessions = sessions.map((s) => {
    if (s.deviceRef === target.deviceId && s.status === "ACTIVE") {
      return { ...s, status: "REVOKED" as SessionStatusType, isCurrent: false };
    }
    return s;
  });
  saveStoredOwnerSessions(updatedSessions);

  return {
    success: true,
    message: `SIMULATED SECURITY REQUEST: Device ${target.deviceId} (${target.deviceName}) revoked and archived in historical ledger. (DEV PREVIEW / SAMPLE)`,
    isSimulated: true,
  };
}

export function revokeAllUserDevicesSimulated(sxId: string, reason: string = "High-Assurance Recovery Device Purge (OD-AUTH-08)"): { success: boolean; message: string; count: number; isSimulated: true } {
  const devices = getStoredOwnerDevices();
  const nowStr = new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC";
  let count = 0;

  const updated = devices.map((d) => {
    if (d.sxId.toUpperCase() === sxId.toUpperCase() && d.status === "TRUSTED_REGISTERED") {
      count++;
      return {
        ...d,
        status: "REVOKED" as DeviceTrustStatus,
        activeSessionCount: 0,
        revokedAt: nowStr,
        revokedReason: reason,
      };
    }
    return d;
  });
  saveStoredOwnerDevices(updated);

  // Terminate active sessions for this user
  revokeAllOwnerSessionsSimulated(sxId);

  return {
    success: true,
    message: `SIMULATED SECURITY REQUEST: ${count} active registered device(s) revoked for ${sxId}. Historical records retained. (DEV PREVIEW / SAMPLE)`,
    count,
    isSimulated: true,
  };
}
