/**
 * SentinelX Dashboard V3 — Connections, Broker Feeds & Plugins Domain
 */
import type { Truth } from "../../shared/data/sharedTypes";
import { STORAGE_KEYS, prototypeFixtureStorage, safeGetJson, safeSetJson } from "../../shared/data/storage";

const localStorage = prototypeFixtureStorage;

export type ConnectionHealthStatus = "HEALTHY" | "DEGRADED" | "OFFLINE" | "UNKNOWN";
export type ConnectionAuthStatus = "NOT_CONFIGURED" | "CONFIGURED" | "AUTH_REQUIRED" | "EXPIRED";
export type ConnectionOwnerAllowance = "ALLOWED" | "HOLD";
export type ConnectionCapability =
  | "HISTORICAL_DATA"
  | "LIVE_MARKET_DATA"
  | "ORDER_EXECUTION"
  | "PAPER_TRADING"
  | "PORTFOLIO_READ"
  | "NOTIFICATIONS";

export type CapabilitySystemStatus = "READY" | "DEGRADED" | "UNSUPPORTED" | "OFFLINE";
export type CapabilityAuthStatus = "AUTHORIZED" | "BLOCKED_AUTH" | "EXPIRED" | "NOT_CONFIGURED";
export type CapabilityOwnerAllowance = "ALLOWED" | "HOLD";
export type CapabilityEffectiveStatus = "AVAILABLE" | "BLOCKED";

export interface ConnectionCapabilityDetail {
  capability: ConnectionCapability;
  name: string;
  systemStatus: CapabilitySystemStatus;
  authStatus: CapabilityAuthStatus;
  ownerAllowance: CapabilityOwnerAllowance;
  effectiveStatus: CapabilityEffectiveStatus;
  blockerReason?: string;
}

export interface OwnerConnectionRow {
  id: string;
  connectionId: string;
  name: string;
  provider: string;
  type: "Broker" | "Market Data" | "Notification" | "Other";
  environment: "Paper / Sandbox" | "Live" | "Both";
  accountAlias: string;
  secretRef: string; // Sealed reference e.g. "ak •••• ••7f"
  authState: ConnectionAuthStatus;
  healthState: ConnectionHealthStatus;
  latencyMs: number;
  lastCheck: string;
  ownerAllowance: ConnectionOwnerAllowance;
  ownerHoldReason?: string;
  capabilities: ConnectionCapabilityDetail[];
  events: { time: string; text: string; tone?: "ok" | "warn" | "neg" | "dim" }[];
}

export function computeCapabilityEffective(
  connectionHealth: ConnectionHealthStatus,
  connectionAllowance: ConnectionOwnerAllowance,
  cap: {
    systemStatus: CapabilitySystemStatus;
    authStatus: CapabilityAuthStatus;
    ownerAllowance: CapabilityOwnerAllowance;
    blockerReason?: string;
  }
): { status: CapabilityEffectiveStatus; label: string; tone: "ok" | "warn" | "neg" | "dim"; blocker?: string } {
  if (connectionAllowance !== "ALLOWED") {
    return {
      status: "BLOCKED",
      label: "BLOCKED (CONN HOLD)",
      tone: "warn",
      blocker: "Connection placed on administrative hold by Owner.",
    };
  }
  if (connectionHealth === "OFFLINE") {
    return {
      status: "BLOCKED",
      label: "BLOCKED (OFFLINE)",
      tone: "neg",
      blocker: "Connection transport adapter is offline.",
    };
  }
  if (cap.ownerAllowance !== "ALLOWED") {
    return {
      status: "BLOCKED",
      label: "BLOCKED (CAP HOLD)",
      tone: "warn",
      blocker: "Capability placed on administrative hold by Owner.",
    };
  }
  if (cap.systemStatus === "UNSUPPORTED" || cap.systemStatus === "OFFLINE") {
    return {
      status: "BLOCKED",
      label: `BLOCKED (${cap.systemStatus})`,
      tone: "neg",
      blocker: cap.blockerReason || `Capability is ${cap.systemStatus.toLowerCase()} by provider adapter.`,
    };
  }
  if (cap.authStatus !== "AUTHORIZED") {
    const reasonTag = cap.authStatus === "EXPIRED" ? "EXPIRED" : cap.authStatus === "BLOCKED_AUTH" ? "AUTH REQUIRED" : "NOT CONFIGURED";
    return {
      status: "BLOCKED",
      label: `BLOCKED (${reasonTag})`,
      tone: cap.authStatus === "EXPIRED" ? "warn" : "neg",
      blocker: cap.blockerReason || (cap.authStatus === "EXPIRED" ? "Session token expired. Re-auth required." : "Requires elevated trading permissions or API provisioning."),
    };
  }
  return {
    status: "AVAILABLE",
    label: cap.systemStatus === "DEGRADED" ? "AVAILABLE (DEGRADED)" : "AVAILABLE",
    tone: cap.systemStatus === "DEGRADED" ? "warn" : "ok",
  };
}

