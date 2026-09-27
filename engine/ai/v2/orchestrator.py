from __future__ import annotations
from dataclasses import dataclass
from engine.ai.v2.agents import ChallengeDecision
from engine.ai.v2.candidates import CandidateValidationResult,TradeCandidateValidator
from engine.ai.v2.contracts import CandidateValidationVerdict,TradeCandidate,TradeCandidateAction
from engine.reproducibility.codec import CanonicalCodec
@dataclass(frozen=True,slots=True)
class OrchestrationResult:
 candidate_validation:CandidateValidationResult
 challenge:ChallengeDecision|None
 effective_action:TradeCandidateAction
 reason_refs:tuple[str,...]
 fingerprint:str
class ResearchShadowOrchestrator:
 def __init__(self,validator:TradeCandidateValidator):
  if not isinstance(validator,TradeCandidateValidator):raise TypeError('TradeCandidateValidator required')
  self._validator=validator
 def evaluate(self,candidate:TradeCandidate,*,challenge:ChallengeDecision|None)->OrchestrationResult:
  validation=self._validator.validate(candidate);reasons=[r.value for r in validation.reasons]
  if validation.verdict is not CandidateValidationVerdict.VALID:effective=TradeCandidateAction.HOLD
  elif challenge is ChallengeDecision.PASS:effective=candidate.action
  else:
   effective=TradeCandidateAction.HOLD;reasons.append('RISK_CHALLENGER_VETO' if challenge is ChallengeDecision.VETO else 'UNRESOLVED_AGENT_DISAGREEMENT')
  fp=CanonicalCodec.fingerprint('algofortis-ai-orchestration/v1',(('candidate_validation',validation.fingerprint),('challenge','' if challenge is None else challenge.value),('effective_action',effective.value),('reason_refs',tuple(sorted(set(reasons))))))
  return OrchestrationResult(validation,challenge,effective,tuple(sorted(set(reasons))),fp)
