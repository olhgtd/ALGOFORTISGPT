import React, { useState, useEffect, useCallback, useRef } from "react";
import { SentinelXCore } from "./SentinelXCore";
import { ReturningUserFlow } from "./ReturningUserFlow";
import { FirstTimeCustomerFlow } from "./FirstTimeCustomerFlow";
import { LocalOwnerSetupCard } from "./LocalOwnerSetupCard";
import { api } from "../../api";
import { HelpRecoveryFlow } from "./HelpRecoveryFlow";
import { GlobalRealTimeClock } from "../../../../shared/utilities/V3Chrome";
import type {
  EntryFlow,
  AccessGateStep,
  VerificationState,
  ViewportMode,
} from "./types";
import "./secure-entry.css";

interface SecureEntryAppProps {
  onEnterWorkspace?: (authenticatedSession?: boolean, workspace?: "user" | "owner") => void;
  onBackToWebsite?: () => void;
  onOpenDashboard?: () => void;
}

export const SecureEntryApp: React.FC<SecureEntryAppProps> = ({
  onEnterWorkspace,
  onBackToWebsite,
  onOpenDashboard,
}) => {
  // Query parameters cannot enable preview controls or choose the startup flow.
  const isDevMode = false;

  // One canonical gate serves Owner and User. The backend bootstrap authority
  // decides only whether one-time Owner setup is permitted; it never chooses a
  // caller-supplied role or grants dashboard access.
  const [viewportMode, setViewportMode] = useState<ViewportMode>("DESKTOP");
  const [flow, setFlow] = useState<EntryFlow | "LOADING" | "UNAVAILABLE">("LOADING");
  const [gateStep, setGateStep] = useState<AccessGateStep>("ENTER_ACCESS_ID");
  const [verificationState, setVerificationState] = useState<VerificationState>("ID_ENTRY");
  const [ownerSetupAllowed, setOwnerSetupAllowed] = useState(false);

  useEffect(() => {
    let active = true;
    void Promise.all([api.securityStatus(), api.ownerBootstrapStatus()])
      .then(([, bootstrap]) => {
        if (!active) return;
        setOwnerSetupAllowed(bootstrap.owner_setup_allowed === true);
        switch (bootstrap.recommended_flow) {
          case "LOCAL_LOGIN":
          case "RETURNING_USER":
            // Existing Owner and returning Users use the exact same canonical
            // password gate. Backend identity determines the workspace.
            setFlow("RETURNING_USER");
            return;
          case "LOCAL_OWNER_SETUP":
            setFlow(bootstrap.owner_setup_allowed ? "LOCAL_OWNER_SETUP" : "UNAVAILABLE");
            return;
          default:
            setFlow("UNAVAILABLE");
        }
      })
      .catch(() => {
        if (active) {
          setOwnerSetupAllowed(false);
          setFlow("UNAVAILABLE");
        }
      });
    return () => { active = false; };
  }, []);

  const [sentinelxId, setSentinelxId] = useState("");
  const [accessId, setAccessId] = useState("");

  // 0.0s - 5.0s Intro Sequence Timing — defaults to settled for instant stability.
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

      if (elapsed < 0.5) setIntroPhase(0);
      else if (elapsed < 1.5) setIntroPhase(1);
      else if (elapsed < 3.0) setIntroPhase(2);
      else setIntroPhase(3);

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
    if (onEnterWorkspace) onEnterWorkspace(authenticatedSession, workspace);
    else if (onOpenDashboard) onOpenDashboard();
  };

  const isMobile = viewportMode === "MOBILE";
  const coreSize = isMobile ? 200 : 280;
  const isCardVisible = introElapsed >= 1.5 || isIntroComplete;

  // This is intentionally unreachable from production navigation. It exists
  // only for the disabled developer preview controls and still obeys backend
  // ownerSetupAllowed authority.
  const requestOwnerSetup = () => {
    setFlow(ownerSetupAllowed ? "LOCAL_OWNER_SETUP" : "UNAVAILABLE");
  };

  return (
    <div className={`secure-entry-root ${introPhase >= 0 ? "intro-anim-fadein" : ""}`} id="secure-entry-root">
      {isDevMode && (
        <header className="secure-entry-prototype-bar" id="prototype-toolbar">
          <div className="prototype-bar-left">
            <span className="prototype-badge">PROTOTYPE</span>
            <span style={{ fontWeight: 600, color: "var(--sx-ink-primary)", fontSize: "11px" }}>AlgoFortis Access Gate</span>
            <span style={{ color: "var(--sx-ink-dim)" }}>|</span>
            <span style={{ color: "var(--sx-ink-muted)", fontSize: "11px" }}>
              {introElapsed < 4.8 ? `Intro: ${introElapsed.toFixed(1)}s / 5.0s` : "Interface Stable (5.0s)"}
            </span>
          </div>

          <div className="prototype-bar-controls">
            <div className="mode-pill-group">
              <button type="button" className={`mode-pill-btn ${viewportMode === "DESKTOP" ? "active" : ""}`} onClick={() => setViewportMode("DESKTOP")} id="mode-btn-desktop" title="Desktop Presentation">🖥 Desktop</button>
              <button type="button" className={`mode-pill-btn ${viewportMode === "WEB_APP" ? "active" : ""}`} onClick={() => setViewportMode("WEB_APP")} id="mode-btn-webapp" title="Web App Full Screen">🌐 Web App</button>
              <button type="button" className={`mode-pill-btn ${viewportMode === "MOBILE" ? "active" : ""}`} onClick={() => setViewportMode("MOBILE")} id="mode-btn-mobile" title="Mobile Responsive Simulation">📱 Mobile</button>
            </div>

            <div className="mode-pill-group">
              <button type="button" className={`mode-pill-btn ${flow === "ACCESS_GATE" ? "active" : ""}`} onClick={() => { setFlow("ACCESS_GATE"); setGateStep("ENTER_ACCESS_ID"); }} id="flow-btn-gate">Activate User</button>
              <button type="button" className={`mode-pill-btn ${flow === "RETURNING_USER" ? "active" : ""}`} onClick={() => { setFlow("RETURNING_USER"); setVerificationState("ID_ENTRY"); }} id="flow-btn-returning">Sign In</button>
              <button type="button" className={`mode-pill-btn ${flow === "LOCAL_OWNER_SETUP" ? "active" : ""}`} onClick={requestOwnerSetup} id="flow-btn-owner">Owner Setup</button>
            </div>

            <button type="button" className="replay-intro-btn" onClick={startIntroSequence} id="replay-intro-btn" title="Replay opening sequence"><span>↺</span> Replay</button>
            {onBackToWebsite && <button type="button" className="exit-prototype-btn" onClick={onBackToWebsite} id="nav-to-website-btn">Website</button>}
            {onOpenDashboard && <button type="button" className="exit-prototype-btn" onClick={onOpenDashboard} id="nav-to-dashboard-btn">Workstation</button>}
          </div>
        </header>
      )}

      <div className="access-gate-clock-bar"><GlobalRealTimeClock isMobile={isMobile} /></div>

      <div className={`viewport-frame-wrapper mode-${viewportMode.toLowerCase().replace("_", "-")}`}>
        <div className="secure-stage" id="desktop-secure-stage">
          <div className={`secure-entry-brand-header intro-identity-reveal ${isCardVisible ? "revealed" : ""}`}>
            <div className="brand-wordmark-row" style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "10px" }}>
              <img src="/algofortis_logo.png" alt="AlgoFortis Logo" style={{ width: "36px", height: "36px", objectFit: "contain" }} />
              <h1 className="brand-title" style={{ margin: 0, letterSpacing: "1px" }}><span style={{ color: "#f8fafc" }}>ALGO</span><span style={{ color: "#f59e0b" }}>FORTIS</span></h1>
            </div>
            <p className="brand-subhead" style={{ marginTop: "4px", color: "#94a3b8", fontSize: "12px", letterSpacing: "0.5px" }}>Trading Research &amp; Risk OS</p>
          </div>

          <div className="core-display-container">
            <SentinelXCore size={coreSize} verificationState={verificationState} introPhase={introPhase} introElapsed={introElapsed} />
          </div>

          <div className={`intro-identity-reveal ${isCardVisible ? "revealed" : ""}`} style={{ width: "100%" }}>
            {(flow === "LOADING" || flow === "UNAVAILABLE") && (
              <div className="secure-access-card" id="security-status-card" role={flow === "UNAVAILABLE" ? "alert" : "status"}>
                <h2 className="card-title">{flow === "LOADING" ? "Checking security status..." : "Account authority unavailable"}</h2>
                <p className="card-subtitle">{flow === "LOADING" ? "Waiting for AlgoFortis account and security authority." : "This installation cannot prove the account authority required for entry. Connect the central account authority or restore the existing identity; Owner Setup stays blocked."}</p>
              </div>
            )}

            {flow === "LOCAL_OWNER_SETUP" && ownerSetupAllowed && (
              <LocalOwnerSetupCard onSetupSuccess={() => handleWorkspaceTransition(true, "owner")} />
            )}

            {flow === "ACCESS_GATE" && (
              <FirstTimeCustomerFlow
                accessId={accessId}
                onAccessIdChange={setAccessId}
                gateStep={gateStep}
                onGateStepChange={setGateStep}
                onSwitchToReturningUser={() => { setFlow("RETURNING_USER"); setVerificationState("ID_ENTRY"); }}
                onSwitchToRecovery={() => setFlow("HELP_RECOVERY")}
                isDevMode={isDevMode}
              />
            )}

            {flow === "RETURNING_USER" && (
              <ReturningUserFlow
                sentinelxId={sentinelxId}
                onIdChange={setSentinelxId}
                verificationState={verificationState}
                onStartVerification={() => setVerificationState("CHALLENGE_ACTIVE")}
                onVerifySuccess={() => setVerificationState("VERIFICATION_SUCCESS")}
                onVerifyFailure={() => setVerificationState("VERIFICATION_FAILED")}
                onSwitchToAccessGate={() => { setFlow("ACCESS_GATE"); setGateStep("ENTER_ACCESS_ID"); }}
                onSwitchToOwnerSetup={requestOwnerSetup}
                onSwitchToRecovery={() => setFlow("HELP_RECOVERY")}
                onEnterWorkspace={(role) => handleWorkspaceTransition(true, role === "OWNER" ? "owner" : "user")}
                isMobileLayout={isMobile}
              />
            )}

            {flow === "HELP_RECOVERY" && (
              <HelpRecoveryFlow
                onBackToReturningUser={() => { setFlow("RETURNING_USER"); setVerificationState("ID_ENTRY"); }}
                onBackToAccessGate={() => { setFlow("ACCESS_GATE"); setGateStep("ENTER_ACCESS_ID"); }}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
