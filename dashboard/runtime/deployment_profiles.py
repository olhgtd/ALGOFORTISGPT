"""AlgoFortis V1 — Deployment Profile Foundation
Authoritative configuration profiles:
1. DESKTOP_LOCAL: Primary active profile for local Windows execution.
2. WINDOWS_VPS: Headless server configuration profile.
3. REMOTE_ENGINE: Placeholder contract for future distributed deployment.
"""
import os
import enum
from typing import Dict, Any, Optional
from dataclasses import dataclass

class DeploymentProfileType(str, enum.Enum):
    DESKTOP_LOCAL = "DESKTOP_LOCAL"
    WINDOWS_VPS = "WINDOWS_VPS"
    REMOTE_ENGINE = "REMOTE_ENGINE"


@dataclass(frozen=True)
class DeploymentProfileConfig:
    profile: DeploymentProfileType
    is_headless: bool
    requires_webview: bool
    allow_remote_connections: bool
    data_root_env_var: str
    listen_host: str
    listen_port: int
    read_only_mode: bool
    disarmed_execution: bool


def resolve_deployment_profile(profile_override: Optional[str] = None) -> DeploymentProfileConfig:
    """Resolve current active deployment profile. Defaults strictly to DESKTOP_LOCAL."""
    raw = profile_override or os.environ.get("ALGOFORTIS_DEPLOYMENT_PROFILE", "DESKTOP_LOCAL")
    
    try:
        profile_type = DeploymentProfileType(raw.upper())
    except ValueError:
        profile_type = DeploymentProfileType.DESKTOP_LOCAL

    if profile_type == DeploymentProfileType.DESKTOP_LOCAL:
        return DeploymentProfileConfig(
            profile=DeploymentProfileType.DESKTOP_LOCAL,
            is_headless=False,
            requires_webview=True,
            allow_remote_connections=False,
            data_root_env_var="LOCALAPPDATA",
            listen_host="127.0.0.1",
            listen_port=0,  # dynamic ephemeral port
            read_only_mode=True,
            disarmed_execution=True
        )
    elif profile_type == DeploymentProfileType.WINDOWS_VPS:
        return DeploymentProfileConfig(
            profile=DeploymentProfileType.WINDOWS_VPS,
            is_headless=True,
            requires_webview=False,
            allow_remote_connections=False,  # Bound to local adapter or reverse proxy
            data_root_env_var="PROGRAMDATA",
            listen_host="127.0.0.1",
            listen_port=8080,
            read_only_mode=True,
            disarmed_execution=True
        )
    elif profile_type == DeploymentProfileType.REMOTE_ENGINE:
        # Placeholder contract: not implemented in V1
        return DeploymentProfileConfig(
            profile=DeploymentProfileType.REMOTE_ENGINE,
            is_headless=True,
            requires_webview=False,
            allow_remote_connections=True,
            data_root_env_var="LOCALAPPDATA",
            listen_host="0.0.0.0",
            listen_port=8443,
            read_only_mode=True,
            disarmed_execution=True
        )
    
    return resolve_deployment_profile("DESKTOP_LOCAL")
