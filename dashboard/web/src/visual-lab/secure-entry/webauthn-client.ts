/**
 * AlgoFortis Real WebAuthn / FIDO2 Client Helper
 * Interacts with authoritative FastAPI endpoints:
 * - /api/v1/auth/webauthn/authentication/options
 * - /api/v1/auth/webauthn/authentication/complete
 */

import { api, setSessionToken } from "../../api";

export function base64Url(bytes: ArrayBuffer | null): string | null {
  if (!bytes) return null;
  const value = new Uint8Array(bytes);
  let binary = "";
  value.forEach((byte) => (binary += String.fromCharCode(byte)));
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

export function toArrayBuffer(value: string): ArrayBuffer {
  const padded = value.replaceAll("-", "+").replaceAll("_", "/") + "=".repeat((4 - (value.length % 4)) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0)).buffer;
}

export interface WebAuthnAuthResult {
  access_token: string;
  expires_at_utc: string;
  credential_id?: string;
  role: "OWNER" | "USER";
  subject: string;
  sx_id: string;
}

export async function executeRealWebAuthnAuthentication(identifier?: string): Promise<WebAuthnAuthResult> {
  if (typeof window === "undefined" || !window.PublicKeyCredential) {
    throw new Error("This browser does not support WebAuthn / FIDO2.");
  }

  // 1. Fetch public challenge options from authoritative backend
  const issued = await api.webauthnAuthenticationOptions(identifier);
  const options = issued.publicKey;
  options.challenge = toArrayBuffer(options.challenge as unknown as string);
  options.allowCredentials = options.allowCredentials?.map((credential) => ({
    ...credential,
    id: toArrayBuffer(credential.id as unknown as string),
  }));

  // 2. Invoke browser navigator.credentials.get
  const assertion = (await navigator.credentials.get({ publicKey: options })) as PublicKeyCredential | null;
  if (!assertion) {
    throw new Error("WebAuthn authentication was cancelled.");
  }

  const response = assertion.response as AuthenticatorAssertionResponse;

  // 3. Complete authentication ceremony with backend to obtain session token
  const completed = await api.webauthnAuthenticationComplete(issued.challenge_id, {
    id: assertion.id,
    rawId: base64Url(assertion.rawId),
    type: assertion.type,
    response: {
      authenticatorData: base64Url(response.authenticatorData),
      clientDataJSON: base64Url(response.clientDataJSON),
      signature: base64Url(response.signature),
      userHandle: base64Url(response.userHandle),
    },
  });

  // 4. Store authoritative session token in API client
  setSessionToken(completed.access_token);
  return completed;
}

export interface WebAuthnBootstrapResult {
  credential_id: string;
  registered: boolean;
  security_setup: string;
}

export async function executeRealWebAuthnBootstrapRegistration(
  bootstrapToken: string,
  label: string = "Owner Hardware Key"
): Promise<WebAuthnBootstrapResult> {
  const cleanToken = (bootstrapToken || "").trim();
  if (!cleanToken) {
    throw new Error("One-time bootstrap authorization token is required.");
  }
  if (typeof window === "undefined" || !window.PublicKeyCredential) {
    throw new Error("This browser does not support WebAuthn / FIDO2.");
  }

  // 1. Request bootstrap registration options with bootstrap token header
  const issued = await api.bootstrapRegistrationOptions(cleanToken);
  const options = issued.publicKey;
  options.challenge = toArrayBuffer(options.challenge as unknown as string);
  if (options.user && typeof options.user.id === "string") {
    options.user.id = toArrayBuffer(options.user.id as unknown as string);
  }
  if (options.excludeCredentials) {
    options.excludeCredentials = options.excludeCredentials.map((c) => ({
      ...c,
      id: toArrayBuffer(c.id as unknown as string),
    }));
  }

  // 2. Invoke browser navigator.credentials.create
  const credential = (await navigator.credentials.create({ publicKey: options })) as PublicKeyCredential | null;
  if (!credential) {
    throw new Error("WebAuthn registration was cancelled.");
  }

  const response = credential.response as AuthenticatorAttestationResponse;

  // 3. Complete bootstrap registration with backend
  const completed = await api.bootstrapRegistrationComplete(
    cleanToken,
    issued.challenge_id,
    label,
    {
      id: credential.id,
      rawId: base64Url(credential.rawId),
      type: credential.type,
      response: {
        attestationObject: base64Url(response.attestationObject),
        clientDataJSON: base64Url(response.clientDataJSON),
      },
    }
  );

  return completed;
}

export async function executeUserEnrollment(issued: { challenge_id: string; publicKey: PublicKeyCredentialCreationOptions }) {
  if (!window.PublicKeyCredential) throw new Error("This browser does not support WebAuthn.");
  const options = issued.publicKey;
  options.challenge = toArrayBuffer(options.challenge as unknown as string);
  options.user.id = toArrayBuffer(options.user.id as unknown as string);
  options.excludeCredentials = options.excludeCredentials?.map(c => ({ ...c, id: toArrayBuffer(c.id as unknown as string) }));
  const credential = await navigator.credentials.create({ publicKey: options }) as PublicKeyCredential | null;
  if (!credential) throw new Error("Enrollment cancelled; request a new invitation from the Owner.");
  const response = credential.response as AuthenticatorAttestationResponse;
  const completed = await api.completeUserActivation(issued.challenge_id, "User passkey", {
    id: credential.id, rawId: base64Url(credential.rawId), type: credential.type,
    response: { attestationObject: base64Url(response.attestationObject), clientDataJSON: base64Url(response.clientDataJSON) },
  });
  if (!completed.registered || !completed.authentication_required) throw new Error("Enrollment could not be confirmed.");
  return completed;
}
