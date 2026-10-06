from datetime import datetime,timedelta,timezone
import pytest
from engine.ai.v2.contracts import TradeCandidate,TradeCandidateAction
NOW=datetime(2026,9,27,6,0,tzinfo=timezone.utc)
def cand(valid=60): return TradeCandidate('c','ctx','NSE:NIFTY:CE',TradeCandidateAction.BUY_CE,NOW-timedelta(seconds=10),NOW+timedelta(seconds=valid),'a'*64,'local-a','m','research','trade-candidate/v1',('p',),(),NOW+timedelta(minutes=2))
def validator():
 from engine.ai.v2.candidates import CandidatePolicy,TradeCandidateValidator
 return TradeCandidateValidator(lambda:NOW,CandidatePolicy('p/v1',('trade-candidate/v1',),('NIFTY','BANKNIFTY')))

def test_only_three_v2_roles_exist():
 from engine.ai.v2.agents import AgentRole
 assert {x.value for x in AgentRole}=={'PRIME_ROUTER','RESEARCH_AGENT','RISK_CHALLENGER'}

def test_challenger_veto_or_unresolved_disagreement_forces_hold():
 from engine.ai.v2.agents import ChallengeDecision
 from engine.ai.v2.orchestrator import IntelligenceCandidateOrchestrator
 o=IntelligenceCandidateOrchestrator(validator())
 assert o.evaluate(cand(),challenge=ChallengeDecision.VETO).effective_action is TradeCandidateAction.HOLD
 assert o.evaluate(cand(),challenge=None).effective_action is TradeCandidateAction.HOLD

def test_challenger_pass_is_not_mint_authority_and_validator_still_controls():
 from engine.ai.v2.agents import ChallengeDecision
 from engine.ai.v2.orchestrator import IntelligenceCandidateOrchestrator
 o=IntelligenceCandidateOrchestrator(validator())
 assert o.evaluate(cand(),challenge=ChallengeDecision.PASS).effective_action is TradeCandidateAction.BUY_CE
 assert o.evaluate(cand(valid=0),challenge=ChallengeDecision.PASS).effective_action is TradeCandidateAction.HOLD

def test_agent_provider_and_tool_scope_are_explicit():
 from engine.ai.v2.agents import AgentRole,AgentSpec,AgentScopeError
 a=AgentSpec('research',AgentRole.RESEARCH_AGENT,('local-a',),('research.read',))
 a.assert_provider_allowed('local-a');a.assert_tool_allowed('research.read')
 with pytest.raises(AgentScopeError):a.assert_provider_allowed('cloud-a')
 with pytest.raises(AgentScopeError):a.assert_tool_allowed('broker.place_order')
 assert not hasattr(a,'risk_limit') and not hasattr(a,'promote')

def test_orchestrator_result_has_no_order_authority_fields():
 from dataclasses import fields
 from engine.ai.v2.agents import ChallengeDecision
 from engine.ai.v2.orchestrator import IntelligenceCandidateOrchestrator
 r=IntelligenceCandidateOrchestrator(validator()).evaluate(cand(),challenge=ChallengeDecision.PASS)
 assert {'approved_order','order_intent','broker_order','quantity'}.isdisjoint({f.name for f in fields(type(r))})
