import React, { useState, useEffect, useCallback, useRef } from "react";
import { LegacyEntryShell } from "./LegacyEntryShell";
import { LegacyUserFirstTimeCustomerFlow } from "./LegacyUserFirstTimeCustomerFlow";
import { LocalOwnerSetupCard } from "./LocalOwnerSetupCard";
import { LegacyUserLoginCard } from "./LegacyUserLoginCard";
import { LegacyLocalRecoveryCard } from "./LegacyLocalRecoveryCard";
import { api } from "../../api";
import type {
  EntryFlow,
  AccessGateStep,
  VerificationState,
  ViewportMode,
} from "./types";
import "./secure-entry.css";

interface LegacyUserSecureEntryAppProps {
  appTarget?: "owner" | "user";
  onEnterWorkspace?: (authenticatedSession?: boolean, workspace?: "user" | "owner") => void;
  onBackToWebsite?: () => void;
  onOpenDashboard?: () => void;
}

export const LegacyUserSecureEntryApp: React.FC<LegacyUserSecureEntryAppProps> = ({
  appTarget = "owner",
  onEnterWorkspace,
  onBackToWebsite,
  onOpenDashboard,
}) => {
  // Developer/prototype toolbar disabled in production
  const isDevMode = false;

  // Viewport and flow states
  const [viewportMode] = useState<ViewportMode>("DESKTOP");
  const [flow, setFlow] = useState<EntryFlow | "LOADING" | "UNAVAILABLE">("LOADING");
  const [gateStep, setGateStep] = useState<AccessGateStep>("ENTER_ACCESS_ID");
  const [verificationState, setVerificationState] = useState<VerificationState>("ID_ENTRY");

  useEffect(() => {
    let active = true;

    if (appTarget === "user") {
      void api.securityStatus()
        .then((status) => {
          if (!active) return;
          // NF-P2-09: backend securityStatus is the authority for the user path.
          // The client localStorage flag is a hint only — it alone must never
          // select LOCAL_LOGIN. Fail closed to backend truth.
          const isUserActivatedHint = (() => {
            try {
              return localStorage.getItem("algofortis_user_activated") === "true";
            } catch {
              return false;
            }
          })();
          const backendReady = status.owner_initialized === true;

          if (isUserActivatedHint && backendReady) {
            setFlow("LOCAL_LOGIN");
          } else {
            setFlow("ACCESS_GATE");
            setGateStep("ENTER_ACCESS_ID");
          }
        })
        .catch(() => {
          if (active) setFlow("UNAVAILABLE");
        });
      return () => { active = false; };
    }

    // Keep the original/manual Owner screens, but use the authoritative
    // singleton bootstrap decision so another PC never treats an empty local
    // database as permission to create OWNER-001 again. Owner login remains
    // reachable even when roaming/bootstrap authority is temporarily missing.
    void api.ownerBootstrapStatus()
      .then((bootstrap) => {
        if (!active) return;
        setFlow(
          bootstrap.owner_setup_allowed === true && bootstrap.recommended_flow === "LOCAL_OWNER_SETUP"
            ? "LOCAL_OWNER_SETUP"
            : "LOCAL_LOGIN"
        );
      })
      .catch(() => {
        if (active) setFlow("LOCAL_LOGIN");
      });

    return () => { active = false; };
  }, [appTarget]);

  // User input states
  const [accessId, setAccessId] = useState("");

  // 0.0s - 5.0s Intro Sequence Timing — defaults to settled for instant stability
  const [introElapsed, setIntroElapsed] = useState(5.0);
  const [introPhase, setIntroPhase] = useState(3);
  const [isIntroComplete, setIsIntroComplete] = useState(true);
  const introTimerRef = useRef<number | null>(null);
  const startTimeRef = useRef<number>(performance.now());

  const startIntroSequence = useCallback(() => {
    startTimeRef.current = performance.now();
    setIntroElapsed(0);
    setIntroPhase(0);
    setIsIntroComplete(false);

    if (introTimerRef.current) cancelAnimationFrame(introTimerRef.current);

    const tick = () => {
      const elapsed = (performance.now() - startTimeRef.current) / 1000;
      setIntroElapsed(elapsed);

      if (elapsed < 0.5) {
        setIntroPhase(0);
      } else if (elapsed < 1.5) {
        setIntroPhase(1);
      } else if (elapsed < 3.0) {
        setIntroPhase(2);
      } else {
        setIntroPhase(3);
      }

      if (elapsed >= 4.8) {
        setIsIntroComplete(true);
        setIntroElapsed(5.0);
      } else {
        introTimerRef.current = requestAnimationFrame(tick);
      }
    };

    introTimerRef.current = requestAnimationFrame(tick);
  }, []);

  const handleWorkspaceTransition = (authenticatedSession = true, workspace: "user" | "owner" = "user") => {
    setVerificationState("WORKSPACE_TRANSITION");
    if (onEnterWorkspace) {
      onEnterWorkspace(authenticatedSession, workspace);
    } else if (onOpenDashboard) {
      onOpenDashboard();
    }
  };

  const isCardVisible = introElapsed >= 1.5 || isIntroComplete;

  return (
    <LegacyEntryShell
      appTarget={appTarget}
      subhead="Invite-Only Access"
      verificationState={verificationState}
      introPhase={introPhase}
      introElapsed={introElapsed}
      isCardVisible={isCardVisible}
      viewportMode={viewportMode}
    >
      {(flow === "LOADING" || flow === "UNAVAILABLE") && (
        <div className="secure-access-card" id="security-status-card" role={flow === "UNAVAILABLE" ? "alert" : "status"}>
          <h2 className="card-title">{flow === "LOADING" ? "Checking security status..." : "Security status unavailable"}</h2>
          <p className="card-subtitle">
            {flow === "LOADING"
              ? "Waiting for AlgoFortis security authority."
              : "Unable to verify AlgoFortis security status. Reload to try again."}
          </p>
        </div>
      )}

      {flow === "LOCAL_OWNER_SETUP" && (
        <LocalOwnerSetupCard
          onSetupSuccess={() => handleWorkspaceTransition(true, "owner")}
          onSwitchToLogin={() => setFlow("LOCAL_LOGIN")}
        />
      )}

      {flow === "LOCAL_LOGIN" && (
        <LegacyUserLoginCard
          appTarget={appTarget}
          onLoginSuccess={() => handleWorkspaceTransition(true, appTarget === "owner" ? "owner" : "user")}
          onForgotPassword={appTarget === "owner" ? () => setFlow("LOCAL_RECOVERY") : undefined}
          onSwitchToAccessGate={appTarget === "user" ? () => {
            setFlow("ACCESS_GATE");
            setGateStep("ENTER_ACCESS_ID");
          } : undefined}
        />
      )}

      {flow === "LOCAL_RECOVERY" && (
        <LegacyLocalRecoveryCard
          onBackToLogin={() => setFlow("LOCAL_LOGIN")}
          onRecoverySuccess={() => setFlow("LOCAL_LOGIN")}
        />
      )}

      {flow === "ACCESS_GATE" && (
        <LegacyUserFirstTimeCustomerFlow
          accessId={accessId}
          onAccessIdChange={setAccessId}
          gateStep={gateStep}
          onGateStepChange={setGateStep}
          onSwitchToReturningUser={() => {
            setFlow("LOCAL_LOGIN");
          }}
          onCompleteActivation={(_token, role) => {
            handleWorkspaceTransition(true, role === "owner" ? "owner" : "user");
          }}
          isDevMode={isDevMode}
        />
      )}
    </LegacyEntryShell>
  );
};
