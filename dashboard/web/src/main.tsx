/**
 * SentinelX Enterprise Control Center & Web Platform – Root Application
 *
 * Single Canonical Entry Point:
 * - Public Website: SentinelXWebsite (landing page, docs, features)
 * - Secure Entry Gate: SecureEntryApp (FIDO2/WebAuthn hardware auth, new user setup, recovery)
 * - Dashboard V3: DashboardV3App (canonical trading workstation for User & Owner workspaces)
 *
 * Strict Architecture Invariants:
 * - Fail-closed security: UNKNOWN ≠ HEALTHY, STALE ≠ LIVE, MISSING ≠ VALID
 * - Zero legacy dashboard code, zero duplicate shells
 */

import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { SentinelXWebsite } from "./website/SentinelXWebsite";
import { SecureEntryApp } from "./visual-lab/secure-entry/SecureEntryApp";
import { RuntimeAvailability } from "./RuntimeAvailability";
import { DashboardV3App, type Workspace } from "./DashboardV3App";
import { api, clearSessionToken, type AuthoritativeUserResponse } from "./api";

type SurfaceId = "website" | "secure-entry" | "dashboard-v3";

type AuthoritativeSession = AuthoritativeUserResponse;

function desktopAppWorkspace(): Workspace | null {
  if (typeof window === "undefined") return null;
  const app = new URLSearchParams(window.location.search).get("app");
  return app === "owner" || app === "user" ? app : null;
}

const DASHBOARD_HASHES = new Set([
  "home", "strategies", "trading", "connections", "backtest", "backtesting",
  "paper", "portfolio", "orders", "reports", "security", "account", "help",
  "control", "users", "access-registry", "plugins", "backtests",
  "portfolio-oversight", "system", "audit", "settings", "agents"
]);

function AuthorizedDashboard({
  requestedWorkspace,
  lockedWorkspace,
  authorizationEpoch,
  onDenied,
  onExit,
}: {
  requestedWorkspace: Workspace;
  lockedWorkspace?: Workspace;
  authorizationEpoch: number;
  onDenied: () => void;
  onExit: () => void;
}) {
  const [session, setSession] = useState<AuthoritativeSession | null>(null);
  const [resolved, setResolved] = useState(false);

  useEffect(() => {
    let active = true;
    setResolved(false);
    setSession(null);
    void api.currentUser()
      .then((identity) => {
        if (active) setSession(identity);
      })
      .catch(() => {
        if (active) setSession(null);
      })
      .finally(() => {
        if (active) setResolved(true);
      });
    return () => {
      active = false;
    };
  }, [authorizationEpoch]);

  const isAccountActive = session?.account_status
    ? session.account_status === "ACTIVE"
    : session?.lifecycle === "ACTIVE";

  const isLifecycleActive = session?.lifecycle === "ACTIVE";

  const authorized = Boolean(
    session &&
    isAccountActive &&
    isLifecycleActive &&
    (
      session.workspace_eligibility
        ? Boolean(session.workspace_eligibility[requestedWorkspace])
        : (
            requestedWorkspace === "user"
              ? (session.service_status ? session.service_status === "ACTIVE" : true)
              : (session.role === "OWNER")
          )
    )
  );

  useEffect(() => {
    if (resolved && !authorized) onDenied();
  }, [authorized, onDenied, resolved]);

  if (!resolved || !authorized) return null;
  return <DashboardV3App initialWorkspace={requestedWorkspace} lockedWorkspace={lockedWorkspace} onExit={onExit} />;
}

