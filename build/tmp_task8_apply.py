from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"anchor not found in {path}: {old[:140]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

shell = Path("dashboard/owner-dashboard/OwnerDashboardApp.tsx")
replace_once(shell, '  OwnerSystemScreen,\n', '')
replace_once(shell, 'import { RiskSafetyScreen } from "./authoritative/RiskSafetyScreen";\n', 'import { RiskSafetyScreen } from "./authoritative/RiskSafetyScreen";\nimport { SystemOperations } from "./authoritative/SystemOperations";\n')
replace_once(shell, '      case "system": return <OwnerSystemScreen />;\n', '      case "system": return <SystemOperations />;\n')