export const INITIAL_OWNER_CONNECTIONS: OwnerConnectionRow[] = [];

const OWNER_CONNECTIONS_KEY = STORAGE_KEYS.OWNER_CONNECTIONS;

export function getStoredOwnerConnections(): OwnerConnectionRow[] {
  try {
    const raw = localStorage.getItem(OWNER_CONNECTIONS_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed;
    return [];
  } catch {
    return [];
  }
}

export function saveOwnerConnections(conns: OwnerConnectionRow[]): void {
  try {
    localStorage.setItem(OWNER_CONNECTIONS_KEY, JSON.stringify(conns));
  } catch (err) {
    console.error("Failed to save connections", err);
  }
}

export function updateOwnerConnectionAllowance(
  connectionId: string,
  allowance: ConnectionOwnerAllowance,
  reason?: string,
  actor: string = "OWNER-001"
): { success: boolean; message: string } {
  const current = getStoredOwnerConnections();
  const index = current.findIndex((c) => c.id === connectionId || c.connectionId === connectionId);
  if (index === -1) return { success: false, message: "Connection not found" };

  const conn = { ...current[index] };
  conn.ownerAllowance = allowance;
  if (allowance === "HOLD") {
    conn.ownerHoldReason = reason || `Placed on hold by ${actor}`;
  } else {
    delete conn.ownerHoldReason;
  }

  // Recalculate per-capability effective statuses
  conn.capabilities = conn.capabilities.map((cap) => {
    const eff = computeCapabilityEffective(conn.healthState, conn.ownerAllowance, cap);
    return { ...cap, effectiveStatus: eff.status, blockerReason: eff.blocker || cap.blockerReason };
  });

  conn.events = [
    {
      time: new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC",
      text: `Owner set connection allowance to ${allowance} by ${actor}`,
      tone: allowance === "ALLOWED" ? "ok" : "warn",
    },
    ...conn.events,
  ];

  current[index] = conn;
  saveOwnerConnections(current);

  const availableCount = conn.capabilities.filter((c) => c.effectiveStatus === "AVAILABLE").length;
  let msg = `Connection "${conn.name}" allowance set to ${allowance}. (${availableCount}/${conn.capabilities.length} capabilities effectively available)`;
  return { success: true, message: msg };
}

export function updateCapabilityAllowance(
  connectionId: string,
  capKey: ConnectionCapability,
  allowance: CapabilityOwnerAllowance,
  reason?: string,
  actor: string = "OWNER-001"
): { success: boolean; message: string } {
  const current = getStoredOwnerConnections();
  const index = current.findIndex((c) => c.id === connectionId || c.connectionId === connectionId);
  if (index === -1) return { success: false, message: "Connection not found" };

  const conn = { ...current[index] };
  conn.capabilities = conn.capabilities.map((c) => {
    if (c.capability === capKey) {
      const updated = { ...c, ownerAllowance: allowance };
      const eff = computeCapabilityEffective(conn.healthState, conn.ownerAllowance, updated);
      return { ...updated, effectiveStatus: eff.status, blockerReason: eff.blocker || updated.blockerReason };
    }
    return c;
  });

  conn.events = [
    {
      time: new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC",
      text: `Owner set capability "${capKey}" allowance to ${allowance} by ${actor}`,
      tone: allowance === "ALLOWED" ? "ok" : "warn",
    },
    ...conn.events,
  ];

  current[index] = conn;
  saveOwnerConnections(current);
  return { success: true, message: `Capability "${capKey}" allowance updated to ${allowance}.` };
}

export type PluginCategory = "Protective Risk" | "Market Data Feed" | "Notification & Audit" | "Analytics & Features";
export type PluginDiscoveryState = "BUILTIN" | "DISCOVERED" | "USER_EXT";
export type PluginCompatibilityStatus = "COMPATIBLE" | "INCOMPATIBLE" | "PENDING_SCAN";
export type PluginPermissionReadiness = "PERMISSIONS_READY" | "PERMISSIONS_BLOCKED";
export type PluginOwnerAllowance = "ALLOWED" | "HOLD";
export type PluginEffectiveStatus = "ACTIVE" | "BLOCKED";

export interface OwnerPluginRow {
  id: string;
  pluginId: string;
  name: string;
  version: string;
  category: PluginCategory;
  author: string;
  discoveryState: PluginDiscoveryState;
  compatibilityStatus: PluginCompatibilityStatus;
  compatibilityDetails?: string;
  permissionReadiness: PluginPermissionReadiness;
  permissionBlockerReason?: string;
  ownerAllowance: PluginOwnerAllowance;
  ownerHoldReason?: string;
  effectiveStatus: PluginEffectiveStatus;
  capabilities: string[];
  permissions: string[];
  lastValidation: string;
  description: string;
  auditHistory: { time: string; action: string; actor: string; note: string; tone?: "ok" | "warn" | "neg" | "dim" }[];
}

export function computePluginEffective(
  compatibility: PluginCompatibilityStatus,
  permissionReadiness: PluginPermissionReadiness,
  allowance: PluginOwnerAllowance
): { status: PluginEffectiveStatus; label: string; tone: "ok" | "warn" | "neg" | "dim"; reason: string } {
  if (compatibility !== "COMPATIBLE") {
    return {
      status: "BLOCKED",
      label: "BLOCKED (COMPATIBILITY ERROR)",
      tone: "neg",
      reason: "Plugin fails AlgoFortis architecture compatibility & ABI verification.",
    };
  }
  if (permissionReadiness !== "PERMISSIONS_READY") {
    return {
      status: "BLOCKED",
      label: "BLOCKED (PERMISSION ERROR)",
      tone: "neg",
      reason: "Plugin requires elevated permissions that are not provisioned.",
    };
  }
  if (allowance !== "ALLOWED") {
    return {
      status: "BLOCKED",
      label: "BLOCKED (OWNER HOLD)",
      tone: "warn",
      reason: "Placed on administrative hold by Owner.",
    };
  }
  return {
    status: "ACTIVE",
    label: "ACTIVE",
    tone: "ok",
    reason: "Compatible, permissions ready, and Owner allowed.",
  };
}

export const INITIAL_OWNER_PLUGINS: OwnerPluginRow[] = [];

const OWNER_PLUGINS_KEY = STORAGE_KEYS.OWNER_PLUGINS;

export function getStoredOwnerPlugins(): OwnerPluginRow[] {
  try {
    const raw = localStorage.getItem(OWNER_PLUGINS_KEY);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed;
    return [];
  } catch {
    return [];
  }
}

export function saveOwnerPlugins(plugins: OwnerPluginRow[]): void {
  try {
    localStorage.setItem(OWNER_PLUGINS_KEY, JSON.stringify(plugins));
  } catch (err) {
    console.error("Failed to save plugins", err);
  }
}

export function updateOwnerPluginAllowance(
  pluginId: string,
  allowance: PluginOwnerAllowance,
  reason?: string,
  actor: string = "OWNER-001"
): { success: boolean; effective: PluginEffectiveStatus; message: string } {
  const current = getStoredOwnerPlugins();
  const index = current.findIndex((p) => p.id === pluginId || p.pluginId === pluginId);
  if (index === -1) return { success: false, effective: "BLOCKED", message: "Plugin not found" };

  const plug = { ...current[index] };
  plug.ownerAllowance = allowance;
  if (allowance === "HOLD") {
    plug.ownerHoldReason = reason || `Placed on hold by ${actor}`;
  } else {
    delete plug.ownerHoldReason;
  }

  const computed = computePluginEffective(plug.compatibilityStatus, plug.permissionReadiness, plug.ownerAllowance);
  plug.effectiveStatus = computed.status;

  plug.auditHistory = [
    {
      time: new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC",
      action: `OWNER_ALLOWANCE_${allowance}`,
      actor,
      note: `Owner set allowance to ${allowance} (Effective: ${computed.label})`,
      tone: computed.status === "ACTIVE" ? "ok" : "warn",
    },
    ...plug.auditHistory,
  ];

  current[index] = plug;
  saveOwnerPlugins(current);

  let msg = `Plugin "${plug.name}" allowance set to ${allowance}.`;
  if (allowance === "ALLOWED" && computed.status === "BLOCKED") {
    msg += ` Effective status remains BLOCKED (${computed.reason}).`;
  }
  return { success: true, effective: computed.status, message: msg };
}
