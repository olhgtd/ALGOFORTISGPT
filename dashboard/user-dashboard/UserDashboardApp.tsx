import React, { useCallback, useEffect, useMemo, useState } from "react";
import { productRuntimeMode } from "../shared/services/runtimeConfig";
import { Icon, type IconName } from "../shared/icons/V3Icons";
import { CommandPalette, TruthChip, GlobalRealTimeClock, type PaletteCmd } from "../shared/utilities/V3Chrome";
import { UserHome } from "./screens/UserHome";
import { ConnectionsScreen } from "./screens/Connections";
import { AgentsScreen } from "./screens/Agents";
import {
  StrategiesScreen,
  TradingScreen,
  BacktestingScreen,
  PaperTradingScreen,
  PortfolioScreen,
  OrdersScreen,
  ReportsScreen,
  SecurityScreen,
  AccountScreen,
  HelpScreen,
  MoreSheet,
  MORE_USER_ITEMS,
} from "./screens/UserScreens";
import { type StrategyRow, type GlobalStrikePolicy, DEFAULT_GLOBAL_STRIKE_POLICY } from "../sampleData";
import "./user-dashboard.css";

/* ════════════════════════════════════════════════════════════
   AlgoFortis User Dashboard — Institutional Trading Terminal
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
  if (productRuntimeMode()) return false;
  try {
    return new URLSearchParams(window.location.search).get("dev") === "1";
  } catch {
    return false;
  }
};

export const DESKTOP_USER_NAV_GROUPS: NavGroup[] = [
  {
    label: "WORKSPACE",
    items: [
      { id: "home", label: "Overview", icon: "home" },
      { id: "strategies", label: "Strategies", icon: "code", badge: "3", badgeTone: "ok" },
      { id: "trading", label: "Strategy Execution", icon: "trade" },
      { id: "connections", label: "Connections", icon: "plug", badge: "3", badgeTone: "ok" },
    ],
  },
  {
    label: "VERIFICATION",
    items: [
      { id: "backtest", label: "Backtesting", icon: "play" },
      { id: "paper", label: "Paper Trading", icon: "layers", badge: "Live", badgeTone: "ok" },
    ],
  },
  {
    label: "OPERATIONS",
    items: [
      { id: "portfolio", label: "Portfolio", icon: "chart" },
      { id: "orders", label: "Orders", icon: "file" },
      { id: "reports", label: "Reports", icon: "file" },
    ],
  },
  {
    label: "SYSTEM",
    items: [
      { id: "security", label: "Security", icon: "shield" },
      { id: "account", label: "Account", icon: "users" },
      { id: "help", label: "Help & Docs", icon: "help" },
    ],
  },
];

export const MOBILE_USER_NAV: NavItem[] = [
  { id: "home", label: "Home", icon: "home" },
  { id: "strategies", label: "Strategies", icon: "code" },
  { id: "trading", label: "Trading", icon: "trade" },
  { id: "paper", label: "Paper", icon: "layers" },
  { id: "more", label: "More", icon: "more" },
];

export interface UserDashboardAppProps {
  theme: ThemeMode;
  toggleTheme: () => void;
  forceMode?: "desktop" | "mobile";
  onSwitchWorkspace?: (ws: "user" | "owner") => void;
  onExit?: () => void;
}

export const UserDashboardApp: React.FC<UserDashboardAppProps> = ({
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
      "home", "strategies", "trading", "connections", "backtest", "backtesting",
      "paper", "portfolio", "orders", "reports", "security", "account", "help",
      ...(isV2AgentsDevMode() ? ["agents"] : []),
    ];
    return valid.includes(hash) ? (hash === "backtesting" ? "backtest" : hash) : "home";
  });

  const [moreOpen, setMoreOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [strategyContext, setStrategyContext] = useState<StrategyRow | undefined>();

  const [strikePolicy, setStrikePolicy] = useState<GlobalStrikePolicy>(() => {
    try {
      const stored = localStorage.getItem("sentinelx_strike_policy_v1");
      if (stored) return JSON.parse(stored);
    } catch {}
    return DEFAULT_GLOBAL_STRIKE_POLICY;
  });

  useEffect(() => {
    try {
      localStorage.setItem("sentinelx_strike_policy_v1", JSON.stringify(strikePolicy));
    } catch {}
  }, [strikePolicy]);

  useEffect(() => {
    const onHash = () => {
      const h = window.location.hash.replace(/^#/, "");
      const valid = [
        "home", "strategies", "trading", "connections", "backtest", "backtesting",
        "paper", "portfolio", "orders", "reports", "security", "account", "help",
        ...(isV2AgentsDevMode() ? ["agents"] : []),
      ];
      if (valid.includes(h)) setScreen(h === "backtesting" ? "backtest" : h);
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
      url.searchParams.set("workspace", "user");
      url.searchParams.delete("dev");
      url.searchParams.delete("preview");
      window.history.replaceState({}, "", url.toString());
    }
  }, []);

  const goWithStrategy = useCallback((screenId: string, strat?: StrategyRow) => {
    if (strat) setStrategyContext(strat);
    go(screenId);
  }, [go]);

  const commands: PaletteCmd[] = useMemo(() => [
    ...DESKTOP_USER_NAV_GROUPS.flatMap((g) => g.items).map((n) => ({
      id: `nav-${n.id}`,
      label: n.label,
      hint: "USER",
      icon: n.icon,
      run: () => go(n.id),
    })),
    {
      id: "cmd-strike-atm",
      label: "Option Policy: ATM (0 strikes) · APPLIES TO ALL STRATEGIES",
      hint: "GLOBAL POLICY",
      icon: "layers",
      run: () => setStrikePolicy({ mode: "ATM", distance: 0 }),
    },
    {
      id: "cmd-strike-otm1",
      label: "Option Policy: OTM (1 strike) · APPLIES TO ALL STRATEGIES",
      hint: "GLOBAL POLICY",
      icon: "layers",
      run: () => setStrikePolicy({ mode: "OTM", distance: 1 }),
    },
    {
      id: "cmd-strike-otm2",
      label: "Option Policy: OTM (2 strikes) · APPLIES TO ALL STRATEGIES",
      hint: "GLOBAL POLICY",
      icon: "layers",
      run: () => setStrikePolicy({ mode: "OTM", distance: 2 }),
    },
    {
      id: "cmd-strike-itm1",
      label: "Option Policy: ITM (1 strike) · APPLIES TO ALL STRATEGIES",
      hint: "GLOBAL POLICY",
      icon: "layers",
      run: () => setStrikePolicy({ mode: "ITM", distance: 1 }),
    },
    {
      id: "cmd-toggle-theme",
      label: `Switch to ${theme === "dark" ? "Light" : "Dark"} Mode`,
      hint: "APPEARANCE",
      icon: theme === "dark" ? "sun" : "moon",
      run: toggleTheme,
    },
  ], [go, theme, toggleTheme]);

  const renderScreen = () => {
    if (productRuntimeMode() && ["strategies", "security"].includes(screen)) {
      return <div className="v3-screen-head" data-testid="product-surface-unavailable">
        <div>
          <h2 className="v3-screen-title">{screen === "strategies" ? "Strategies" : "Security & Passkeys"}</h2>
          <p className="v3-screen-sub">{screen === "strategies"
            ? "The strategy management view is unavailable in this local runtime."
            : "The device management view is unavailable. WebAuthn authentication remains mandatory."}</p>
        </div>
        <TruthChip kind="DISABLED" title="This view requires an authoritative product integration." />
      </div>;
    }
    switch (screen) {
      case "home": return <UserHome go={go} policy={strikePolicy} onChangePolicy={setStrikePolicy} />;
      case "strategies": return <StrategiesScreen onNavigate={goWithStrategy} policy={strikePolicy} onChangePolicy={setStrikePolicy} />;
      case "trading": return <TradingScreen initialStrategy={strategyContext} policy={strikePolicy} onChangePolicy={setStrikePolicy} />;
      case "connections": return <ConnectionsScreen />;
      case "backtest": return <BacktestingScreen initialStrategy={strategyContext} policy={strikePolicy} onChangePolicy={setStrikePolicy} />;
      case "paper": return <PaperTradingScreen initialStrategy={strategyContext} policy={strikePolicy} onChangePolicy={setStrikePolicy} />;
      case "portfolio": return <PortfolioScreen />;
      case "orders": return <OrdersScreen />;
      case "reports": return <ReportsScreen />;
      case "security": return <SecurityScreen />;
      case "account": return <AccountScreen />;
      case "help": return <HelpScreen />;
      case "agents":
        if (!isV2AgentsDevMode()) return <UserHome go={go} policy={strikePolicy} onChangePolicy={setStrikePolicy} />;
        return <AgentsScreen />;
      default: return <UserHome go={go} policy={strikePolicy} onChangePolicy={setStrikePolicy} />;
    }
  };

  return (
    <div className="v3-root" data-theme={theme}>
      <header className="v3-topbar">
        <div className="v3-brand" style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <img src="/algofortis_logo.png" alt="AlgoFortis" style={{ width: "20px", height: "20px", objectFit: "contain" }} />
          <div>
            <b>ALGOFORTIS</b>
            <span>USER WORKSPACE</span>
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
          {DESKTOP_USER_NAV_GROUPS.map((grp) => (
            <div key={grp.label} className="v3-rail-group">
              <div className="v3-rail-label">{grp.label}</div>
              {grp.items.map((it) => {
                const active = screen === it.id;
                return (
                  <button key={it.id} className={`v3-rail-item ${active ? "active" : ""}`} onClick={() => go(it.id)} aria-label={it.id === "trading" ? "Trading" : it.label}
                    aria-current={active ? "page" : undefined}
                    id={`nav-item-${it.id}`} data-nav-id={`v3-nav-${it.id}`}
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

      <main className={`v3-shell ${mobile ? "mobile" : ""} ${["home", "trading"].includes(screen) ? "wide" : ""}`} id="v3-main-content">
        <div className="v3-screen" key={screen}>
          {renderScreen()}
        </div>
      </main>

      {mobile && (
        <nav className="v3-bottom-nav v3-dock" aria-label="Mobile navigation" id="v3-mobile-bottom-nav">
          {MOBILE_USER_NAV.map((it) => {
            const active = screen === it.id;
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
          workspace="user"
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
