from engine.ai.contracts import AIAvailability
from engine.ai.evidence import routing_evidence
from engine.ai.laya import LayaMarketIntelligence
from engine.ai.provider_registry import ProviderRegistryUnavailable, ProviderRegistryView


class _Repo:
    def __init__(self):
        self.providers = [{
            "provider_id": "p1", "display_name": "P1", "provider_type": "LOCAL",
            "credential_ref": "vault:provider:p1", "enabled": 1, "authority_state": "AVAILABLE",
        }]
        self.models = [{
            "model_id": "m1", "provider_id": "p1", "display_name": "M1",
            "capability": "RESEARCH", "enabled": 1, "authority_state": "AVAILABLE",
        }]
        self.binding = {
            "agent_id": "laya", "provider_id": "p1", "model_id": "m1",
            "fallback_policy_json": '{"mode":"FAIL_CLOSED"}',
        }

    def get_binding(self, agent_id):
        return self.binding if agent_id == "laya" else None

    def list_providers(self):
        return list(self.providers)

    def list_models(self):
        return list(self.models)


def test_laya_contract_is_market_intelligence_only() -> None:
    laya = LayaMarketIntelligence()
    assert not hasattr(laya, "route_agent")
    assert not hasattr(laya, "dispatch_agent")
    assert not hasattr(laya, "select_provider")
    result = laya.observe(market_context=None, authority_state="UNAVAILABLE")
    assert result.state is AIAvailability.UNAVAILABLE
    assert result.research_disposition == "NO-TRADE"


def test_provider_registry_requires_explicit_available_authority() -> None:
    repo = _Repo()
    binding = ProviderRegistryView(repo).binding_for("laya")
    assert binding.provider_id == "p1"
    assert binding.model_id == "m1"
    assert binding.fallback_mode == "FAIL_CLOSED"

    repo.providers[0]["authority_state"] = "UNKNOWN"
    try:
        ProviderRegistryView(repo).binding_for("laya")
    except ProviderRegistryUnavailable:
        pass
    else:
        raise AssertionError("UNKNOWN provider authority must fail closed")


def test_routing_evidence_is_deterministic_and_prime_owned() -> None:
    a = routing_evidence(agent_id="laya", provider_id="p1", model_id="m1", scope="RESEARCH")
    b = routing_evidence(agent_id="laya", provider_id="p1", model_id="m1", scope="RESEARCH")
    assert a.evidence_ref == b.evidence_ref
    assert a.payload["routing_owner"] == "PRIME"
    assert a.payload["fallback_mode"] == "FAIL_CLOSED"
