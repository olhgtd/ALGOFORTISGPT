"""Bounded, interpreted strategy adapter for StrategySignalGenerator/1.0.

No Python import, eval, exec, bytecode, user callable, or object attribute is
executed. The accepted syntax is deliberately finite; see P0_STRATEGY_ARTIFACTS.md.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import math
import operator
from pathlib import Path

from engine.strategy.base import Signal, StrategySignalGenerator
from .strategy_validation import StrategyValidationError

ADAPTER_VERSION = "sentinelx-bounded-strategy/v1"


def bar(data, field: str, lookback: int = 0) -> float:
    """Read only an already assembled single-stream, as-of engine data view."""
    if field not in {"open", "high", "low", "close", "volume"} or type(lookback) is not int or not 0 <= lookback <= 10000:
        raise StrategyValidationError("Unsupported bar request")
    if not isinstance(data, dict) or len(data) != 1:
        raise StrategyValidationError("Single-stream data required")
    frame = next(iter(data.values()))
    if len(frame) <= lookback:
        raise StrategyValidationError("Insufficient strategy lookback")
    return float(frame[field].iloc[-1-lookback])


class BoundedStrategy(StrategySignalGenerator):
    interface_version = "1.0"
    _binary = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
               ast.Div: operator.truediv, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv}
    _compare = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
                ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}

    def __init__(self, source: str, strategy_id: str):
        self.id = strategy_id
        self.failure = None
        self.signals = []
        if len(source.encode("utf-8")) > 200000:
            raise StrategyValidationError("Artifact exceeds execution limit")
        try:
            tree = ast.parse(source)
        except (SyntaxError, RecursionError):
            raise StrategyValidationError("Unsupported artifact syntax") from None
        nodes = list(ast.walk(tree))
        if len(nodes) > 1024:
            raise StrategyValidationError("Artifact exceeds syntax limit")
        classes = []
        for n in tree.body:
            if isinstance(n, ast.ImportFrom):
                allowed = {"engine.strategy.base": {"Signal", "StrategySignalGenerator"},
                           "dashboard.backend.strategy_execution": {"bar"}}
                if n.level or n.module not in allowed or any(a.asname or a.name not in allowed[n.module] for a in n.names):
                    raise StrategyValidationError("Unsupported artifact import")
            elif isinstance(n, ast.ClassDef): classes.append(n)
            elif not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)):
                raise StrategyValidationError("Unsupported top-level statement")
        if len(classes) != 1:
            raise StrategyValidationError("Exactly one strategy class required")
        cls = classes[0]
        if cls.decorator_list or cls.keywords or len(cls.bases) != 1 or not isinstance(cls.bases[0], ast.Name) or cls.bases[0].id != "StrategySignalGenerator":
            raise StrategyValidationError("Unsupported strategy class")
        constants = {}; methods = []
        for n in cls.body:
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                name = n.targets[0].id
                if name not in {"interface_version", "state_schema"} or name in constants:
                    raise StrategyValidationError("Unsupported strategy declaration")
                try: constants[name] = ast.literal_eval(n.value)
                except (ValueError, TypeError): raise StrategyValidationError("Literal declarations required") from None
            elif isinstance(n, ast.FunctionDef): methods.append(n)
            elif not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)):
                raise StrategyValidationError("Unsupported class statement")
        if constants.get("interface_version") != "1.0" or len(methods) != 1:
            raise StrategyValidationError("StrategySignalGenerator/1.0 required")
        fn = methods[0]
        if (fn.name != "generate_signal" or [a.arg for a in fn.args.args] != ["self", "data", "state"]
                or fn.decorator_list or fn.args.defaults or fn.args.kw_defaults or fn.args.vararg or fn.args.kwarg or fn.args.posonlyargs or fn.args.kwonlyargs):
            raise StrategyValidationError("generate_signal(self, data, state) required")
        self.state_schema = constants.get("state_schema", {})
        if not isinstance(self.state_schema, dict) or len(self.state_schema) > 64:
            raise StrategyValidationError("Bounded state dictionary required")
        for k,v in self.state_schema.items():
            if not isinstance(k,str) or len(k)>64: raise StrategyValidationError("Invalid state key")
            self._scalar(v)
        self._body = fn.body
        allowed_nodes = (ast.Assign, ast.AugAssign, ast.If, ast.Return, ast.Pass, ast.Expr,
            ast.Name, ast.Constant, ast.Subscript, ast.Load, ast.Store, ast.BinOp, ast.UnaryOp,
            ast.BoolOp, ast.Compare, ast.Call, ast.Dict, ast.keyword, ast.IfExp,
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.FloorDiv, ast.USub, ast.UAdd,
            ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)
        for statement in fn.body:
            for n in ast.walk(statement):
                if not isinstance(n, allowed_nodes): raise StrategyValidationError("Unsupported executable syntax")
                if isinstance(n,ast.Name) and n.id.startswith("_"): raise StrategyValidationError("Private names forbidden")
                if isinstance(n,ast.Subscript) and not (isinstance(n.value,ast.Name) and n.value.id=="state" and isinstance(n.slice,ast.Constant) and n.slice.value in self.state_schema):
                    raise StrategyValidationError("Only declared state keys may be indexed")
                if isinstance(n,ast.Call) and (not isinstance(n.func,ast.Name) or n.func.id not in {"Signal","bar","abs","min","max"}):
                    raise StrategyValidationError("Unsupported strategy call")
                if isinstance(n,ast.Assign) and len(n.targets)!=1: raise StrategyValidationError("Single assignment required")
                if isinstance(n,(ast.Assign,ast.AugAssign)):
                    target = n.targets[0] if isinstance(n,ast.Assign) else n.target
                    if not isinstance(target,(ast.Name,ast.Subscript)) or isinstance(target,ast.Name) and target.id in {"self","state","data","Signal","bar","abs","min","max"}:
                        raise StrategyValidationError("Invalid assignment target")

    @staticmethod
    def _scalar(value):
        if type(value) not in {int,float,bool,str,type(None)} or isinstance(value,str) and len(value)>256:
            raise StrategyValidationError("Unsupported scalar")
        if type(value) in {int,float} and (not math.isfinite(value) or abs(value)>1e18):
            raise StrategyValidationError("Numeric execution limit")
        return value

    def _expr(self, node, local, state, data):
        if isinstance(node,ast.Constant): return self._scalar(node.value)
        if isinstance(node,ast.Name): return local[node.id]
        if isinstance(node,ast.Subscript): return state[node.slice.value]
        if isinstance(node,ast.Dict):
            if len(node.keys)>32: raise StrategyValidationError("Metadata limit")
            return {self._expr(k,local,state,data):self._expr(v,local,state,data) for k,v in zip(node.keys,node.values)}
        if isinstance(node,ast.BinOp):
            a,b = self._expr(node.left,local,state,data),self._expr(node.right,local,state,data)
            if type(a) not in {int,float} or type(b) not in {int,float}: raise StrategyValidationError("Numeric operands required")
            return self._scalar(self._binary[type(node.op)](a,b))
        if isinstance(node,ast.UnaryOp):
            value=self._expr(node.operand,local,state,data)
            if isinstance(node.op,ast.Not): return not value
            if type(value) not in {int,float}: raise StrategyValidationError("Numeric operand required")
            return self._scalar(-value if isinstance(node.op,ast.USub) else +value)
        if isinstance(node,ast.BoolOp):
            for n in node.values:
                value=self._expr(n,local,state,data)
                if isinstance(node.op,ast.And) and not value or isinstance(node.op,ast.Or) and value: return value
            return value
        if isinstance(node,ast.Compare):
            left=self._expr(node.left,local,state,data)
            for op,right_node in zip(node.ops,node.comparators):
                right=self._expr(right_node,local,state,data)
                if not self._compare[type(op)](left,right): return False
                left=right
            return True
        if isinstance(node,ast.IfExp): return self._expr(node.body if self._expr(node.test,local,state,data) else node.orelse,local,state,data)
        if isinstance(node,ast.Call):
            name=node.func.id
            if name=="bar":
                if not node.args or not isinstance(node.args[0],ast.Name) or node.args[0].id!="data" or node.keywords: raise StrategyValidationError("bar(data, field, lookback) required")
                return self._scalar(bar(data,*[self._expr(n,local,state,data) for n in node.args[1:]]))
            args=[self._expr(n,local,state,data) for n in node.args]
            kwargs={n.arg:self._expr(n.value,local,state,data) for n in node.keywords}
            if name=="Signal": return Signal(*args,**kwargs)
            if kwargs or not args or len(args)>32 or any(type(a) not in {int,float} for a in args): raise StrategyValidationError("Numeric arguments required")
            return self._scalar({"abs":abs,"min":min,"max":max}[name](*args))
        raise StrategyValidationError("Unsupported expression")

    def _statements(self, statements, local, state, data):
        for n in statements:
            if isinstance(n,ast.Return): return self._expr(n.value,local,state,data)
            if isinstance(n,ast.If):
                result=self._statements(n.body if self._expr(n.test,local,state,data) else n.orelse,local,state,data)
                if result is not None: return result
            elif isinstance(n,(ast.Assign,ast.AugAssign)):
                target=n.targets[0] if isinstance(n,ast.Assign) else n.target
                value=self._expr(n.value,local,state,data)
                if isinstance(n,ast.AugAssign):
                    prior=local[target.id] if isinstance(target,ast.Name) else state[target.slice.value]
                    if type(prior) not in {int,float} or type(value) not in {int,float}: raise StrategyValidationError("Numeric assignment required")
                    value=self._binary[type(n.op)](prior,value)
                value=self._scalar(value)
                if isinstance(target,ast.Name): local[target.id]=value
                else: state[target.slice.value]=value
            elif isinstance(n,ast.Expr):
                if not isinstance(n.value,ast.Constant) or not isinstance(n.value.value,str): raise StrategyValidationError("Unsupported expression statement")
            elif not isinstance(n,(ast.If,ast.Pass)): raise StrategyValidationError("Unsupported statement")
        return None

    def generate_signal(self, data, state):
        try:
            result=self._statements(self._body,{},state,data)
            if not isinstance(result,Signal): raise StrategyValidationError("Strategy did not return Signal")
            self.signals.append({"action":result.action,"confidence":result.confidence,"metadata":copy.deepcopy(result.metadata)})
            return result
        except Exception:
            self.failure="STRATEGY_EVALUATION_FAILED"
            # The existing engine Rule 7 records this and produces HOLD. The
            # coordinator detects failure and persists FAILED, without metrics.
            raise StrategyValidationError(self.failure) from None


def validate_bounded_strategy_source(source: str, strategy_id: str = "validation-probe") -> tuple[bool, str | None]:
    """Validate that source conforms to BoundedStrategy execution contract without executing signals."""
    if not isinstance(source, str) or not source.strip():
        return False, "Strategy source is empty"
    try:
        BoundedStrategy(source, strategy_id)
        return True, None
    except StrategyValidationError as exc:
        return False, str(exc)
    except Exception as exc:
        return False, f"Unexpected validation error: {exc}"


class BoundedConformanceAuthority:
    def validate_source(self, source: str) -> tuple[bool, str | None]:
        return validate_bounded_strategy_source(source)

    def validate_version(self, version) -> bool:
        payload = Path(version.source_artifact).read_bytes()
        if hashlib.sha256(payload).hexdigest() != version.source_sha256:
            return False
        try:
            BoundedStrategy(payload.decode("utf-8"), str(version.strategy_id))
            return True
        except (StrategyValidationError, ValueError, TypeError, RecursionError):
            return False

