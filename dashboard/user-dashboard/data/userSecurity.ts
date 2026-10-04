/**
 * AlgoFortis User Dashboard — User Security Preview & Passkeys
 */
export interface SecuritySession {
  id: string;
  device: string;
  browser: string;
  ip: string;
  location: string;
  lastActive: string;
  isCurrent: boolean;
}

export const SECURITY_SESSIONS: SecuritySession[] = [
  {
    id: "sess-01",
    device: "Windows Workstation (Dual Display)",
    browser: "Edge 128 / Chromium",
    ip: "103.241.12.98",
    location: "Mumbai, IN",
    lastActive: "Active Now",
    isCurrent: true,
  },
  {
    id: "sess-02",
    device: "MacBook Pro 16",
    browser: "Safari 17.5",
    ip: "182.74.45.12",
    location: "Bengaluru, IN",
    lastActive: "4 hours ago",
    isCurrent: false,
  },
];

export interface PasskeyCredential {
  id: string;
  label: string;
  registeredAt: string;
  lastUsed: string;
  aaguid: string;
}

export const WEBAUTHN_KEYS: PasskeyCredential[] = [
  {
    id: "key-01",
    label: "Hardware Security Key (sample passkey)",
    registeredAt: "2026-04-12",
    lastUsed: "2026-08-30 04:00 UTC",
    aaguid: "ea9b8d66-4d01-1d21-3ce2-b89c14378a0a",
  },
  {
    id: "key-02",
    label: "Platform Passkey (sample credential)",
    registeredAt: "2026-06-01",
    lastUsed: "2026-08-29 14:02 UTC",
    aaguid: "08987058-cadc-4b81-b6e1-30bb04509bb9",
  },
];
