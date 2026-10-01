import React from "react";
import { Icon } from "../../shared/icons/V3Icons";
import { GlobalRealTimeClock } from "../../shared/utilities/V3Chrome";
import type { UserShellStatus } from "../shellState";

export interface UserTopBarProps {
  theme: "dark" | "light";
  toggleTheme: () => void;
  status: UserShellStatus;
  notificationCount: number;
  onNotifications: () => void;
  onOpenPalette: () => void;
  onAccount: () => void;
  onExit?: () => void;
}

export const UserTopBar: React.FC<UserTopBarProps> = ({
  theme,
  toggleTheme,
  status,
  notificationCount,
  onNotifications,
  onOpenPalette,
  onAccount,
  onExit,
}) => (
  <header className="af-user-topbar">
    <div className="af-user-brand" aria-label="AlgoFortis user workspace">
      <img src="/algofortis_logo.png" alt="" aria-hidden="true" />
      <div>
        <strong>AlgoFortis</strong>
        <span>DISCIPLINE DRIVES WEALTH</span>
      </div>
    </div>

    <div className="af-topbar-status" aria-label="Operational status">
      <span className={`af-mode-chip af-mode-${status.mode.toLowerCase()}`}>{status.modeLabel}</span>
      {status.liveStateLabel && <span className="af-live-lock">{status.liveStateLabel}</span>}
      <span className="af-status-chip"><b>Broker</b> {status.brokerState}</span>
      <span className="af-status-chip"><b>Engine</b> {status.engineState}</span>
      <span className={`af-status-chip af-data-${status.dataFreshness.toLowerCase()}`}><b>Data</b> {status.dataFreshness}</span>
    </div>

    <div className="af-topbar-actions">
      <button type="button" className="af-search-button" onClick={onOpenPalette} aria-label="Open command palette">
        <Icon name="search" size={15} /> <span>Search</span><kbd>Ctrl K</kbd>
      </button>
      <button
        type="button"
        className="af-icon-button af-bell-button"
        data-testid="notification-bell"
        onClick={onNotifications}
        aria-label={`Notifications${notificationCount ? `, ${notificationCount} unread` : ""}`}
      >
        <Icon name="alert" size={17} />
        {notificationCount > 0 && <span className="af-notification-count">{notificationCount}</span>}
      </button>
      <button type="button" className="af-icon-button" onClick={toggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
        <Icon name={theme === "dark" ? "sun" : "moon"} size={17} />
      </button>
      <GlobalRealTimeClock />
      <button
        type="button"
        className="af-profile-button"
        data-testid="account-entry"
        onClick={onAccount}
        aria-label="Open account"
        title="Account"
      >
        <span>AF</span>
      </button>
      {onExit && <button type="button" className="af-exit-button" onClick={onExit}>Exit</button>}
    </div>
  </header>
);
