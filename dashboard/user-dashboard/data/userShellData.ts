import {
  listUserConnections,
  listUserDeployments,
  liveReadinessRequest,
  queryPersistenceHealth,
  type LiveReadiness,
  type UserConnection,
  type UserDeployment,
} from "../../shared/services/integrationClient";
import type { UserNotification } from "../components/NotificationCenter";
import { queryUserMarketChart } from "./userMarketAuthority";
import {
  deriveUserShellStatus,
  type AuthorityState,
  type AutomationState,
  type BrokerState,
  type TradingMode,
  type UserShellStatus,
} from "../shellState";

export interface UserRiskAuthority {
  state: AuthorityState;
  level: string | null;
  reasons: string[];
}

export interface UserShellAuthorityData {
  status: UserShellStatus;
  notifications: UserNotification[];
  risk: UserRiskAuthority;
}

export interface UserShellAuthorityQueries {
  persistenceQuery?: typeof queryPersistenceHealth;
  marketQuery?: typeof queryUserMarketChart;
  connectionsQuery?: typeof listUserConnections;
  deploymentsQuery?: typeof listUserDeployments;
  liveReadinessQuery?: () => Promise<LiveReadiness>;
}

const upper = (value: unknown): string => typeof value === "string" ? value.trim().toUpperCase() : "";

const deploymentMode = (deployment: UserDeployment): TradingMode | null => {
  const raw = upper(deployment.executionMode ?? deployment.execution_mode);
  if (raw === "BACKTEST") return "BACKTEST";
  if (raw === "PAPER" || raw === "LIVE_PAPER") return "PAPER";
  if (raw === "LIVE") return "LIVE";
  return null;
};

const automationPriority: readonly AutomationState[] = [
  "RECOVERY",
  "HALTED",
  "HALT_ENTRIES",
  "READY_FOR_RESUME",
  "PAUSED",
  "RUNNING",
  "STOPPED",
];

const automationState = (deployments: readonly UserDeployment[]): AutomationState => {
  const states = new Set(deployments.map((deployment) => upper(deployment.status)));
  return automationPriority.find((candidate) => states.has(candidate)) ?? "UNKNOWN";
};

export function deriveDeploymentShell(deployments: readonly UserDeployment[]): {
  mode: TradingMode;
  automationState: AutomationState;
} {
  const nonStopped = deployments.filter((deployment) => !["STOPPED", "COMPLETED", "CANCELLED", "ARCHIVED"].includes(upper(deployment.status)));
  const modes = new Set(nonStopped.map(deploymentMode).filter((mode): mode is TradingMode => mode !== null));
  return {
    mode: modes.size === 1 ? [...modes][0] : "UNKNOWN",
    automationState: automationState(deployments),
  };
}

export function deriveBrokerState(authority: "AVAILABLE" | "UNAVAILABLE", connections: readonly UserConnection[]): BrokerState {
  if (authority !== "AVAILABLE") return "UNAVAILABLE";
  if (connections.length === 0) return "DISCONNECTED";
  const needsAttention = connections.some((connection) => {
    const status = upper(connection.status);
    const health = upper(connection.healthState);
    return connection.suspended
      || ["ERROR", "FAILED", "EXPIRED", "AUTH_EXPIRED", "SUSPENDED", "NEEDS_ATTENTION"].includes(status)
      || ["ERROR", "FAILED", "DEGRADED", "EXPIRED", "AUTH_EXPIRED", "NEEDS_ATTENTION"].includes(health);
  });
  if (needsAttention) return "NEEDS_ATTENTION";
  const connected = connections.some((connection) =>
    ["CONNECTED", "ACTIVE", "READY"].includes(upper(connection.status))
    || ["CONNECTED", "HEALTHY", "READY"].includes(upper(connection.healthState)));
  return connected ? "CONNECTED" : "DISCONNECTED";
}

const engineStateFromPersistence = (result: Awaited<ReturnType<typeof queryPersistenceHealth>> | null): AuthorityState => {
  if (!result || result.source !== "BACKEND") return "UNAVAILABLE";
  if (result.trust === "FRESH") return "AVAILABLE";
  if (result.trust === "STALE") return "STALE";
  return "UNKNOWN";
};

