import React, { useCallback, useEffect, useState } from "react";
import { UserDashboardApp, type ThemeMode } from "../../user-dashboard/UserDashboardApp";
import { OwnerDashboardApp } from "../../owner-dashboard/OwnerDashboardApp";
import "../../shared/shared.css";
import "../../user-dashboard/user-dashboard.css";
import "../../owner-dashboard/owner-dashboard.css";

/* ════════════════════════════════════════════════════════════
   SentinelX Dashboard V3 — Master Workspace Dispatcher
   Strict User / Owner Workspace Separation
   ════════════════════════════════════════════════════════════ */

export type Workspace = "user" | "owner";
export type { ThemeMode };

export interface DashboardV3AppProps {
  initialWorkspace?: Workspace;
  initialTheme?: ThemeMode;
  forceMode?: "desktop" | "mobile";
  onExit?: () => void;
}

export const DashboardV3App: React.FC<DashboardV3AppProps> = ({
  initialWorkspace = "user",
  initialTheme = "dark",
  forceMode,
  onExit,
}) => {
  const [ws, setWs] = useState<Workspace>(() => {
    try {
      const p = new URLSearchParams(window.location.search);
      const q = p.get("workspace");
      if (q === "owner" || q === "user") return q;
    } catch {}
    return initialWorkspace;
  });

  const [theme, setTheme] = useState<ThemeMode>(() => {
    try {
      const stored = localStorage.getItem("sentinelx_theme");
      if (stored === "light" || stored === "dark") return stored;
    } catch {}
    return initialTheme;
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("sentinelx_theme", theme);
    } catch {}
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  }, []);

  const syncUrl = useCallback((nextWs: Workspace) => {
    const url = new URL(window.location.href);
    url.searchParams.set("surface", "dashboard-v3");
    url.searchParams.set("workspace", nextWs);
    url.searchParams.delete("preview");
    url.searchParams.delete("dev");
    window.history.replaceState({}, "", url.toString());
  }, []);

  const switchWs = useCallback((next: Workspace) => {
    setWs(next);
    syncUrl(next);
  }, [syncUrl]);

  useEffect(() => {
    const onPop = () => {
      const p = new URLSearchParams(window.location.search);
      const q = p.get("workspace");
      if (q === "owner" || q === "user") setWs(q);
    };
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  if (ws === "owner") {
    return (
      <OwnerDashboardApp
        theme={theme}
        toggleTheme={toggleTheme}
        forceMode={forceMode}
        onSwitchWorkspace={switchWs}
        onExit={onExit}
      />
    );
  }

  return (
    <UserDashboardApp
      theme={theme}
      toggleTheme={toggleTheme}
      forceMode={forceMode}
      onSwitchWorkspace={switchWs}
      onExit={onExit}
    />
  );
};
