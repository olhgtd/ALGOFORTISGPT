import React, { useMemo, useState } from "react";
import type { UserScreenId } from "../navigation";
import type { UserShellStatus } from "../shellState";
import { NotificationCenter, type UserNotification } from "./NotificationCenter";
import { UserNavRail } from "./UserNavRail";
import { UserTopBar } from "./UserTopBar";

export interface UserDashboardShellProps {
  theme: "dark" | "light";
  toggleTheme: () => void;
  activeScreen: UserScreenId;
  onNavigate: (screen: UserScreenId) => void;
  onOpenPalette: () => void;
  status: UserShellStatus;
  notifications: readonly UserNotification[];
  onExit?: () => void;
  children: React.ReactNode;
}

const attrValue = (value: string) => value.toLowerCase().replaceAll("_", "-");

export const UserDashboardShell: React.FC<UserDashboardShellProps> = ({
  theme,
  toggleTheme,
  activeScreen,
  onNavigate,
  onOpenPalette,
  status,
  notifications,
  onExit,
  children,
}) => {
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const notificationCount = useMemo(
    () => status.criticalNotifications + status.actionRequiredNotifications + status.importantNotifications + status.infoNotifications,
    [status],
  );

  return (
    <div
      className="v3-root af-user-workspace"
      data-theme={theme}
      data-mode={status.mode.toLowerCase()}
      data-operational-state={attrValue(status.automationState)}
      data-manual-resume-required={status.manualResumeRequired ? "true" : "false"}
    >
      <UserTopBar
        theme={theme}
        toggleTheme={toggleTheme}
        status={status}
        notificationCount={notificationCount}
        onNotifications={() => setNotificationsOpen(true)}
        onOpenPalette={onOpenPalette}
        onAccount={() => onNavigate("account")}
        onExit={onExit}
      />

      <div className="af-mobile-safety-bar" data-testid="mobile-safety-bar" aria-label="Operational safety status">
        <span className={`af-mode-chip af-mode-${status.mode.toLowerCase()}`}>{status.modeLabel}</span>
        {status.liveStateLabel && <span className="af-live-lock">{status.liveStateLabel}</span>}
        <span className={`af-mobile-automation af-state-${attrValue(status.automationState)}`}>
          {status.automationState}
        </span>
        {status.manualResumeRequired && <span className="af-mobile-manual-resume">Manual resume required</span>}
      </div>

      <UserNavRail activeScreen={activeScreen} onNavigate={onNavigate} />
      <main className="af-user-main" id="v3-main-content">
        <div className="af-user-page" key={activeScreen}>{children}</div>
      </main>
      <NotificationCenter
        open={notificationsOpen}
        notifications={notifications}
        onClose={() => setNotificationsOpen(false)}
      />
    </div>
  );
};
