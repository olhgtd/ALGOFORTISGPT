from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"anchor not found in {path}: {old[:140]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

step = Path("dashboard/backend/owner_admin/step_up.py")
anchor = '    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/deployments/(?P<resource>[^/]+)/(?:resume|stop)$"), "DEPLOYMENT_CONTROL"),\n'
extra = anchor + (
    '    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/historical/providers$"), "HISTORICAL_PROVIDER_CONFIG", None),\n'
    '    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/historical/providers/(?P<resource>[^/]+)/toggle$"), "HISTORICAL_PROVIDER_CONFIG"),\n'
    '    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/historical/sync/schedule$"), "HISTORICAL_SYNC_POLICY", None),\n'
    '    DestructiveRoute("POST", re.compile(r"^/api/v1/owner/historical/gaps/repair$"), "HISTORICAL_DATA_REPAIR", None),\n'
)
replace_once(step, anchor, extra)

shell = Path("dashboard/owner-dashboard/OwnerDashboardApp.tsx")
replace_once(shell, '  OwnerConnectionsScreen,\n', '')
replace_once(shell, 'import { DeploymentOperations } from "./authoritative/DeploymentOperations";\n', 'import { DeploymentOperations } from "./authoritative/DeploymentOperations";\nimport { DataOperations } from "./authoritative/DataOperations";\n')
replace_once(shell, '      case "plugins": return <OwnerConnectionsScreen />;\n', '      case "plugins": return <DataOperations />;\n')
