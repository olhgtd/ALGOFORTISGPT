"""Developer-only localhost composition for manual Phase 9 dashboard testing."""
from decimal import Decimal
from pathlib import Path
from uuid import UUID
import os

from engine.persistence.sqlite_store import SQLitePaperStateStore
from .api import create_app
from .core_audit import MandatoryCoreSecurityAudit
from .domain import Lifecycle, Role, UserIdentity
from .governance_store import SQLiteGovernanceStore
from .security import SecurityConfiguration, WebAuthnCeremonyService, WebAuthnRelyingParty
from .security_store import SQLiteSecurityStore
from .identity import local_owner
from dashboard.runtime.paths import RuntimePaths, RuntimeMode

if os.environ.get("ALGOFORTIS_APP_MODE", "DEVELOPMENT").upper() != "DEVELOPMENT":
    raise RuntimeError("dev_app is DEVELOPMENT only; use the explicit runtime controller")
_root = RuntimePaths.resolve(RuntimeMode.DEVELOPMENT, data_root=Path(os.environ["ALGOFORTIS_DEV_DATA_ROOT"]) if os.environ.get("ALGOFORTIS_DEV_DATA_ROOT") else None).root
_origin = os.environ.get("ALGOFORTIS_DEV_ORIGIN", "http://127.0.0.1:5173")
_security = SQLiteSecurityStore(_root / "security" / "algofortis_security.sqlite3", seed_governance=False)
_governance = SQLiteGovernanceStore(_root / "governance" / "algofortis_governance.sqlite3")
_core = SQLitePaperStateStore(_root / "core-audit.sqlite3", account_id="phase9-development", starting_capital=Decimal("1.00"), audit_source_identity="phase9-development")
_ceremonies = WebAuthnCeremonyService(store=_security, normal_rp=WebAuthnRelyingParty("localhost", _origin.replace("127.0.0.1", "localhost"), development_only=True))
(_root / "config").mkdir(exist_ok=True)
app = create_app(owner=local_owner(_security, _root / "config" / "identity.json"), config=SecurityConfiguration(normal_mtls_required=False), security_store=_security, governance_store=_governance, webauthn_ceremonies=_ceremonies, core_security_audit=MandatoryCoreSecurityAudit(audit_store=_core, security_store=_security), artifact_root=_root / "users")
