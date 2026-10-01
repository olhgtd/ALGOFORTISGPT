"""Deterministic G8 evidence for Phase-8 AI research/shadow qualification."""
from __future__ import annotations
from dataclasses import dataclass
from engine.reproducibility.codec import CanonicalCodec

class G8EvidenceError(ValueError): pass

REQUIRED_G8_MARKERS=(
    'AI_AUTHORITY=RESEARCH_SHADOW_ONLY',
    'APPROVED_ORDER_AUTHORITY=RISK_GATE_V2_ONLY',
    'PROVIDER_SCOPE=ONE_LOCAL_ONE_CLOUD',
    'COMMITTEE_ENSEMBLE=DEFERRED_T2',
    'PROVIDER_DATA_GATE=ALLOWLIST_REDACT_FAIL_CLOSED',
    'CLOUD_DATA_EGRESS=LICENSING_PROVENANCE_REQUIRED',
    'TRADE_CANDIDATE=NON_EXECUTABLE_TTL_PROVENANCE',
    'STALE_CANDIDATE=DISCARD_NO_TRADE',
    'TOOL_GATEWAY=DENY_BY_DEFAULT_QUOTA_AUDIT',
    'PROMPT_INJECTION=UNTRUSTED_CONTENT_BOUNDARY',
    'PROVIDER_OUTAGE=NO_TRADE_OR_APPROVED_FALLBACK',
    'LIVE_STATE=READ_ONLY/DISARMED',
    'G8_ENABLES_REAL_MONEY_TRADING=NO',
)

def validate_g8_markers(markers:tuple[str,...])->None:
    if not isinstance(markers,tuple): raise G8EvidenceError('markers must be tuple')
    if markers != REQUIRED_G8_MARKERS: raise G8EvidenceError('G8 markers missing, reordered, or changed')

@dataclass(frozen=True,slots=True)
class G8Evidence:
    markers:tuple[str,...]
    fingerprint:str
    def text(self)->str:
        return '\n'.join((*self.markers,f'G8_FINGERPRINT={self.fingerprint}'))+'\n'

def build_g8_evidence()->G8Evidence:
    markers=REQUIRED_G8_MARKERS
    validate_g8_markers(markers)
    fp=CanonicalCodec.fingerprint('algofortis-phase8-g8-evidence/v1',(('markers',markers),))
    return G8Evidence(markers,fp)

__all__=['G8EvidenceError','REQUIRED_G8_MARKERS','G8Evidence','validate_g8_markers','build_g8_evidence']
