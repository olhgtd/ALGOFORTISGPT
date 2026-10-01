import {
  listUserConnections,
  listUserDeployments,
  listWalkForwardJobs,
  queryBacktestRuns,
  queryCurrentUserProfile,
  queryOrdersPortfolio,
  queryReports,
  queryStrategyReadiness,
  queryUserStrategyRegistry,
  type AuthoritativeBacktestRun,
  type AuthoritativeReportItem,
  type OrdersPortfolioSnapshot,
  type StrategyReadiness,
  type UserConnection,
  type UserDeployment,
  type UserProfileData,
  type UserStrategyEntry,
  type WalkForwardJob,
} from "../../shared/services/integrationClient";

export type UserSurfaceAuthorityState = "AVAILABLE" | "STALE" | "UNKNOWN" | "UNAVAILABLE";

export interface AuthorityBlock<T> {
  state: UserSurfaceAuthorityState;
  data: T;
  asOf: string | null;
}

export interface StrategySurfaceItem {
  entry: UserStrategyEntry;
  readiness: StrategyReadiness | null;
  deployments: UserDeployment[];
}

export interface StrategiesSurfaceData {
  state: UserSurfaceAuthorityState;
  strategies: StrategySurfaceItem[];
  deploymentsState: UserSurfaceAuthorityState;
  asOf: string | null;
}

export interface TestingSurfaceData {
  backtests: AuthorityBlock<AuthoritativeBacktestRun[]>;
  walkForward: AuthorityBlock<WalkForwardJob[]>;
  reports: AuthorityBlock<AuthoritativeReportItem[]>;
}

export interface RuntimeSurfaceBlock {
  state: UserSurfaceAuthorityState;
  snapshot: OrdersPortfolioSnapshot | null;
}

export interface TradingSurfaceData {
  PAPER: RuntimeSurfaceBlock;
  LIVE: RuntimeSurfaceBlock;
}

export interface AccountSurfaceData {
  profile: AuthorityBlock<UserProfileData | null>;
  connections: AuthorityBlock<UserConnection[]>;
}

const unavailable = <T,>(data: T): AuthorityBlock<T> => ({
  state: "UNAVAILABLE",
  data,
  asOf: null,
});

const authorityState = (result: { source?: string; trust?: string } | null | undefined): UserSurfaceAuthorityState => {
  if (!result || result.source !== "BACKEND") return "UNAVAILABLE";
  if (result.trust === "FRESH") return "AVAILABLE";
  if (result.trust === "STALE") return "STALE";
  return "UNKNOWN";
};

export async function loadStrategiesSurface(
  registryQuery: typeof queryUserStrategyRegistry = queryUserStrategyRegistry,
  deploymentsQuery: typeof listUserDeployments = listUserDeployments,
  readinessQuery: typeof queryStrategyReadiness = queryStrategyReadiness,
): Promise<StrategiesSurfaceData> {
  const registry = await registryQuery().catch(() => null);
  const registryState = authorityState(registry);
  if (registryState !== "AVAILABLE" || !registry) {
    return {
      state: registryState,
      strategies: [],
      deploymentsState: registryState === "UNAVAILABLE" ? "UNAVAILABLE" : "UNKNOWN",
      asOf: registry?.asOf ?? null,
    };
  }

  const deployments = await deploymentsQuery().catch(() => null);
  const deploymentsState = authorityState(deployments);
  const deploymentRows = deploymentsState === "AVAILABLE" && deployments ? deployments.data : [];

  const items = await Promise.all(registry.data.map(async (entry) => {
    const readiness = await readinessQuery(entry.strategy_id).catch(() => null);
    return {
      entry,
      readiness,
      deployments: deploymentRows.filter((deployment) => deployment.strategyId === entry.strategy_id),
    };
  }));

  return {
    state: "AVAILABLE",
    strategies: items,
    deploymentsState,
    asOf: registry.asOf ?? null,
  };
}

const backendBlock = async <T,>(
  query: () => Promise<{ data: T; source: string; trust?: string; asOf: string }>,
  emptyValue: T,
): Promise<AuthorityBlock<T>> => {
  try {
    const result = await query();
    const state = authorityState(result);
    if (state !== "AVAILABLE") {
      return { state, data: emptyValue, asOf: result.asOf ?? null };
    }
    return { state: "AVAILABLE", data: result.data, asOf: result.asOf ?? null };
  } catch {
    return unavailable(emptyValue);
  }
};

export async function loadTestingSurface(
  backtestsQuery: typeof queryBacktestRuns = queryBacktestRuns,
  walkForwardQuery: typeof listWalkForwardJobs = listWalkForwardJobs,
  reportsQuery: typeof queryReports = queryReports,
): Promise<TestingSurfaceData> {
  const [backtests, walkForward, reports] = await Promise.all([
    backendBlock(() => backtestsQuery(), [] as AuthoritativeBacktestRun[]),
    backendBlock(() => walkForwardQuery(), [] as WalkForwardJob[]),
    backendBlock(() => reportsQuery(), [] as AuthoritativeReportItem[]),
  ]);
  return { backtests, walkForward, reports };
}

const runtimeBlock = async (
  mode: "PAPER" | "LIVE",
  query: typeof queryOrdersPortfolio,
): Promise<RuntimeSurfaceBlock> => {
  try {
    const snapshot = await query(false, mode);
    if (snapshot.availability !== "AVAILABLE") return { state: "UNAVAILABLE", snapshot: null };
    return { state: "AVAILABLE", snapshot };
  } catch {
    return { state: "UNAVAILABLE", snapshot: null };
  }
};

export async function loadTradingSurface(
  query: typeof queryOrdersPortfolio = queryOrdersPortfolio,
): Promise<TradingSurfaceData> {
  const [paper, live] = await Promise.all([
    runtimeBlock("PAPER", query),
    runtimeBlock("LIVE", query),
  ]);
  return { PAPER: paper, LIVE: live };
}

export async function loadAccountSurface(
  profileQuery: typeof queryCurrentUserProfile = queryCurrentUserProfile,
  connectionsQuery: typeof listUserConnections = listUserConnections,
): Promise<AccountSurfaceData> {
  const [profileResult, connectionsResult] = await Promise.all([
    profileQuery().catch(() => null),
    connectionsQuery().catch(() => null),
  ]);

  const profileState = authorityState(profileResult);
  const profile: AuthorityBlock<UserProfileData | null> = profileState === "AVAILABLE" && profileResult
    ? { state: "AVAILABLE", data: profileResult.data, asOf: profileResult.asOf ?? null }
    : { state: profileState, data: null, asOf: profileResult?.asOf ?? null };

  const connectionsState = authorityState(connectionsResult);
  const connections: AuthorityBlock<UserConnection[]> = connectionsState === "AVAILABLE" && connectionsResult
    ? { state: "AVAILABLE", data: connectionsResult.data, asOf: connectionsResult.asOf ?? null }
    : { state: connectionsState, data: [], asOf: connectionsResult?.asOf ?? null };

  return { profile, connections };
}
