import React, { useMemo, useState } from "react";
import { AsyncActionButton, SimpleTable } from "./components";
import { useAsyncResource } from "./hooks";
import { ownerFetch, ownerMutationWithStepUp } from "./api";

const CAPS = [
  "ACCESS_LAYA_ANALYSIS",
  "ACCESS_AI_REVIEW",
  "ACCESS_INTELLIGENCE_CANDIDATES",
  "ACCESS_STRATEGY_HUNTING",
  "ACCESS_ADVANCED_RESEARCH",
];

async function queryDecisionIntelligence() {
  return ownerFetch<any>("/api/v1/owner/admin/ai/intelligence");
}

export const DecisionIntelligenceControls: React.FC = () => {
  const resource = useAsyncResource(queryDecisionIntelligence);
  const payload: any = resource.data || {};
  const currentPolicy = payload.market_watch_policy?.value || {};
  const currentQueue = payload.provider_queue?.value || {};
  const [instruments, setInstruments] = useState((currentPolicy.allowed_instruments || ["NIFTY", "BANKNIFTY", "SENSEX"]).join(","));
  const [providerId, setProviderId] = useState(currentPolicy.provider_id || "");
  const [modelId, setModelId] = useState(currentPolicy.model_id || "");
  const [frequency, setFrequency] = useState(String(currentPolicy.frequency_seconds || 60));
  const [ttl, setTtl] = useState(String(currentPolicy.task_ttl_seconds || 30));
  const [reviewMode, setReviewMode] = useState(currentPolicy.strategy_review_mode || "OPTIONAL");
  const [queueConcurrency, setQueueConcurrency] = useState(String(currentQueue.max_concurrency || 2));
  const [queueSize, setQueueSize] = useState(String(currentQueue.max_queue_size || 32));
  const [userId, setUserId] = useState("");
  const [selectedCaps, setSelectedCaps] = useState<string[]>([]);

  const scopeRows = Array.isArray(payload.scope_requests) ? payload.scope_requests : [];
  const huntingEnabled = payload.strategy_hunting?.value?.enabled === true;
  const providerOptions = Array.isArray(payload.providers) ? payload.providers : [];
  const modelOptions = Array.isArray(payload.models) ? payload.models : [];
  const inferredProvider = providerId || providerOptions[0]?.provider_id || "";
  const compatibleModels = useMemo(
    () => modelOptions.filter((row: any) => !inferredProvider || row.provider_id === inferredProvider),
    [modelOptions, inferredProvider],
  );
  const inferredModel = modelId || compatibleModels[0]?.model_id || "";

  const savePolicy = async () => {
    if (!inferredProvider || !inferredModel) throw new Error("Provider and model required");
    await ownerMutationWithStepUp({
      actionFamily: "AI_MONITORING_POLICY",
      path: "/api/v1/owner/admin/ai/intelligence/market-watch-policy",
      body: {
        policy_ref: "owner-market-watch/v1",
        policy_version: "1.0.0",
        allowed_instruments: instruments.split(",").map((item: string) => item.trim()).filter(Boolean),
        frequency_seconds: Number(frequency),
        task_ttl_seconds: Number(ttl),
        provider_id: inferredProvider,
        model_id: inferredModel,
        allowed_trigger_types: ["SCHEDULED", "EVENT", "OWNER"],
        allowed_task_classes: ["ACTIVE_CANDIDATE_REVIEW", "REGIME_EVENT", "SCHEDULED_MONITORING", "STRATEGY_HUNTING", "LOW_PRIORITY_RESEARCH"],
        allowed_timeframes: ["1m", "5m"],
        strategy_review_mode: reviewMode,
        independent_candidate_scan: true,
      },
    });
    await resource.refresh();
  };

  const saveQueue = async () => {
    if (!inferredProvider) throw new Error("Provider required");
    await ownerMutationWithStepUp({
      actionFamily: "AI_PROVIDER_QUEUE_POLICY",
      path: "/api/v1/owner/admin/ai/intelligence/provider-queue",
      body: {
        policy_ref: `owner-provider-queue/${inferredProvider}/v1`,
        provider_id: inferredProvider,
        max_concurrency: Number(queueConcurrency),
        max_queue_size: Number(queueSize),
        retry_after_seconds: 5,
        allowed_fallback_provider_ids: [],
        max_requests_per_window: null,
        window_seconds: 60,
      },
    });
    await resource.refresh();
  };

  const setHunting = async (enabled: boolean) => {
    await ownerMutationWithStepUp({
      actionFamily: "AI_STRATEGY_HUNTING_POLICY",
      path: "/api/v1/owner/admin/ai/intelligence/strategy-hunting",
      body: { enabled, data_policy_ref: "OD-V2-16" },
    });
    await resource.refresh();
  };

  const saveEntitlements = async () => {
    if (!userId.trim()) throw new Error("User ID required");
    await ownerMutationWithStepUp({
      actionFamily: "AI_ENTITLEMENT_CHANGE",
      resourceRef: userId.trim(),
      path: `/api/v1/owner/admin/ai/intelligence/entitlements/${encodeURIComponent(userId.trim())}`,
      body: { capabilities: selectedCaps },
    });
  };

  const decideScope = async (requestId: string, decision: "APPROVE" | "DENY") => {
    await ownerMutationWithStepUp({
      actionFamily: "AI_SCOPE_POLICY",
      resourceRef: requestId,
      path: `/api/v1/owner/admin/ai/intelligence/scope-requests/${encodeURIComponent(requestId)}/decision`,
      body: { decision },
    });
    await resource.refresh();
  };

  return <section className="v3-region v3-sp12">
    <div className="v3-region-head">
      <span className="v3-region-title">Decision Intelligence</span>
      <span className="v3-region-note">Owner-only · RiskGateV2 authority · Live READ_ONLY/DISARMED</span>
    </div>
    <div className="v3-grid" style={{ marginTop: 12 }}>
      <div className="v3-region v3-sp6">
        <strong>MarketWatchPolicy</strong>
        <p className="v3-region-note">Scope/cadence is versioned Owner policy. AI/Laya cannot self-expand it.</p>
        <input className="v3-input" value={instruments} onChange={(e) => setInstruments(e.target.value)} placeholder="NIFTY,BANKNIFTY,SENSEX" />
        <select className="v3-input" value={inferredProvider} onChange={(e) => { setProviderId(e.target.value); setModelId(""); }}>
          {providerOptions.map((row: any) => <option key={row.provider_id} value={row.provider_id}>{row.display_name || row.provider_id}</option>)}
        </select>
        <select className="v3-input" value={inferredModel} onChange={(e) => setModelId(e.target.value)}>
          {compatibleModels.map((row: any) => <option key={row.model_id} value={row.model_id}>{row.display_name || row.model_id}</option>)}
        </select>
        <input className="v3-input" value={frequency} onChange={(e) => setFrequency(e.target.value)} placeholder="Frequency seconds" />
        <input className="v3-input" value={ttl} onChange={(e) => setTtl(e.target.value)} placeholder="Task TTL seconds" />
        <select className="v3-input" value={reviewMode} onChange={(e) => setReviewMode(e.target.value)}>
          <option value="OPTIONAL">Review optional</option>
          <option value="PREFERRED">Review preferred</option>
          <option value="REQUIRED">Review required for configured research/paper workflow</option>
        </select>
        <AsyncActionButton label="Save MarketWatchPolicy" onRun={savePolicy} />
      </div>

      <div className="v3-region v3-sp6">
        <strong>Provider Queue / Budget</strong>
        <p className="v3-region-note">Rate/concurrency pressure queues work; expired market tasks are discarded.</p>
        <input className="v3-input" value={queueConcurrency} onChange={(e) => setQueueConcurrency(e.target.value)} placeholder="Max concurrency" />
        <input className="v3-input" value={queueSize} onChange={(e) => setQueueSize(e.target.value)} placeholder="Max queue size" />
        <AsyncActionButton label="Save queue policy" onRun={saveQueue} />
        <div style={{ marginTop: 12 }}>
          <strong>Strategy Hunting</strong>
          <p className="v3-region-note">After-hours research only; OD-V2-16 licensing/provenance gate remains mandatory.</p>
          <AsyncActionButton label={huntingEnabled ? "Disable Strategy Hunting" : "Enable Strategy Hunting"} tone="warn" onRun={() => setHunting(!huntingEnabled)} />
        </div>
      </div>

      <div className="v3-region v3-sp6">
        <strong>User Intelligence Entitlements</strong>
        <p className="v3-region-note">Capability authorization is layered on S2 account/device/session identity.</p>
        <input className="v3-input" value={userId} onChange={(e) => setUserId(e.target.value)} placeholder="User UUID" />
        {CAPS.map((cap) => <label key={cap} style={{ display: "block", marginTop: 6 }}>
          <input
            type="checkbox"
            checked={selectedCaps.includes(cap)}
            onChange={(e) => setSelectedCaps((current) => e.target.checked ? [...current, cap] : current.filter((item) => item !== cap))}
          /> {cap}
        </label>)}
        <AsyncActionButton label="Save user capabilities" tone="warn" onRun={saveEntitlements} />
      </div>

      <div className="v3-region v3-sp6">
        <strong>Portfolio / Authority Status</strong>
        <div className="v3-region-note">Risk authority: {String(payload.risk_authority || "RiskGateV2")}</div>
        <div className="v3-region-note">Candidate portfolio: {String(payload.candidate_portfolio?.authority_state || "UNAVAILABLE")}</div>
        <div className="v3-region-note">Aggregate reserved: {String(payload.candidate_portfolio?.aggregate_reserved ?? "—")}</div>
        <div className="v3-region-note">Entitlement authority: {String(payload.entitlement_authority || "S2")}</div>
        <div className="v3-region-note">Live: {String(payload.live_state || "READ_ONLY/DISARMED")}</div>
      </div>

      <div className="v3-region v3-sp12">
        <strong>Scope Expansion Requests</strong>
        <p className="v3-region-note">AI may request scope; only Owner policy can approve it.</p>
        <SimpleTable rows={scopeRows} columns={[
          { key: "request_id", label: "Request" },
          { key: "requested_by", label: "Requested by" },
          { key: "expansion_type", label: "Type" },
          { key: "requested_value", label: "Value" },
          { key: "status", label: "Status" },
          { key: "actions", label: "Decision", render: (row) => row.status === "PENDING_OWNER_REVIEW" ? <div style={{ display: "flex", gap: 6 }}>
            <AsyncActionButton label="Approve" onRun={() => decideScope(row.request_id, "APPROVE")} />
            <AsyncActionButton label="Deny" tone="warn" onRun={() => decideScope(row.request_id, "DENY")} />
          </div> : "—" },
        ]} />
      </div>
    </div>
  </section>;
};
