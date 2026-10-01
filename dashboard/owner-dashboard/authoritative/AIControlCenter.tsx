import React, { useState } from "react";
import {
  bindAIAgent,
  cancelAIJob,
  configureAIModel,
  createAIJob,
  ownerMutationWithStepUp,
  queryOwnerAI,
  setAIAgentPolicy,
} from "./api";
import { AuthorityBadge, AsyncActionButton, SimpleTable } from "./components";
import { DecisionIntelligenceControls } from "./DecisionIntelligenceControls";
import { useAsyncResource } from "./hooks";
import type { AuthorityState } from "../authority";

const asState = (value: unknown): AuthorityState => (
  value === "AVAILABLE" || value === "STALE" || value === "UNKNOWN" || value === "UNAVAILABLE"
    ? value
    : "UNKNOWN"
);
const asRows = (value: unknown): any[] => Array.isArray(value) ? value : [];

async function saveAIProviderMetadata(providerId: string, displayName: string, providerType: string) {
  return ownerMutationWithStepUp<any>({
    actionFamily: "AI_PROVIDER_CONFIG",
    resourceRef: providerId,
    path: `/api/v1/owner/admin/ai/providers/${encodeURIComponent(providerId)}/metadata`,
    body: { display_name: displayName, provider_type: providerType, enabled: true },
  });
}

async function storeAIProviderCredential(providerId: string, token: string) {
  return ownerMutationWithStepUp<any>({
    actionFamily: "AI_PROVIDER_CREDENTIAL",
    resourceRef: providerId,
    path: `/api/v1/owner/admin/ai/providers/${encodeURIComponent(providerId)}/credential`,
    body: { token },
  });
}

async function verifyAIProvider(providerId: string, modelId?: string) {
  return ownerMutationWithStepUp<any>({
    actionFamily: "AI_PROVIDER_VERIFY",
    resourceRef: providerId,
    path: `/api/v1/owner/admin/ai/providers/${encodeURIComponent(providerId)}/verify`,
    body: { model_id: modelId || null },
  });
}