export function App() {
  const lockedWorkspace = desktopAppWorkspace();
  const [authorizationEpoch, setAuthorizationEpoch] = useState(0);
  const [surface, setSurface] = useState<SurfaceId>(() => {
    if (typeof window !== "undefined") {
      const s = new URLSearchParams(window.location.search).get("surface");
      if (s === "website" || window.location.hash === "#website") {
        return "website";
      }
      if (s === "secure-entry" || window.location.hash === "#secure-entry") {
        return "secure-entry";
      }
      if (s === "dashboard-v3") {
        return "dashboard-v3";
      }
      const ws = new URLSearchParams(window.location.search).get("workspace");
      if (ws === "owner" || ws === "user") {
        return "dashboard-v3";
      }
      const rawHash = window.location.hash.replace(/^#/, "");
      if (DASHBOARD_HASHES.has(rawHash)) {
        return "dashboard-v3";
      }
    }
    return "secure-entry";
  });

  const [activeWorkspace, setActiveWorkspace] = useState<Workspace>(() => {
    if (lockedWorkspace) return lockedWorkspace;
    if (typeof window !== "undefined") {
      const ws = new URLSearchParams(window.location.search).get("workspace");
      if (ws === "owner" || ws === "user") return ws;
    }
    return "user";
  });

  const switchToWebsite = () => {
    clearSessionToken();
    setSurface("website");
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("surface", "website");
      url.searchParams.delete("preview");
      url.searchParams.delete("workspace");
      if (url.hash === "#secure-entry" || url.hash === "#app") url.hash = "";
      window.history.pushState({}, "", url.toString());
    }
  };

  const switchToSecureEntry = () => {
    clearSessionToken();
    setSurface("secure-entry");
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("surface", "secure-entry");
      url.searchParams.delete("preview");
      url.searchParams.delete("workspace");
      if (url.hash === "#website" || url.hash === "#app") url.hash = "";
      window.history.pushState({}, "", url.toString());
    }
  };

  const handleExit = () => {
    void api.revokeSession().catch(() => {});
    switchToSecureEntry();
  };

  const switchToDashboardV3 = (workspace: Workspace = "user") => {
    const target = lockedWorkspace ?? workspace;
    setActiveWorkspace(target);
    setSurface("dashboard-v3");
    setAuthorizationEpoch((value) => value + 1);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("surface", "dashboard-v3");
      url.searchParams.set("workspace", target);
      url.searchParams.delete("preview");
      if (url.hash === "#secure-entry" || url.hash === "#website" || url.hash === "#app") url.hash = "";
      window.history.pushState({}, "", url.toString());
    }
  };

  // Keep state in sync with popstate & hashchange
  useEffect(() => {
    const handleNavigation = () => {
      const s = new URLSearchParams(window.location.search).get("surface");
      const ws = new URLSearchParams(window.location.search).get("workspace");
      const rawHash = window.location.hash.replace(/^#/, "");

      if (lockedWorkspace) {
        setActiveWorkspace(lockedWorkspace);
      } else if (ws === "owner" || ws === "user") {
        setActiveWorkspace(ws);
      }

      if (s === "website" || window.location.hash === "#website") {
        setSurface("website");
      } else if (s === "secure-entry" || window.location.hash === "#secure-entry") {
        setSurface("secure-entry");
      } else if (s === "dashboard-v3" || ws === "owner" || ws === "user" || DASHBOARD_HASHES.has(rawHash)) {
        setSurface("dashboard-v3");
      } else {
        setSurface("secure-entry");
      }
    };

    window.addEventListener("popstate", handleNavigation);
    window.addEventListener("hashchange", handleNavigation);
    return () => {
      window.removeEventListener("popstate", handleNavigation);
      window.removeEventListener("hashchange", handleNavigation);
    };
  }, [lockedWorkspace]);

  if (surface === "website") {
    return <SentinelXWebsite onLaunchApp={switchToSecureEntry} />;
  }

  if (surface === "secure-entry") {
    return (
      <SecureEntryApp
        appRole={lockedWorkspace ?? undefined}
        onEnterWorkspace={(_authenticatedSession = true, workspace = "user") => {
          switchToDashboardV3(workspace);
        }}
        onBackToWebsite={switchToWebsite}
        onOpenDashboard={() => switchToDashboardV3(lockedWorkspace ?? "user")}
      />
    );
  }

  return (
    <AuthorizedDashboard
      requestedWorkspace={lockedWorkspace ?? activeWorkspace}
      lockedWorkspace={lockedWorkspace ?? undefined}
      authorizationEpoch={authorizationEpoch}
      onDenied={switchToSecureEntry}
      onExit={handleExit}
    />
  );
}

createRoot(document.getElementById("root")!).render(<RuntimeAvailability><App /></RuntimeAvailability>);