const marketAuthorityState = (results: Array<Awaited<ReturnType<typeof queryUserMarketChart>> | null>): AuthorityState => {
  const states = results.map((result) => result?.state ?? "BACKEND_UNAVAILABLE");
  if (states.some((state) => state === "STALE")) return "STALE";
  if (states.length > 0 && states.every((state) => state === "AVAILABLE")) return "AVAILABLE";
  if (states.some((state) => state === "AVAILABLE")) return "UNKNOWN";
  if (states.every((state) => ["BACKEND_UNAVAILABLE", "DATA_PROVIDER_NOT_CONFIGURED", "NO_DATA", "ERROR"].includes(state))) return "UNAVAILABLE";
  return "UNKNOWN";
};

const liveBrokerState = (readiness: LiveReadiness | null): BrokerState | null => {
  if (!readiness) return null;
  const connection = upper(readiness.connection_state);
  if (["ERROR", "FAILED", "AUTH_EXPIRED", "SUSPENDED", "DEGRADED", "NEEDS_ATTENTION"].includes(connection)) return "NEEDS_ATTENTION";
  if (connection === "CONNECTED") return "CONNECTED";
  if (["DISCONNECTED", "NOT_CONNECTED", "UNCONFIGURED"].includes(connection)) return "DISCONNECTED";
  return "UNKNOWN";
};

const combineBrokerState = (connections: BrokerState, live: BrokerState | null): BrokerState => {
  if (connections === "NEEDS_ATTENTION" || live === "NEEDS_ATTENTION") return "NEEDS_ATTENTION";
  if (live === "CONNECTED" || connections === "CONNECTED") return "CONNECTED";
  if (connections === "UNAVAILABLE" && live === null) return "UNAVAILABLE";
  if (live === "UNKNOWN" || connections === "UNKNOWN") return "UNKNOWN";
  if (live === "DISCONNECTED" || connections === "DISCONNECTED") return "DISCONNECTED";
  return connections;
};

const riskAuthority = (readiness: LiveReadiness | null): UserRiskAuthority => {
  const level = readiness ? upper(readiness.risk_state) : "";
  if (!readiness || !level || level === "UNKNOWN" || level === "UNAVAILABLE") {
    return { state: "UNKNOWN", level: null, reasons: [] };
  }
  const reasons: string[] = [];
  if (readiness.execution_policy?.global_hold) reasons.push("Global execution hold is active.");
  if (readiness.execution_policy?.safe_mode) reasons.push("Safe mode is active.");
  const reconciliation = upper(readiness.reconciliation?.state);
  if (reconciliation && reconciliation !== "CLEAN") reasons.push(`Reconciliation: ${reconciliation}.`);
  if (readiness.execution_policy?.arming_state === "READ_ONLY") reasons.push("Live execution remains READ_ONLY / DISARMED.");
  return { state: "AVAILABLE", level, reasons };
};

const notificationCounts = (notifications: readonly UserNotification[]) => ({
  critical: notifications.filter((item) => item.priority === "Critical").length,
  actionRequired: notifications.filter((item) => item.priority === "Action Required").length,
  important: notifications.filter((item) => item.priority === "Important").length,
  info: notifications.filter((item) => item.priority === "Info").length,
});