export const OwnerAIControlScreen: React.FC = () => {
  const ai = useAsyncResource(queryOwnerAI);
  const [providerId, setProviderId] = useState("");
  const [providerName, setProviderName] = useState("");
  const [providerType, setProviderType] = useState("OPENAI_COMPATIBLE");
  const [providerSecret, setProviderSecret] = useState("");
  const [modelId, setModelId] = useState("");
  const [modelName, setModelName] = useState("");
  const [agentId, setAgentId] = useState("laya");
  const [jobType, setJobType] = useState("MARKET_INTELLIGENCE");

  const payload: any = ai.data || {};
  const state = ai.error ? "UNAVAILABLE" : ai.loading ? "UNKNOWN" : asState(payload.authority_state);
  const providers = asRows(payload.providers);
  const models = asRows(payload.models);
  const agents = asRows(payload.agents);
  const jobs = asRows(payload.jobs);
  const selectedProvider = providerId || providers[0]?.provider_id || "";
  const compatibleModels = models.filter((model) => !selectedProvider || model.provider_id === selectedProvider);
  const selectedModel = modelId || compatibleModels[0]?.model_id || "";

  return <>
    <div className="v3-screen-head">
      <div>
        <h2 className="v3-screen-title">AI Control Center</h2>
        <p className="v3-screen-sub">Strategy remains independent. Laya and optional 0..N AI providers can review or create research/backtest/paper candidates. RiskGateV2 remains the only order-approval authority.</p>
      </div>
    </div>
    <div className="dev-preview-banner" style={{ marginBottom: 18 }}>
      <span className="banner-tag">AI SAFETY</span>
      <span>RESEARCH / BACKTEST / PAPER INTELLIGENCE · Owner-controlled scope · Live READ_ONLY/DISARMED · no broker mutation</span>
    </div>

    <div className="v3-grid">
      <DecisionIntelligenceControls />

      <section className="v3-region v3-sp12">
        <div className="v3-region-head"><span className="v3-region-title">Agents</span><AuthorityBadge state={state} /></div>
        <SimpleTable rows={agents} columns={[
          { key: "display_name", label: "Agent" },
          { key: "role_type", label: "Role" },
          { key: "authority_state", label: "Authority" },
          { key: "provider", label: "Provider", render: (row) => row.provider?.display_name || "—" },
          { key: "model", label: "Model", render: (row) => row.model?.display_name || "—" },
          { key: "actions", label: "Policy", render: (row) => <AsyncActionButton label={row.enabled ? "Disable" : "Enable"} tone="warn" onRun={() => setAIAgentPolicy(row.agent_id, !row.enabled)} onDone={ai.refresh} /> },
        ]} />
      </section>

      <section className="v3-region v3-sp6">
        <div className="v3-region-head"><span className="v3-region-title">Provider Registry</span></div>
        <p className="v3-region-note">Save metadata first. Provider keys/tokens are sent only to the backend DPAPI vault, never stored in UI/browser storage and never returned. Verification remains backend-owned.</p>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <input className="v3-input" value={providerId} onChange={(e) => setProviderId(e.target.value)} placeholder="Provider ID" />
          <input className="v3-input" value={providerName} onChange={(e) => setProviderName(e.target.value)} placeholder="Display name" />
          <select className="v3-input" value={providerType} onChange={(e) => setProviderType(e.target.value)}>
            <option value="OPENAI_COMPATIBLE">OpenAI-compatible</option>
            <option value="LOCAL">Local</option>
            <option value="NATIVE">Native adapter</option>
          </select>
          <AsyncActionButton label="Save provider metadata" onRun={async () => {
            if (!providerId || !providerName) throw new Error("Provider ID and name required");
            await saveAIProviderMetadata(providerId, providerName, providerType);
            await ai.refresh();
          }} />
          <input
            className="v3-input"
            type="password"
            autoComplete="off"
            value={providerSecret}
            onChange={(e) => setProviderSecret(e.target.value)}
            placeholder="API key / token — stored encrypted, never displayed again"
          />
          <AsyncActionButton label="Store credential securely" tone="warn" disabled={!selectedProvider || !providerSecret} onRun={async () => {
            await storeAIProviderCredential(selectedProvider, providerSecret);
            setProviderSecret("");
            await ai.refresh();
          }} />
          <AsyncActionButton label="Verify provider/model" tone="warn" disabled={!selectedProvider} onRun={async () => {
            await verifyAIProvider(selectedProvider, selectedModel || undefined);
            await ai.refresh();
          }} />
        </div>
        <SimpleTable rows={providers} columns={[
          { key: "provider_id", label: "ID" },
          { key: "display_name", label: "Provider" },
          { key: "provider_type", label: "Type" },
          { key: "authority_state", label: "State" },
          { key: "credential_configured", label: "Credential", render: (row) => row.credential_configured ? "CONFIGURED" : "NONE" },
        ]} />
      </section>

      <section className="v3-region v3-sp6">
        <div className="v3-region-head"><span className="v3-region-title">Model Registry</span></div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <input className="v3-input" value={modelId} onChange={(e) => setModelId(e.target.value)} placeholder="Model ID" />
          <input className="v3-input" value={modelName} onChange={(e) => setModelName(e.target.value)} placeholder="Display name" />
          <AsyncActionButton label="Save model" onRun={async () => {
            if (!modelId || !modelName || !selectedProvider) throw new Error("Model and provider required");
            await configureAIModel(modelId, {
              provider_id: selectedProvider,
              display_name: modelName,
              capability: "RESEARCH",
              enabled: true,
              authority_state: "UNKNOWN",
            });
            await ai.refresh();
          }} />
        </div>
        <SimpleTable rows={models} columns={[
          { key: "model_id", label: "ID" },
          { key: "provider_id", label: "Provider" },
          { key: "display_name", label: "Model" },
          { key: "authority_state", label: "State" },
        ]} />
      </section>

      <section className="v3-region v3-sp12">
        <div className="v3-region-head"><span className="v3-region-title">Agent Binding</span></div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <select className="v3-input" value={agentId} onChange={(e) => setAgentId(e.target.value)}>
            {["prime", "laya", "research", "risk-challenger"].map((id) => <option key={id} value={id}>{id}</option>)}
          </select>
          <select className="v3-input" value={selectedProvider} onChange={(e) => { setProviderId(e.target.value); setModelId(""); }}>
            {providers.map((provider) => <option key={provider.provider_id} value={provider.provider_id}>{provider.display_name || provider.provider_id}</option>)}
          </select>
          <select className="v3-input" value={selectedModel} onChange={(e) => setModelId(e.target.value)}>
            {compatibleModels.map((model) => <option key={model.model_id} value={model.model_id}>{model.display_name || model.model_id}</option>)}
          </select>
          <AsyncActionButton label="Bind (FAIL_CLOSED)" disabled={!selectedProvider || !selectedModel} onRun={async () => {
            await bindAIAgent(agentId, { provider_id: selectedProvider, model_id: selectedModel, fallback_policy: { mode: "FAIL_CLOSED" } });
            await ai.refresh();
          }} />
        </div>
      </section>

      <section className="v3-region v3-sp12">
        <div className="v3-region-head"><span className="v3-region-title">Decision Intelligence Jobs</span></div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
          <select className="v3-input" value={jobType} onChange={(e) => setJobType(e.target.value)}>
            <option value="MARKET_INTELLIGENCE">Laya · Market intelligence</option>
            <option value="STRATEGY_REVIEW">Strategy review</option>
            <option value="INDEPENDENT_CANDIDATE">Independent research candidate</option>
            <option value="STRATEGY_HUNTING">Strategy Hunting</option>
            <option value="STRATEGY_RESEARCH">Research Agent</option>
            <option value="EVIDENCE_RESEARCH">Research evidence</option>
            <option value="RISK_CHALLENGE">Risk Challenger</option>
            <option value="ORCHESTRATE">Prime orchestration</option>
          </select>
          <AsyncActionButton label="Create research job" onRun={async () => {
            await createAIJob({ job_type: jobType, scope: "RESEARCH", request: {}, auto_submit: false });
            await ai.refresh();
          }} />
        </div>
        <SimpleTable rows={jobs} columns={[
          { key: "job_id", label: "Job" },
          { key: "agent_id", label: "Agent" },
          { key: "job_type", label: "Type" },
          { key: "scope", label: "Scope" },
          { key: "status", label: "Status" },
          { key: "evidence_ref", label: "Evidence" },
          { key: "failure_reason", label: "Reason" },
          { key: "actions", label: "Action", render: (row) => <AsyncActionButton label="Cancel" tone="warn" disabled={!['QUEUED','BLOCKED'].includes(row.status)} onRun={() => cancelAIJob(row.job_id)} onDone={ai.refresh} /> },
        ]} />
      </section>
    </div>
  </>;
};
