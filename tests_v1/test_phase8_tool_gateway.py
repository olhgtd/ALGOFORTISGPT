import os
import pytest
from engine.ai.v2.contracts import DataClass

def api():
 from engine.ai.v2.tool_gateway import ToolAccess,ToolManifest,ToolSideEffect,ToolPolicy,ToolInvocation,ToolUsageSnapshot,ToolGateway
 return ToolAccess,ToolManifest,ToolSideEffect,ToolPolicy,ToolInvocation,ToolUsageSnapshot,ToolGateway

def manifest(tool='research.read',access_name='READ',paths=('/safe/research',),max_calls=10,max_conc=2,side='NONE'):
 A,M,S,*_=api(); return M(tool,'1.0.0',getattr(A,access_name),paths,(DataClass.STRATEGY_RESEARCH,),max_calls,max_conc,getattr(S,side),True)
def invocation(tool='research.read',agent='research',access_name='READ',path='/safe/research/file.txt',cost=1):
 A,_,_,_,I,_,_=api();return I(agent,tool,getattr(A,access_name),path,(DataClass.STRATEGY_RESEARCH,),{'q':'x'},cost)
def policy(agent='research',tools=('research.read',),budget=10):
 *_,P,_,_,_=api();return P(agent,tools,budget)
def usage(calls=0,concurrent=0,budget=0):
 *_,U,_=api();return U(calls,concurrent,budget)
def resolver(p): return os.path.realpath(p.replace('\\','/'))

def gateway(manifests=None,impls=None,events=None,usage_value=None):
 *_,G=api(); manifests=manifests or (manifest(),); impls=impls or {'research.read':lambda inv:{'ok':True}}; events=events if events is not None else []
 return G(manifests=manifests,implementations=impls,audit_sink=events.append,usage_supplier=lambda a,t:usage_value or usage(),path_resolver=resolver)

def test_unknown_and_not_allowlisted_tools_are_denied():
 from engine.ai.v2.tool_gateway import ToolDenied
 g=gateway()
 with pytest.raises(ToolDenied):g.invoke(invocation(tool='missing'),policy=policy(tools=('missing',)))
 with pytest.raises(ToolDenied):g.invoke(invocation(),policy=policy(tools=('other',)))

def test_access_and_path_escape_are_denied_before_dispatch():
 from engine.ai.v2.tool_gateway import ToolDenied
 calls=[];g=gateway(impls={'research.read':lambda inv:calls.append(inv)})
 with pytest.raises(ToolDenied):g.invoke(invocation(access_name='WRITE'),policy=policy())
 with pytest.raises(ToolDenied):g.invoke(invocation(path='/safe/research/../secret.txt'),policy=policy())
 with pytest.raises(ToolDenied):g.invoke(invocation(path='\\safe\\research\\..\\secret.txt'),policy=policy())
 assert calls==[]

def test_rate_budget_and_concurrency_excess_are_denied():
 from engine.ai.v2.tool_gateway import ToolDenied
 for u in (usage(calls=10),usage(concurrent=2),usage(budget=10)):
  with pytest.raises(ToolDenied): gateway(usage_value=u).invoke(invocation(),policy=policy())

def test_audit_failure_blocks_dispatch():
 from engine.ai.v2.tool_gateway import ToolGateway,ToolDenied
 calls=[]
 def bad(_):raise RuntimeError('audit')
 g=ToolGateway(manifests=(manifest(),),implementations={'research.read':lambda inv:calls.append(inv)},audit_sink=bad,usage_supplier=lambda a,t:usage(),path_resolver=resolver)
 with pytest.raises(ToolDenied):g.invoke(invocation(),policy=policy())
 assert calls==[]

def test_research_artifact_write_is_scoped_and_output_is_sanitized():
 M=manifest(tool='research.write',access_name='WRITE',paths=('/safe/artifacts',),side='RESEARCH_ARTIFACT')
 calls=[];events=[]
 g=gateway((M,),{'research.write':lambda inv:(calls.append(inv) or {'path':inv.path,'api_token':'SECRET','nested':{'account_id':'ACC','ok':'yes'}})},events)
 r=g.invoke(invocation(tool='research.write',access_name='WRITE',path='/safe/artifacts/report.json'),policy=policy(tools=('research.write',)))
 assert len(calls)==1 and r.payload['nested']['ok']=='yes'
 assert 'SECRET' not in repr(r.payload) and 'ACC' not in repr(r.payload) and 'SECRET' not in repr(events)

def test_forbidden_authority_tools_cannot_be_registered():
 from engine.ai.v2.tool_gateway import ToolGatewayError
 A,M,S,*_=api()
 for tool in ('broker.place_order','live.arm','credentials.read','risk.set_limit','kill_switch.disable','promotion.approve'):
  with pytest.raises(ToolGatewayError): gateway((M(tool,'1.0.0',A.READ,('/safe',),(DataClass.STRATEGY_RESEARCH,),1,1,S.NONE,True),),{tool:lambda i:{}})
