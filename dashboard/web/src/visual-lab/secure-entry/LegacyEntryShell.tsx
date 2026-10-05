import React from "react";
import { LegacyAlgoFortisCore } from "./LegacyAlgoFortisCore";
import { GlobalRealTimeClock } from "../../../../shared/utilities/V3Chrome";
import type { VerificationState, ViewportMode } from "./types";
import "./secure-entry.css";

export interface LegacyEntryShellProps {
  appTarget?: "owner" | "user";
  subhead?: string;
  verificationState?: VerificationState;
  introPhase?: number;
  introElapsed?: number;
  isCardVisible?: boolean;
  viewportMode?: ViewportMode;
  children: React.ReactNode;
}

export const LegacyEntryShell: React.FC<LegacyEntryShellProps> = ({
  appTarget = "owner",
  subhead = "Invite-Only Access",
  verificationState = "ID_ENTRY",
  introPhase = 3,
  introElapsed = 5.0,
  isCardVisible = true,
  viewportMode = "DESKTOP",
  children,
}) => {
  const isMobile = viewportMode === "MOBILE";
  const coreSize = isMobile ? 200 : 280;

  return (
    <div className={`secure-entry-root ${introPhase >= 0 ? "intro-anim-fadein" : ""}`} id="secure-entry-root">
      {/* Top Real-Time Clock Bar */}
      <div className="access-gate-clock-bar">
        <GlobalRealTimeClock isMobile={isMobile} />
      </div>

      {/* Viewport Chassis */}
      <div className={`viewport-frame-wrapper mode-${viewportMode.toLowerCase().replace("_", "-")}`}>
        <div className="secure-stage" id="desktop-secure-stage">
          {/* Brand Header */}
          <div className={`secure-entry-brand-header intro-identity-reveal ${isCardVisible ? "revealed" : ""}`}>
            <div className="brand-wordmark-row">
              <h1 className="brand-title">ALGOFORTIS</h1>
            </div>
            <p className="brand-subhead">{subhead}</p>
          </div>

          {/* Animated Multi-Color Core (NO center logo, NO shield, exact original AlgoFortis visual) */}
          <div className="core-display-container">
            <LegacyAlgoFortisCore
              size={coreSize}
              verificationState={verificationState}
              introPhase={introPhase}
              introElapsed={introElapsed}
            />
          </div>

          {/* Child Auth Content */}
          <div className={`intro-identity-reveal ${isCardVisible ? "revealed" : ""}`} style={{ width: "100%" }}>
            {children}
          </div>
        </div>
      </div>
    </div>
  );
};
