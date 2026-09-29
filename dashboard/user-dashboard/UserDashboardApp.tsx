import React, { useCallback, useEffect, useMemo, useState } from "react";
import { CommandPalette, type PaletteCmd } from "../shared/utilities/V3Chrome";
import { UserHome } from "./screens/UserHome";
import { UserMarkets } from "./markets/UserMarkets";
import { UserStrategies } from "./screens/UserStrategies";
import { UserTesting } from "./screens/UserTesting";
import { UserTrades } from "./screens/UserTrades";
import { UserPortfolio } from "./screens/UserPortfolio";
import { UserAccount } from "./screens/UserAccount";
import { UserDashboardShell } from "./components/UserDashboardShell";
import { USER_NAV_ITEMS, isUserScreenId, type UserScreenId } from "./navigation";
import { deriveUserShellStatus, type UserShellStatus } from "./shellState";
import { loadHomeCommandCenterModel } from "./home/homeData";
import "./user-dashboard.css";
import "./user-dashboard-finish.css";
import "./user-pages.css";

export type ThemeMode = "dark" | "light";

export interface UserDashboardAppProps {
  theme: ThemeMode;
  toggleTheme: () => void;
  forceMode?: "desktop" | "mobile";
  onSwitchWorkspace?: (ws: "user" | "owner") => void;
  onExit?: () => void;
}

const LEGACY_ROUTE_MAP: Record<string, UserScreenId> = {
  trading: "trades",
  orders: "trades",
  paper: "trades",
  backtest: "testing",
  backtesting: "testing",
  connections: "account",
  reports: "account",
  security: "account",
  help: "account",
  agents: "home",
};

const locationScreen = (): UserScreenId => {
  if (typeof window === "undefined") return "home";
  const raw = window.location.hash.replace(/^#/, "");
  if (isUserScreenId(raw)) return raw;
  return LEGACY_ROUTE_MAP[raw] ?? "home";
};

const initialShellStatus = (): UserShellStatus => deriveUserShellStatus({
  mode: "UNKNOWN",
  automationState: "UNKNOWN",
  brokerState: "UNKNOWN",
  engineState: "UNKNOWN",
  dataFreshness: "UNKNOWN",
  notifications: {},
});

export const UserDashboardApp: React.FC<UserDashboardAppProps> = ({
  theme,
  toggleTheme,
  onExit,
}) => {
  const [screen, setScreen] = useState<UserScreenId>(locationScreen);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [shellStatus, setShellStatus] = useState<UserShellStatus>(initialShellStatus);

  useEffect(() => {
    const onHash = () => setScreen(locationScreen());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // Home already loads the authoritative command-center model and reports its
  // shell status. Direct routes must do the same instead of remaining at the
  // bootstrap UNKNOWN state for the entire session.
  useEffect(() => {
    if (screen === "home") return;
    let active = true;

    void loadHomeCommandCenterModel()
      .then((model) => {
        if (active) setShellStatus(model.shell);
      })
      .catch(() => {
        if (active) setShellStatus(initialShellStatus());
      });

    return () => {
      active = false;
    };
  }, [screen]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const go = useCallback((next: string) => {
    const resolved = isUserScreenId(next) ? next : LEGACY_ROUTE_MAP[next] ?? "home";
    setScreen(resolved);
    setPaletteOpen(false);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("surface", "dashboard-v3");
      url.searchParams.set("workspace", "user");
      url.searchParams.delete("dev");
      url.searchParams.delete("preview");
      url.hash = resolved;
      window.history.replaceState({}, "", url.toString());
    }
  }, []);

  const commands: PaletteCmd[] = useMemo(() => [
    ...USER_NAV_ITEMS.map((item) => ({
      id: `nav-${item.id}`,
      label: item.label,
      hint: "USER",
      icon: item.icon,
      run: () => go(item.id),
    })),
    {
      id: "cmd-toggle-theme",
      label: `Switch to ${theme === "dark" ? "Light" : "Dark"} Mode`,
      hint: "APPEARANCE",
      icon: theme === "dark" ? "sun" : "moon",
      run: toggleTheme,
    },
  ], [go, theme, toggleTheme]);

  const content = (() => {
    switch (screen) {
      case "home": return <UserHome go={go} onShellStatus={setShellStatus} />;
      case "markets": return <UserMarkets theme={theme} />;
      case "strategies": return <UserStrategies />;
      case "testing": return <UserTesting />;
      case "trades": return <UserTrades />;
      case "portfolio": return <UserPortfolio />;
      case "account": return <UserAccount />;
    }
  })();

  return (
    <>
      <UserDashboardShell
        theme={theme}
        toggleTheme={toggleTheme}
        activeScreen={screen}
        onNavigate={go}
        onOpenPalette={() => setPaletteOpen(true)}
        status={shellStatus}
        notifications={[]}
        onExit={onExit}
      >
        {content}
      </UserDashboardShell>
      <CommandPalette open={paletteOpen} commands={commands} onClose={() => setPaletteOpen(false)} />
    </>
  );
};
