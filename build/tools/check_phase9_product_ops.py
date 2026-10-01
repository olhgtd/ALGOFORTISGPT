from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "dashboard" / "backend" / "product_ops_v2"
FRONTEND = (
    ROOT / "dashboard" / "owner-dashboard" / "data" / "productOps.ts",
    ROOT / "dashboard" / "owner-dashboard" / "screens" / "ProductOperationsScreen.tsx",
    ROOT / "dashboard" / "user-dashboard" / "data" / "privacy.ts",
    ROOT / "dashboard" / "user-dashboard" / "screens" / "PrivacyAndRequestsScreen.tsx",
)

backend_forbidden = (
    "engine.broker_adapters",
    "engine.live",
    "Approved" + "Order(",
    "arm_" + "live",
    "place_" + "order",
    "modify_" + "order",
    "cancel_" + "order",
    "requests.",
    "httpx.",
    "urllib.request",
    "WebAuthnCeremonyService",
)
frontend_forbidden = (
    "/api/v1/live",
    "/api/v1/paper",
    "/api/v1/broker",
    "/api/v1/orders",
    "/api/v1/settings/safe-mode",
    "placeOrder(",
    "modifyOrder(",
    "cancelOrder(",
    "armLive(",
)
required_frontend_endpoints = {
    "productOps.ts": "/api/v1/product-ops/owner/health",
    "privacy.ts": "/api/v1/product-ops/privacy/current",
}

violations: list[str] = []
for path in BACKEND.glob("*.py"):
    text = path.read_text(encoding="utf-8")
    low = text.lower()
    for token in backend_forbidden:
        if token.lower() in low:
            violations.append(f"{path.relative_to(ROOT)}:{token}")

for path in FRONTEND:
    if not path.is_file():
        violations.append(f"{path.relative_to(ROOT)}:MISSING_PHASE9_FRONTEND")
        continue
    text = path.read_text(encoding="utf-8")
    low = text.lower()
    for token in frontend_forbidden:
        if token.lower() in low:
            violations.append(f"{path.relative_to(ROOT)}:{token}")
    expected = required_frontend_endpoints.get(path.name)
    if expected is not None:
        if expected not in text:
            violations.append(f"{path.relative_to(ROOT)}:MISSING_READ_MODEL_ENDPOINT")
        if text.count("/api/v1/") != 1:
            violations.append(f"{path.relative_to(ROOT)}:EXTRA_API_AUTHORITY")

if violations:
    raise SystemExit("PHASE9_PRODUCT_OPS_STATIC_FAIL\n" + "\n".join(violations))

print("PHASE9_PRODUCT_OPS_STATIC_PASS")
print("PHASE9_UI_AUTHORITY=READ_MODEL_ONLY")
print("AI_AUTHORITY=RESEARCH_SHADOW_ONLY")
print("LIVE_STATE=READ_ONLY/DISARMED")