const attentionNotices = (
  shell: { mode: TradingMode; automationState: AutomationState; brokerState: BrokerState; engineState: AuthorityState; dataFreshness: AuthorityState },
  risk: UserRiskAuthority,
  connections: readonly UserConnection[],
): UserNotification[] => {
  const notices: UserNotification[] = [];
  if (["HALT_ENTRIES", "HALTED", "RECOVERY", "READY_FOR_RESUME"].includes(shell.automationState)) {
    notices.push({ id: `automation-${shell.automationState.toLowerCase()}`, priority: "Action Required", title: "Manual resume required", detail: `Operational state is ${shell.automationState}. AlgoFortis will not infer or auto-resume entry permission.` });
  }
  if (shell.brokerState === "NEEDS_ATTENTION") {
    notices.push({ id: "broker-needs-attention", priority: "Action Required", title: "Broker connection needs attention", detail: "Authoritative connection health reports a suspended, degraded, expired, or failed state." });
  }
  if (shell.engineState === "UNAVAILABLE") {
    notices.push({ id: "engine-unavailable", priority: "Critical", title: "Engine authority unavailable", detail: "Persistence/runtime authority could not be verified. UNKNOWN is not treated as healthy." });
  } else if (shell.engineState === "STALE") {
    notices.push({ id: "engine-stale", priority: "Important", title: "Engine health evidence is stale", detail: "The latest authoritative engine health evidence is stale." });
  }
  if (shell.dataFreshness === "STALE") {
    notices.push({ id: "market-data-stale", priority: "Important", title: "Market data is stale", detail: "Canonical market authority reports stale data; stale values are labelled and never promoted to fresh." });
  } else if (shell.dataFreshness === "UNAVAILABLE") {
    notices.push({ id: "market-data-unavailable", priority: "Important", title: "Market data authority unavailable", detail: "Canonical market data could not be verified. No sample prices are substituted." });
  }
  for (const connection of connections.filter((item) => item.suspended && item.suspendReason)) {
    notices.push({ id: `connection-${connection.connectionId}`, priority: "Important", title: `${connection.provider} connection suspended`, detail: connection.suspendReason ?? undefined, asOf: connection.lastVerifiedAtUtc ?? undefined });
  }
  if (risk.state === "AVAILABLE" && risk.level && !["HEALTHY", "OK", "CLEAR"].includes(risk.level)) {
    notices.push({ id: `risk-${risk.level.toLowerCase()}`, priority: "Important", title: `Risk authority reports ${risk.level}`, detail: risk.reasons.join(" ") || "Review authoritative risk state before continuing." });
  }
  if (shell.mode === "LIVE") {
    notices.push({ id: "live-read-only", priority: "Info", title: "Live remains READ_ONLY / DISARMED", detail: "Broker connectivity never grants execution authority from the user dashboard." });
  }
  return notices;
};

export async function loadUserShellAuthority(queries: UserShellAuthorityQueries = {}): Promise<UserShellAuthorityData> {
  const persistenceQuery = queries.persistenceQuery ?? queryPersistenceHealth;
  const marketQuery = queries.marketQuery ?? queryUserMarketChart;
  const connectionsQuery = queries.connectionsQuery ?? listUserConnections;
  const deploymentsQuery = queries.deploymentsQuery ?? listUserDeployments;
  const readinessQuery = queries.liveReadinessQuery ?? (() => liveReadinessRequest<LiveReadiness>("/api/v1/user/live-readiness"));

  const [persistence, nifty, bankNifty, connectionsResult, deploymentsResult, readiness] = await Promise.all([
    persistenceQuery().catch(() => null),
    marketQuery({ instrument: "NIFTY", timeframe: "5m", mode: "LIVE", limit: 2 }).catch(() => null),
    marketQuery({ instrument: "BANKNIFTY", timeframe: "5m", mode: "LIVE", limit: 2 }).catch(() => null),
    connectionsQuery().catch(() => null),
    deploymentsQuery().catch(() => null),
    readinessQuery().catch(() => null),
  ]);

  const connectionsAvailable = connectionsResult?.source === "BACKEND" ? "AVAILABLE" as const : "UNAVAILABLE" as const;
  const connections = connectionsAvailable === "AVAILABLE" ? connectionsResult!.data : [];
  const deployments = deploymentsResult?.source === "BACKEND" ? deploymentsResult.data : [];
  const deployment = deploymentsResult?.source === "BACKEND" ? deriveDeploymentShell(deployments) : { mode: "UNKNOWN" as const, automationState: "UNKNOWN" as const };
  const brokerState = combineBrokerState(deriveBrokerState(connectionsAvailable, connections), liveBrokerState(readiness));
  const risk = riskAuthority(readiness);
  const shellInput = { ...deployment, brokerState, engineState: engineStateFromPersistence(persistence), dataFreshness: marketAuthorityState([nifty, bankNifty]) };
  const notifications = attentionNotices(shellInput, risk, connections);

  return {
    status: deriveUserShellStatus({ ...shellInput, notifications: notificationCounts(notifications) }),
    notifications,
    risk,
  };
}
