export type TradingMode = "BACKTEST" | "PAPER" | "LIVE";
export type AutomationState =
  | "RUNNING"
  | "PAUSED"
  | "STOPPED"
  | "HALT_ENTRIES"
  | "RECOVERY"
  | "READY_FOR_RESUME";
export type AuthorityState = "AVAILABLE" | "STALE" | "UNAVAILABLE" | "UNKNOWN";
export type BrokerState = "CONNECTED" | "DISCONNECTED" | "NEEDS_ATTENTION" | "UNAVAILABLE" | "UNKNOWN";

export interface UserShellStatusInput {
  mode: TradingMode;
  automationState: AutomationState;
  brokerState?: BrokerState;
  engineState?: AuthorityState;
  dataFreshness?: AuthorityState;
  notifications?: Partial<Record<"critical" | "actionRequired" | "important" | "info", number>>;
}

export interface UserShellStatus {
  mode: TradingMode;
  modeLabel: string;
  liveStateLabel: "READ_ONLY / DISARMED" | null;
  automationState: AutomationState;
  manualResumeRequired: boolean;
  brokerState: BrokerState;
  engineState: AuthorityState;
  dataFreshness: AuthorityState;
  criticalNotifications: number;
  actionRequiredNotifications: number;
  importantNotifications: number;
  infoNotifications: number;
}

const nonNegative = (value: number | undefined): number => Math.max(0, Math.trunc(value ?? 0));

export const deriveUserShellStatus = (input: UserShellStatusInput): UserShellStatus => ({
  mode: input.mode,
  modeLabel: input.mode === "BACKTEST" ? "Backtest" : input.mode === "PAPER" ? "Paper" : "Live",
  liveStateLabel: input.mode === "LIVE" ? "READ_ONLY / DISARMED" : null,
  automationState: input.automationState,
  manualResumeRequired: ["HALT_ENTRIES", "RECOVERY", "READY_FOR_RESUME"].includes(input.automationState),
  brokerState: input.brokerState ?? "UNKNOWN",
  engineState: input.engineState ?? "UNKNOWN",
  dataFreshness: input.dataFreshness ?? "UNKNOWN",
  criticalNotifications: nonNegative(input.notifications?.critical),
  actionRequiredNotifications: nonNegative(input.notifications?.actionRequired),
  importantNotifications: nonNegative(input.notifications?.important),
  infoNotifications: nonNegative(input.notifications?.info),
});
