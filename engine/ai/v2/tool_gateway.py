from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import os,re
from typing import Callable,Mapping
from engine.ai.v2.contracts import DataClass
from engine.ai.v2.provider_gateway import _safe_value,_restore
from engine.reproducibility.codec import CanonicalCodec

class ToolGatewayError(ValueError): pass
class ToolDenied(RuntimeError): pass
class ToolAccess(str,Enum): READ='READ'; WRITE='WRITE'
class ToolSideEffect(str,Enum): NONE='NONE'; RESEARCH_ARTIFACT='RESEARCH_ARTIFACT'
_SEMVER=re.compile(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$')
_FORBIDDEN_TOOL_PREFIXES=('broker.','live.','credentials.','credential.','kill_switch.','promotion.')
# Allowlist (fail-closed): a tool id must start with one of these research-only namespaces.
# The denylist above is kept as defence in depth; the allowlist is the primary control.
_ALLOWED_TOOL_PREFIXES=('research.','data.read.')

def _txt(v,n):
 if not isinstance(v,str) or not v.strip(): raise ToolGatewayError(f'{n} required')
 return v.strip()

@dataclass(frozen=True,slots=True)
class ToolManifest:
 tool_id:str;version:str;access:ToolAccess;allowed_path_prefixes:tuple[str,...];allowed_data_classes:tuple[DataClass,...];max_calls:int;max_concurrency:int;side_effect:ToolSideEffect;audit_required:bool
 def __post_init__(self):
  object.__setattr__(self,'tool_id',_txt(self.tool_id,'tool_id')); v=_txt(self.version,'version')
  if _SEMVER.fullmatch(v) is None: raise ToolGatewayError('tool version must be semantic')
  if not isinstance(self.access,ToolAccess) or not isinstance(self.side_effect,ToolSideEffect): raise ToolGatewayError('invalid access/side effect')
  if not isinstance(self.allowed_path_prefixes,tuple) or not self.allowed_path_prefixes or any(not isinstance(x,str) or not x.strip() for x in self.allowed_path_prefixes): raise ToolGatewayError('path scopes required')
  if not isinstance(self.allowed_data_classes,tuple) or not self.allowed_data_classes or any(not isinstance(x,DataClass) for x in self.allowed_data_classes): raise ToolGatewayError('data class scopes required')
  for n in ('max_calls','max_concurrency'):
   x=getattr(self,n)
   if isinstance(x,bool) or not isinstance(x,int) or x<=0: raise ToolGatewayError(f'{n} must be positive')
  if self.audit_required is not True: raise ToolGatewayError('per-call audit is mandatory')

@dataclass(frozen=True,slots=True)
class ToolPolicy:
 agent_id:str;allowed_tool_ids:tuple[str,...];max_budget:int
 def __post_init__(self):
  object.__setattr__(self,'agent_id',_txt(self.agent_id,'agent_id'))
  if not isinstance(self.allowed_tool_ids,tuple) or any(not isinstance(x,str) or not x.strip() for x in self.allowed_tool_ids): raise ToolGatewayError('allowed_tool_ids must be tuple')
  if isinstance(self.max_budget,bool) or not isinstance(self.max_budget,int) or self.max_budget<=0: raise ToolGatewayError('max_budget must be positive')

@dataclass(frozen=True,slots=True)
class ToolInvocation:
 agent_id:str;tool_id:str;access:ToolAccess;path:str;data_classes:tuple[DataClass,...];payload:object;budget_cost:int=1
 def __post_init__(self):
  object.__setattr__(self,'agent_id',_txt(self.agent_id,'agent_id'));object.__setattr__(self,'tool_id',_txt(self.tool_id,'tool_id'));object.__setattr__(self,'path',_txt(self.path,'path'))
  if not isinstance(self.access,ToolAccess) or not isinstance(self.data_classes,tuple) or any(not isinstance(x,DataClass) for x in self.data_classes): raise ToolGatewayError('invalid invocation scope')
  if isinstance(self.budget_cost,bool) or not isinstance(self.budget_cost,int) or self.budget_cost<=0: raise ToolGatewayError('budget_cost must be positive')

@dataclass(frozen=True,slots=True)
class ToolUsageSnapshot:
 calls:int;concurrent:int;budget_used:int
 def __post_init__(self):
  if any(isinstance(x,bool) or not isinstance(x,int) or x<0 for x in (self.calls,self.concurrent,self.budget_used)): raise ToolGatewayError('usage must be non-negative integers')

@dataclass(frozen=True,slots=True)
class ToolAuditEvent:
 agent_id:str;tool_id:str;tool_version:str;access:str;resolved_path:str;data_classes:tuple[str,...];input_fingerprint:str

@dataclass(frozen=True,slots=True)
class ToolResult:
 tool_id:str;payload:object;data_classes:tuple[DataClass,...];fingerprint:str

class ToolGateway:
 def __init__(self,*,manifests:tuple[ToolManifest,...],implementations:Mapping[str,Callable],audit_sink:Callable,usage_supplier:Callable,path_resolver:Callable[[str],str]):
  self._manifests={m.tool_id:m for m in manifests};self._impl=dict(implementations);self._audit=audit_sink;self._usage=usage_supplier;self._resolve=path_resolver
  if len(self._manifests)!=len(manifests): raise ToolGatewayError('duplicate tool manifest')
  if not callable(audit_sink) or not callable(usage_supplier) or not callable(path_resolver): raise ToolGatewayError('gateway dependencies must be callable')
  if set(self._manifests)!=set(self._impl) or any(not callable(v) for v in self._impl.values()): raise ToolGatewayError('exact tool implementation set required')
  for tid in self._manifests:
   low=tid.lower()
   if low.startswith(_FORBIDDEN_TOOL_PREFIXES) or low.startswith('risk.set') or low.startswith('risk.write'): raise ToolGatewayError('forbidden trading authority tool')
   if tid!=low or not low.startswith(_ALLOWED_TOOL_PREFIXES): raise ToolGatewayError('tool id outside research-only allowlist')
  for m in self._manifests.values():
   if m.access is ToolAccess.WRITE and m.side_effect is not ToolSideEffect.RESEARCH_ARTIFACT: raise ToolGatewayError('write tools must declare RESEARCH_ARTIFACT side effect')

 def _path_allowed(self,path:str,m:ToolManifest)->tuple[bool,str]:
  normalized=path.replace('\\','/')
  resolved=self._resolve(normalized)
  for prefix in m.allowed_path_prefixes:
   root=self._resolve(prefix.replace('\\','/'))
   try:
    if os.path.commonpath([resolved,root])==root:return True,resolved
   except ValueError:pass
  return False,resolved

 def invoke(self,inv:ToolInvocation,*,policy:ToolPolicy)->ToolResult:
  if not isinstance(inv,ToolInvocation) or not isinstance(policy,ToolPolicy): raise ToolDenied('typed invocation/policy required')
  m=self._manifests.get(inv.tool_id)
  if m is None: raise ToolDenied('unknown tool')
  if inv.agent_id!=policy.agent_id or inv.tool_id not in policy.allowed_tool_ids: raise ToolDenied('tool not allowlisted for agent')
  if inv.access is not m.access: raise ToolDenied('tool access mismatch')
  if any(c not in m.allowed_data_classes for c in inv.data_classes): raise ToolDenied('data scope denied')
  ok,resolved=self._path_allowed(inv.path,m)
  if not ok: raise ToolDenied('path scope denied')
  u=self._usage(inv.agent_id,inv.tool_id)
  if not isinstance(u,ToolUsageSnapshot): raise ToolDenied('usage evidence missing')
  if u.calls>=m.max_calls or u.concurrent>=m.max_concurrency or u.budget_used+inv.budget_cost>policy.max_budget: raise ToolDenied('tool rate/quota/budget denied')
  canonical=_safe_value(inv.payload)
  infp=CanonicalCodec.fingerprint('algofortis-ai-tool-input/v1',(('agent_id',inv.agent_id),('tool_id',m.tool_id),('tool_version',m.version),('access',inv.access.value),('resolved_path',resolved),('data_classes',tuple(c.value for c in inv.data_classes)),('payload',canonical)))
  event=ToolAuditEvent(inv.agent_id,m.tool_id,m.version,inv.access.value,resolved,tuple(c.value for c in inv.data_classes),infp)
  try:self._audit(event)
  except Exception as exc:raise ToolDenied('tool audit failed') from exc
  try:raw=self._impl[m.tool_id](inv)
  except Exception as exc:raise ToolDenied('tool implementation failed') from exc
  safe=_safe_value(raw);outfp=CanonicalCodec.fingerprint('algofortis-ai-tool-output/v1',(('input_fingerprint',infp),('payload',safe),('data_classes',tuple(c.value for c in m.allowed_data_classes))))
  return ToolResult(m.tool_id,_restore(safe),m.allowed_data_classes,outfp)
