import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Icon, type IconName } from "../shared/icons/V3Icons";
import { CommandPalette, GlobalRealTimeClock, type PaletteCmd } from "../shared/utilities/V3Chrome";
import {
  OwnerAccessRegistryScreen,
  OwnerBacktestsScreen,
  OwnerConnectionsScreen,
  OwnerIncidentsScreen,
  OwnerOverviewScreen,
  OwnerPaperScreen,
  OwnerPortfolioOrdersScreen,
  OwnerReportsAuditScreen,
  OwnerSecurityScreen,
  OwnerSettingsScreen,
  OwnerStrategiesScreen,
  OwnerSystemScreen,
} from "./authoritative/screens";
import { OwnerUsersInspectionScreen } from "./authoritative/UserInspection";
import { OwnerAIControlScreen } from "./authoritative/AIControlCenter";
import { ProductOperationsScreen } from "./authoritative/ProductOperationsScreen";
import "./owner-dashboard.css";

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

export const DESKTOP_OWNER_NAV_GROUPS: NavGroup[] = [
  {
    label: "CONTROL",
    items: [
      { id: "control", label: "Overview", icon: "home", badge: "Root", badgeTone: "warn" },
      { id: "users", label: "Users Oversight", icon: "users" },
      { id: "access-registry", label: "Access Registry", icon: "shield" },
      { id: "strategies", label: "Strategies Governance", icon: "code" },
      { id: "plugins", label: "Connections & Data", icon: "plug" },
    ],
  },
  {
    label: "OPERATIONS",
    items: [
      { id: "backtests", label: "Backtests Oversight", icon: "play" },
      { id: "paper", label: "Paper Sessions", icon: "layers" },
      { id: "portfolio-oversight", label: "Portfolio & Orders", icon: "chart" },
      { id: "reports", label: "Reports & Audit", icon: "file" },
      { id: "product-operations", label: "Product Operations", icon: "activity", badge: "Read only", badgeTone: "dim" },
    ],
  },
  {
    label: "AI",
    items: [
      { id: "ai-control", label: "AI Control Center", icon: "activity", badge: "Shadow", badgeTone: "dim" },
    ],
  },
  {
    label: "SYSTEM",
    items: [
      { id: "system", label: "System Health", icon: "activity" },
      { id: "security", label: "Security Authority", icon: "shield" },
      { id: "incidents", label: "Security Incidents", icon: "file" },
      { id: "settings", label: "Settings", icon: "shield" },
    ],
  },
];

export const MOBILE_OWNER_NAV: NavItem[] = [
  { id: "control", label: "Overview", icon: "home" },
  { id: "users", label: "Users", icon: "users" },
  { id: "strategies", label: "Strategies", icon: "code" },
  { id: "ai-control", label: "AI", icon: "activity" },
  { id: "more", label: "More", icon: "more" },
];

