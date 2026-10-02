"""Create a canonical signed AlgoFortis update manifest.

Production signing material is supplied externally. This tool never generates,
persists, logs, or commits a production private key.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from dashboard.backend.update_service import UpdateService


def _load_private_key(path: Path, password_env: str | None) -> Ed25519PrivateKey:
    password = None
    if password_env:
        raw = os.environ.get(password_env)
        if raw is None:
            raise SystemExit(f"private-key password environment variable {password_env!r} is missing")
        password = raw.encode("utf-8")
    loaded = serialization.load_pem_private_key(path.read_bytes(), password=password)
    if not isinstance(loaded, Ed25519PrivateKey):
        raise SystemExit("release manifest private key must be Ed25519")
    return loaded


def _nonempty(value: str, label: str) -> str:
    value = str(value).strip()
    if not value:
        raise SystemExit(f"{label} must be non-empty")
    return value


def build_manifest(args: argparse.Namespace) -> dict:
    installer_path = Path(args.installer).resolve()
    evidence_path = Path(args.artifact_evidence).resolve()
    installer = installer_path.read_bytes()
    digest = hashlib.sha256(installer).hexdigest()

    evidence = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
    if not isinstance(evidence, dict):
        raise SystemExit("artifact evidence must be a JSON object")
    if evidence.get("schema") != "AlgoFortisReleaseArtifactEvidence/v1":
        raise SystemExit("unsupported artifact evidence schema")
    if str(evidence.get("sha256", "")).lower() != digest:
        raise SystemExit("artifact evidence SHA-256 does not match installer")
    if evidence.get("installer_authenticode_verified") is not True:
        raise SystemExit("installer Authenticode evidence is not verified")
    thumbprint = _nonempty(
        evidence.get("installer_signer_thumbprint", ""),
        "installer signer thumbprint",
    )

    key_id = _nonempty(args.signing_key_id, "signing key id")
    installer_signer_id = _nonempty(
        args.installer_signer_id or key_id,
        "installer signer id",
    )
    key = _load_private_key(Path(args.private_key).resolve(), args.private_key_password_env)

    data = {
        "version": _nonempty(args.version, "version"),
        "channel": _nonempty(args.channel, "channel").upper(),
        "installer_url": _nonempty(args.installer_url, "installer URL"),
        "sha256_checksum": digest,
        "min_compatible_version": _nonempty(
            args.min_compatible_version,
            "minimum compatible version",
        ),
        "security_critical": bool(args.security_critical),
        "release_notes": args.release_notes or "",
        "signing_key_id": key_id,
        "installer_signer_id": installer_signer_id,
        "installer_signature": base64.b64encode(key.sign(installer)).decode("ascii"),
        "installer_authenticode_thumbprint": thumbprint,
        "safe_window_policy_id": _nonempty(
            args.safe_window_policy_id,
            "safe-window policy id",
        ),
        "safe_window_policy_version": _nonempty(
            args.safe_window_policy_version,
            "safe-window policy version",
        ),
    }
    canonical = UpdateService.canonical_manifest_bytes(data)
    data["manifest_signature"] = base64.b64encode(key.sign(canonical)).decode("ascii")
    return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--installer", required=True)
    parser.add_argument("--artifact-evidence", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--channel", choices=("STABLE", "BETA"), required=True)
    parser.add_argument("--installer-url", required=True)
    parser.add_argument("--min-compatible-version", required=True)
    parser.add_argument("--safe-window-policy-id", required=True)
    parser.add_argument("--safe-window-policy-version", required=True)
    parser.add_argument("--signing-key-id", required=True)
    parser.add_argument("--installer-signer-id")
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--private-key-password-env")
    parser.add_argument("--security-critical", action="store_true")
    parser.add_argument("--release-notes", default="")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build_manifest(args)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"SIGNED_UPDATE_MANIFEST={output}")
    print(f"VERSION={manifest['version']}")
    print(f"CHANNEL={manifest['channel']}")
    print(f"SHA256={manifest['sha256_checksum']}")
    print("PRIVATE_KEY_EXPORTED=NO")


if __name__ == "__main__":
    main()
