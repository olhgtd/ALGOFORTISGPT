"""Pure replay of safe Phase-8 AI audit evidence."""
from __future__ import annotations
from dataclasses import dataclass
from engine.ai.v2.audit import AIAuditEvent

class ReplayError(ValueError): pass

@dataclass(frozen=True,slots=True)
class ReplayStep:
    event_id:str
    action:str
    sequence:int
    provider_id:str
    model_id:str
    tool_id:str|None
    policy_ref:str
    licensing_ref:str
    input_fingerprint:str
    output_fingerprint:str|None
    status:str

@dataclass(frozen=True,slots=True)
class ReplayChain:
    correlation_id:str
    steps:tuple[ReplayStep,...]


def replay(events:tuple[AIAuditEvent,...])->ReplayChain:
    if not isinstance(events,tuple) or not events: raise ReplayError('events must be non-empty tuple')
    if any(not isinstance(e,AIAuditEvent) for e in events): raise ReplayError('events must be AIAuditEvent')
    correlations={e.correlation_id for e in events}
    if len(correlations)!=1: raise ReplayError('mixed correlation IDs are not replayable together')
    sequences=[e.sequence for e in events]
    if len(set(sequences))!=len(sequences): raise ReplayError('duplicate audit sequence')
    ordered=tuple(sorted(events,key=lambda e:e.sequence))
    steps=tuple(ReplayStep(e.event_id,e.action,e.sequence,e.provider_id,e.model_id,e.tool_id,e.policy_ref,e.licensing_ref,e.input_fingerprint,e.output_fingerprint,e.status) for e in ordered)
    return ReplayChain(ordered[0].correlation_id,steps)

__all__=['ReplayError','ReplayStep','ReplayChain','replay']
