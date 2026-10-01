import type { IconName } from "../shared/icons/V3Icons";

export type UserScreenId =
  | "home"
  | "markets"
  | "strategies"
  | "testing"
  | "trades"
  | "portfolio"
  | "account";

export interface UserNavItem {
  id: UserScreenId;
  label: string;
  icon: IconName;
}

export const USER_NAV_ITEMS: readonly UserNavItem[] = [
  { id: "home", label: "Home", icon: "home" },
  { id: "markets", label: "Markets", icon: "chart" },
  { id: "strategies", label: "Strategies", icon: "code" },
  { id: "testing", label: "Testing & Validation", icon: "play" },
  { id: "trades", label: "Trades", icon: "trade" },
  { id: "portfolio", label: "Portfolio", icon: "wallet" },
  { id: "account", label: "Account", icon: "users" },
] as const;

export const USER_SCREEN_IDS = new Set<UserScreenId>(USER_NAV_ITEMS.map((item) => item.id));

export const isUserScreenId = (value: string): value is UserScreenId =>
  USER_SCREEN_IDS.has(value as UserScreenId);