const ALL_SCREEN_IDS = DESKTOP_OWNER_NAV_GROUPS.flatMap((group) => group.items.map((item) => item.id));

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
  onExit,
}) => {
  const [mobile, setMobile] = useState<boolean>(() =>
    forceMode === "mobile" ? true : forceMode === "desktop" ? false : window.innerWidth < 900
  );
  const [screen, setScreen] = useState(() => {
    const hash = typeof window !== "undefined" ? window.location.hash.replace(/^#/, "") : "";
    return ALL_SCREEN_IDS.includes(hash) ? hash : "control";
  });
  const [moreOpen, setMoreOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    const onHash = () => {
      const hash = window.location.hash.replace(/^#/, "");
      if (ALL_SCREEN_IDS.includes(hash)) setScreen(hash);
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
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const go = useCallback((id: string) => {
    if (id === "more") { setMoreOpen((open) => !open); return; }
    if (!ALL_SCREEN_IDS.includes(id)) return;
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
    ...DESKTOP_OWNER_NAV_GROUPS.flatMap((group) => group.items).map((item) => ({
      id: `nav-${item.id}`,
      label: item.label,
      hint: "OWNER",
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

  const renderScreen = () => {
    switch (screen) {
      case "control": return <OwnerOverviewScreen go={go} />;
      case "users": return <OwnerUsersInspectionScreen />;
      case "access-registry": return <OwnerAccessRegistryScreen />;
      case "strategies": return <OwnerStrategiesScreen />;
      case "plugins": return <OwnerConnectionsScreen />;
      case "backtests": return <OwnerBacktestsScreen />;
      case "paper": return <OwnerPaperScreen />;
      case "portfolio-oversight": return <OwnerPortfolioOrdersScreen />;
      case "reports": return <OwnerReportsAuditScreen />;
      case "product-operations": return <ProductOperationsScreen />;
      case "ai-control": return <OwnerAIControlScreen />;
      case "system": return <OwnerSystemScreen />;
      case "security": return <OwnerSecurityScreen />;
      case "incidents": return <OwnerIncidentsScreen />;
      case "settings": return <OwnerSettingsScreen />;
      default: return <OwnerOverviewScreen go={go} />;
    }
  };

  const moreItems = DESKTOP_OWNER_NAV_GROUPS
    .flatMap((group) => group.items)
    .filter((item) => !MOBILE_OWNER_NAV.some((mobileItem) => mobileItem.id === item.id));

  return (
    <div className="v3-root" data-theme={theme}>
      <header className="v3-topbar">
        <div className="v3-brand" style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <img src="/algofortis_logo.png" alt="AlgoFortis" style={{ width: 20, height: 20, objectFit: "contain" }} />
          <div><b>ALGOFORTIS</b><span>OWNER CONTROL CENTER</span></div>
        </div>
        <span className="v3-lab-badge">OWNER AUTHORITY · LIVE DISARMED</span>
        <div className="v3-spacer" />
        <button className="v3-theme-btn" onClick={toggleTheme} aria-label={`Toggle theme (currently ${theme} mode)`}>
          <Icon name={theme === "dark" ? "sun" : "moon"} size={16} />
        </button>
        <button className="v3-search-btn" onClick={() => setPaletteOpen(true)} aria-label="Open command palette">
          <Icon name="search" size={14} /><span className="sb-label">Search</span><kbd>Ctrl K</kbd>
        </button>
        <GlobalRealTimeClock isMobile={mobile} />
        {onExit && <button className="v3-exit-btn" onClick={onExit}>Exit to Gate</button>}
      </header>

      {!mobile && (
        <nav className="v3-rail" aria-label="Owner navigation">
          {DESKTOP_OWNER_NAV_GROUPS.map((group) => <div key={group.label} className="v3-rail-group">
            <div className="v3-rail-label">{group.label}</div>
            {group.items.map((item) => {
              const active = screen === item.id;
              return <button key={item.id} className={`v3-rail-item ${active ? "active" : ""}`} onClick={() => go(item.id)} aria-current={active ? "page" : undefined}>
                <Icon name={item.icon} size={15} /><span className="v3-rail-item-text">{item.label}</span>
                {item.badge && <span className={`v3-rail-badge ${item.badgeTone || "ok"}`}>{item.badge}</span>}
              </button>;
            })}
          </div>)}
        </nav>
      )}

      <main className={`v3-shell ${mobile ? "mobile" : ""} ${["control", "portfolio-oversight", "ai-control", "users", "product-operations"].includes(screen) ? "wide" : ""}`}>
        <div className="v3-screen" key={screen}>{renderScreen()}</div>
      </main>

      {mobile && <nav className="v3-bottom-nav v3-dock" aria-label="Mobile owner navigation">
        {MOBILE_OWNER_NAV.map((item) => {
          const active = item.id === "more" ? moreOpen : screen === item.id;
          return <button key={item.id} className={`v3-bottom-nav-item v3-dock-item ${active ? "active" : ""}`} onClick={() => go(item.id)} aria-current={active ? "page" : undefined}>
            <Icon name={item.icon} size={18} /><span className="v3-rail-item-text">{item.label.toUpperCase()}</span>
          </button>;
        })}
      </nav>}

      {mobile && moreOpen && <div className="v3-drawer open" role="dialog" aria-label="More Owner screens">
        <div className="v3-drawer-head"><strong>Owner Controls</strong><button className="v3-btn ghost mini" onClick={() => setMoreOpen(false)}>Close</button></div>
        <div style={{ display: "grid", gap: 8, padding: 14 }}>
          {moreItems.map((item) => <button key={item.id} className="v3-btn ghost" onClick={() => go(item.id)}><Icon name={item.icon} size={15} /> {item.label}</button>)}
        </div>
      </div>}

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} commands={commands} />
    </div>
  );
};
