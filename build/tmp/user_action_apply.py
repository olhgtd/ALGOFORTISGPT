from pathlib import Path

path = Path("dashboard/shared/services/integrationClient.ts")
text = path.read_text(encoding="utf-8")
marker = "export interface PromotionRequestReceipt {"
if marker not in text:
    raise SystemExit("marker not found")
if "export async function submitUserStrategy(" in text:
    raise SystemExit("submitUserStrategy already exists")
insert = '''export interface StrategySubmitReceipt {\n  strategy_id: string;\n  version_id: string;\n  stage: string;\n  source_sha256?: string | null;\n}\n\n/** User submits strategy source to canonical governed backend. Fail-closed, no sample fallback. */\nexport async function submitUserStrategy(\n  source: string,\n  protectivePolicyIdentity: string | null = null,\n): Promise<MutationResult<StrategySubmitReceipt>> {\n  const url = `${getApiBaseUrl()}/api/v1/strategies`;\n  if (!isBackendEnabled()) {\n    return { success: false, error: "BACKEND_AUTHORITY_UNAVAILABLE", isFallback: false };\n  }\n  try {\n    const res = await fetchWithTimeout(url, {\n      method: "POST",\n      body: JSON.stringify({\n        source,\n        protective_policy_identity: protectivePolicyIdentity,\n      }),\n    });\n    let json: any = null;\n    try { json = await res.json(); } catch { json = null; }\n    if (res.ok && json) {\n      return { success: true, data: json as StrategySubmitReceipt, isFallback: false };\n    }\n    return {\n      success: false,\n      error: json?.detail || json?.error || `Strategy submission rejected (HTTP ${res.status})`,\n      isFallback: false,\n    };\n  } catch (err: any) {\n    return { success: false, error: err?.message || "Network error", isFallback: false };\n  }\n}\n\n'''
path.write_text(text.replace(marker, insert + marker, 1), encoding="utf-8")
