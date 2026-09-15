import React from "react";

/* SentinelX V3 icon set — 24px stroke grid, monochrome, no fills except dots. */

export type IconName =
  | "home" | "layers" | "trade" | "plug" | "more" | "users" | "puzzle"
  | "cpu" | "control" | "shield" | "chart" | "file" | "lock" | "help"
  | "search" | "close" | "chevron" | "plus" | "refresh" | "pause"
  | "play" | "back" | "alert" | "check" | "activity" | "key" | "clock"
  | "wallet" | "sun" | "moon" | "upload" | "code" | "terminal" | "copy";

const PATHS: Record<IconName, React.ReactNode> = {
  home: <path d="M4 11.5 12 4l8 7.5V20a1 1 0 0 1-1 1h-4.5v-6h-5v6H5a1 1 0 0 1-1-1z" />,
  layers: <><path d="M12 3 3 8l9 5 9-5-9-5z" /><path d="M3 12.5l9 5 9-5" /><path d="M3 17l9 5 9-5" opacity=".45" /></>,
  trade: <><path d="M4 17l5-5 4 3 7-8" /><path d="M15 7h5v5" /></>,
  plug: <><path d="M9 3v5M15 3v5" /><path d="M6 8h12v3a6 6 0 0 1-12 0V8z" /><path d="M12 17v4" /></>,
  more: <><circle cx="5" cy="12" r="1.6" fill="currentColor" stroke="none" /><circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" /><circle cx="19" cy="12" r="1.6" fill="currentColor" stroke="none" /></>,
  users: <><circle cx="9" cy="8.5" r="3.2" /><path d="M3.5 20c.6-3.4 2.9-5 5.5-5s4.9 1.6 5.5 5" /><path d="M15.5 5.6a3.2 3.2 0 0 1 0 5.8M17.5 15.4c1.6.8 2.7 2.3 3 4.6" opacity=".5" /></>,
  puzzle: <><rect x="4" y="4" width="7" height="7" rx="1.5" /><rect x="13" y="13" width="7" height="7" rx="1.5" /><path d="M13 7.5h3.5V11M7.5 13v3.5H11" opacity=".55" /></>,
  cpu: <><rect x="6" y="6" width="12" height="12" rx="2" /><rect x="10" y="10" width="4" height="4" /><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3" /></>,
  control: <><path d="M4 14a8 8 0 0 1 16 0" /><path d="M12 14l3.5-3.5" /><circle cx="12" cy="14" r="1.4" /></>,
  shield: <><path d="M12 3l7 2.5V11c0 4.6-3 7.8-7 9-4-1.2-7-4.4-7-9V5.5z" /><path d="M9.2 11.8l2 2 3.6-3.8" /></>,
  chart: <><path d="M4 4v16h16" /><path d="M8.5 16v-5M12.5 16V8M16.5 16v-8" /></>,
  file: <><path d="M7 3h7l4 4v14H7z" /><path d="M14 3v4h4" /></>,
  lock: <><rect x="6" y="11" width="12" height="9" rx="2" /><path d="M9 11V8a3 3 0 0 1 6 0v3" /></>,
  help: <><circle cx="12" cy="12" r="8.5" /><path d="M9.8 9.5A2.4 2.4 0 1 1 12 12.6v1.2" /><circle cx="12" cy="16.9" r=".9" fill="currentColor" stroke="none" /></>,
  search: <><circle cx="11" cy="11" r="6" /><path d="M15.5 15.5 20 20" /></>,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  chevron: <path d="M9 6l6 6-6 6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  refresh: <><path d="M20 12a8 8 0 1 1-2.34-5.66" /><path d="M20 4v4h-4" /></>,
  pause: <path d="M9 5v14M15 5v14" />,
  play: <path d="M8 5.5v13l10-6.5z" />,
  back: <path d="M15 6l-6 6 6 6" />,
  alert: <><path d="M12 4 2.8 19.5h18.4z" /><path d="M12 10v4.2" /><circle cx="12" cy="17" r=".9" fill="currentColor" stroke="none" /></>,
  check: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  activity: <path d="M3 12h4l2.5-6 5 12 2.5-6H21" />,
  key: <><circle cx="8" cy="14" r="4" /><path d="M11 11l8-8M16 6l2.5 2.5M13.5 8.5 16 11" /></>,
  clock: <><circle cx="12" cy="12" r="8.5" /><path d="M12 7v5l3.5 2" /></>,
  wallet: <><rect x="3.5" y="6.5" width="17" height="13" rx="2.5" /><path d="M3.5 10h17" /><circle cx="16.5" cy="15" r="1.2" fill="currentColor" stroke="none" /></>,
  sun: <><circle cx="12" cy="12" r="4.2" /><path d="M12 2v2.5M12 19.5v2.5M4.93 4.93l1.77 1.77M17.3 17.3l1.77 1.77M2 12h2.5M19.5 12h2.5M6.7 17.3l-1.77 1.77M19.07 4.93l-1.77 1.77" /></>,
  moon: <path d="M12 3a9 9 0 1 0 9 9c0-.46-.04-.92-.1-1.36a5.389 5.389 0 0 1-4.4 2.26 5.403 5.403 0 0 1-3.14-9.8c-.44-.06-.9-.1-1.36-.1z" />,
  upload: <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="17 8 12 3 7 8" /><line x1="12" y1="3" x2="12" y2="15" /></>,
  code: <><polyline points="16 18 22 12 16 6" /><polyline points="8 6 2 12 8 18" /></>,
  terminal: <><polyline points="4 17 10 11 4 5" /><line x1="12" y1="19" x2="20" y2="19" /></>,
  copy: <><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></>,
};

export const Icon: React.FC<{ name: IconName; size?: number; className?: string; style?: React.CSSProperties }> = ({ name, size = 18, className, style }) => (
  <svg
    className={className}
    style={style}
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    {PATHS[name]}
  </svg>
);

