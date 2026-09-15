import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Icon, type IconName } from "../shared/icons/V3Icons";
import { CommandPalette, GlobalRealTimeClock, type PaletteCmd } from "../shared/utilities/V3Chrome";
import { AdminHome } from "./screens/AdminHome";
import {
  AdminUsers,
  AdminStrategies,
  AdminPlugins,
  AdminBacktestPaper,
  AdminPortfolioOrders,
  AdminReportsAudit,
  AdminSecuritySystemSettingsScreen,
} from "./screens/AdminScreens";
import { AccessRegistryScreen } from "./screens/AccessRegistryScreen";
import { AgentsScreen } from "../user-dashboard/screens/Agents";
import { MoreSheet, MORE_OWNER_ITEMS } from "../user-dashboard/screens/UserScreens";
import "./owner-dashboard.css";

/* ════════════════════════════════════════════════════════════
   SentinelX Owner Dashboard — Control Center & Governance
   ════════════════════════════════════════════════════════════ */

export type ThemeMode = "dark" | "light";

export interface NavItem {
  id: string;
  label: string;
  icon: IconName;
  badge?: string;
  badgeTone?: "ok" | "warn" | "dim";
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const isV2AgentsDevMode = (): boolean => {
  try {
    return new URLSearchParams(window.location.search).get("dev") === "1";
  } catch {
    return false;
  }
};

export const DESKTOP_OWNER_NAV_GROUPS: NavGroup[] = [
  {
    label: "CONTROL",
    items: [
      { id: "control", label: "Overview", icon: "home", badge: "Root", badgeTone: "warn" },
      { id: "users", label: "Users Oversight", icon: "users" },
      { id: "access-registry", label: "Access Registry", icon: "shield", badge: "Live", badgeTone: "ok" },
      { id: "strategies", label: "Strategies Governance", icon: "code" },
      { id: "plugins", label: "Connections & Plugins", icon: "plug" },
    ],
  },
  {
    label: "OPERATIONS",
    items: [
      { id: "backtests", label: "Backtests Oversight", icon: "play" },
      { id: "paper", label: "Paper Sessions", icon: "layers" },
      { id: "portfolio-oversight", label: "Portfolio & Orders", icon: "chart" },
      { id: "reports", label: "Reports & Audits", icon: "file" },
    ],
  },
  {
    label: "SYSTEM",
    items: [
      { id: "system", label: "System Health", icon: "activity" },
      { id: "security", label: "Security Authority", icon: "shield" },
      { id: "audit", label: "Audit Ledger", icon: "file" },
      { id: "settings", label: "Settings", icon: "shield" },
    ],
  },
];

export const MOBILE_OWNER_NAV: NavItem[] = [
  { id: "control", label: "Overview", icon: "home" },
  { id: "users", label: "Users", icon: "users" },
  { id: "access-registry", label: "Access", icon: "shield" },
  { id: "strategies", label: "Strategies", icon: "code" },
  { id: "more", label: "More", icon: "more" },
];

export interface OwnerDashboardAppProps {
  theme: ThemeMode;
  toggleTheme: () => void;
  forceMode?: "desktop" | "mobile";
  onSwitchWorkspace?: (ws: "user" | "owner") => void;
  onExit?: () => void;
}

export const OwnerDashboardApp: React.FC<OwnerDashboardAppProps> = ({
  theme,
  toggleTheme,
  forceMode,
  onSwitchWorkspace,
  onExit,
}) => {
  const [mobile, setMobile] = useState<boolean>(() =>
    forceMode === "mobile" ? true : forceMode === "desktop" ? false : window.innerWidth < 900
  );

  const [screen, setScreen] = useState(() => {
    const hash = typeof window !== "undefined" ? window.location.hash.replace(/^#/, "") : "";
    const valid = [
      "control", "users", "access-registry", "strategies", "plugins",
      ...(isV2AgentsDevMode() ? ["agents"] : []),
      "backtests", "paper", "portfolio-oversight", "reports", "system",
      "security", "settings", "audit", "positions", "orders", "reports-audit",
    ];
    return valid.includes(hash) ? hash : "control";
  });

  const [moreOpen, setMoreOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    const onHash = () => {
      const h = window.location.hash.replace(/^#/, "");
      const valid = [
        "control", "users", "access-registry", "strategies", "plugins",
        ...(isV2AgentsDevMode() ? ["agents"] : []),
        "backtests", "paper", "portfolio-oversight", "reports", "system",
        "security", "settings", "audit", "positions", "orders", "reports-audit",
      ];
      if (valid.includes(h)) setScreen(h);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (forceMode) return;
    const onResize = () => setMobile(window.innerWidth < 900);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [forceMode]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((p) => !p);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const go = useCallback((id: string) => {
    if (id === "more") { setMoreOpen((m) => !m); return; }
    setScreen(id);
    setMoreOpen(false);
    if (typeof window !== "undefined") {
      window.location.hash = `#${id}`;
      const url = new URL(window.location.href);
      url.searchParams.set("surface", "dashboard-v3");
      url.searchParams.set("workspace", "owner");
      url.searchParams.delete("dev");
      url.searchParams.delete("preview");
      window.history.replaceState({}, "", url.toString());
    }
  }, []);

  const commands: PaletteCmd[] = useMemo(() => [
    ...DESKTOP_OWNER_NAV_GROUPS.flatMap((g) => g.items).map((n) => ({
      id: `nav-${n.id}`,
      label: n.label,
      hint: "OWNER",
      icon: n.icon,
      run: () => go(n.id),
    })),
    {
      id: "cmd-toggle-theme",
      label: `Switch to ${theme === "dark" ? "Light" : "Dark"} Mode`,
      hint: "APPEARANCE",
      icon: theme === "dark" ? "sun" : "moon",
      run: toggleTheme,
    },
  ], [go, theme, toggleTheme]);

  const renderScreen = () => {
    switch (screen) {
      case "control": return <AdminHome go={go} />;
      case "users": return <AdminUsers />;
      case "access-registry": return <AccessRegistryScreen />;
      case "strategies": return <AdminStrategies />;
      case "plugins": return <AdminPlugins />;
      case "agents":
        if (!isV2AgentsDevMode()) return <AdminHome go={go} />;
        return <AgentsScreen ownerView />;
      case "backtests": return <AdminBacktestPaper initialTab="backtest" go={go} />;
      case "paper": return <AdminBacktestPaper initialTab="paper" go={go} />;
      case "portfolio-oversight": return <AdminPortfolioOrders initialTab="portfolio" go={go} />;
      case "portfolio": return <AdminPortfolioOrders initialTab="portfolio" go={go} />;
      case "positions": return <AdminPortfolioOrders initialTab="positions" go={go} />;
      case "orders": return <AdminPortfolioOrders initialTab="orders" go={go} />;
      case "reports": return <AdminReportsAudit initialTab="reports" go={go} />;
      case "audit": return <AdminReportsAudit initialTab="audit" go={go} />;
      case "reports-audit": return <AdminReportsAudit initialTab="reports" go={go} />;
      case "system": return <AdminSecuritySystemSettingsScreen initialTab="system" go={go} />;
      case "security": return <AdminSecuritySystemSettingsScreen initialTab="security" go={go} />;
      case "settings": return <AdminSecuritySystemSettingsScreen initialTab="settings" go={go} />;
      default: return <AdminHome go={go} />;
    }
  };

  return (
    <div className="v3-root" data-theme={theme}>
      <header className="v3-topbar">
        <div className="v3-brand" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <img src="/algofortis_logo.png" alt="AlgoFortis" style={{ width: "20px", height: "20px", objectFit: "contain" }} />
          <div>
            <b>ALGOFORTIS</b>
            <span>OWNER CONTROL CENTER</span>
          </div>
        </div>
        <span className="v3-lab-badge">AUTHORITATIVE RUNTIME · RELEASE CANDIDATE</span>
        <div className="v3-spacer" />

        <button
          className="v3-theme-btn"
          onClick={toggleTheme}
          aria-label={`Toggle theme (currently ${theme} mode)`}
          title={`Switch to ${theme === "dark" ? "Light" : "Dark"} mode`}
          id="v3-theme-toggle-btn"
        >
          <Icon name={theme === "dark" ? "sun" : "moon"} size={16} />
        </button>

        <button className="v3-search-btn" onClick={() => setPaletteOpen(true)} aria-label="Open command palette">
          <Icon name="search" size={14} />
          <span className="sb-label">Search</span>
          <kbd>Ctrl K</kbd>
        </button>

        <GlobalRealTimeClock isMobile={mobile} />

        {onExit && <button className="v3-exit-btn" onClick={onExit} id="exit-to-access-gate-btn">Exit to Gate</button>}
      </header>

      {!mobile && (
        <nav className="v3-rail" aria-label="Primary navigation" id="v3-desktop-nav-rail">
          {DESKTOP_OWNER_NAV_GROUPS.map((grp) => (
            <div key={grp.label} className="v3-rail-group">
              <div className="v3-rail-label">{grp.label}</div>
              {grp.items.map((it) => {
                const active =
                  screen === it.id ||
                  (it.id === "portfolio-oversight" && ["portfolio", "positions", "orders"].includes(screen)) ||
                  (it.id === "reports" && screen === "reports-audit");
                return (
                  <button
                    key={it.id}
                    className={`v3-rail-item ${active ? "active" : ""}`}
                    onClick={() => go(it.id)}
                    aria-current={active ? "page" : undefined}
                    id={`v3-nav-${it.id}`}
                  >
                    <Icon name={it.icon} size={15} />
                    <span className="v3-rail-item-text">{it.label}</span>
                    {it.badge && (
                      <span className={`v3-rail-badge ${it.badgeTone || "ok"}`}>
                        {it.badge}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>
      )}

      <main className={`v3-shell ${mobile ? "mobile" : ""} ${["control", "portfolio-oversight", "portfolio", "positions", "orders"].includes(screen) ? "wide" : ""}`} id="v3-main-content">
        <div className="v3-screen" key={screen}>
          {renderScreen()}
        </div>
      </main>

      {mobile && (
        <nav className="v3-bottom-nav v3-dock" aria-label="Mobile navigation" id="v3-mobile-bottom-nav">
          {MOBILE_OWNER_NAV.map((it) => {
            const active =
              it.id === "control"
                ? ["control", "overview", "home"].includes(screen)
                : it.id === "more"
                ? moreOpen
                : screen === it.id ||
                  (it.id === "portfolio-oversight" && ["portfolio", "positions", "orders"].includes(screen)) ||
                  (it.id === "reports" && screen === "reports-audit");
            return (
              <button
                key={it.id}
                className={`v3-bottom-nav-item v3-dock-item ${active ? "active" : ""}`}
                onClick={() => go(it.id)}
                aria-current={active ? "page" : undefined}
                id={`v3-mobile-nav-${it.id}`}
              >
                <Icon name={it.icon} size={18} />
                <span className="v3-rail-item-text">{it.label.toUpperCase()}</span>
              </button>
            );
          })}
        </nav>
      )}

      {mobile && moreOpen && (
        <MoreSheet
          workspace="owner"
          currentScreen={screen}
          onOpen={(id) => go(id)}
          onClose={() => setMoreOpen(false)}
        />
      )}

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        commands={commands}
      />
    </div>
  );
};
