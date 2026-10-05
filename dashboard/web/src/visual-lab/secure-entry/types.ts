/**
 * AlgoFortis Secure Entry & Access Gate Types
 * Governed by AlgoFortis DESIGN.md & Owner Invite-Only Specifications
 */

export type EntryFlow =
  | "ACCESS_GATE"
  | "RETURNING_USER"
  | "OWNER_SETUP"
  | "HELP_RECOVERY"
  | "LOCAL_OWNER_SETUP"
  | "LOCAL_LOGIN"
  | "LOCAL_RECOVERY";

export type AccessGateStep =
  | "ENTER_ACCESS_ID"
  | "ACCESS_DENIED"
  | "VERIFY_IDENTITY"
  | "CREATE_ACCOUNT"
  | "ACCOUNT_ACTIVATED";

export type VerificationState =
  | "ID_ENTRY"
  | "CHALLENGE_ACTIVE"
  | "VERIFYING_PASSKEY"
  | "VERIFICATION_SUCCESS"
  | "VERIFICATION_FAILED"
  | "UNAVAILABLE"
  | "WORKSPACE_TRANSITION";

export type ViewportMode = "DESKTOP" | "WEB_APP" | "MOBILE";

export interface SecureEntryState {
  flow: EntryFlow;
  gateStep: AccessGateStep;
  verificationState: VerificationState;
  viewportMode: ViewportMode;
  accessId: string;
  email: string;
  phone: string;
  password: string;
  confirmPassword: string;
  displayName: string;
  algofortisId: string;
  denialReason?: string;
  introPhase: number;
  isIntroComplete: boolean;
}

