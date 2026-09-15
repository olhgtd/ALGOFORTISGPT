import { useState } from "react";
import { Icon } from "../../shared/icons/V3Icons";
import { Panel, Drawer, KV, TruthChip, Dot } from "../../shared/utilities/V3Chrome";
import { AGENTS, type AgentItem } from "../../sampleData";

/* AGENT WORKSPACE — full agent surface opened from the Home summary.
   Visual prototype: safety-critical agents are PROTECTED / SYSTEM / VIEW ONLY.
   Non-safety analytical agents allow local sample state Pause/Resume. */

const HEALTH_TONE = { GOOD: "ok", WATCH: "warn", DEGRADED: "neg" } as const;
const STATUS_LABEL: Record<AgentItem["status"], string> = { ACTIVE: "Active", PAUSED: "Paused", NEEDS_ATTENTION: "Needs Attention" };

// Safety-critical system agents that cannot be paused/stopped by normal users
const PROTECTED_AGENT_IDS = new Set(["warden", "ledger", "sentry"]);

export const AgentsScreen: React.FC<{ ownerView?: boolean }> = ({ ownerView }) => {
  const [agents, setAgents] = useState<AgentItem[]>(() => AGENTS.map((a) => ({ ...a })));
  const [openId, setOpenId] = useState<string | null>(null);
  const active = agents.filter((a) => a.status === "ACTIVE").length;
  const attention = agents.filter((a) => a.status === "NEEDS_ATTENTION").length;
  const selected = agents.find((a) => a.id === openId) ?? null;

  const toggle = (id: string) => {
    if (PROTECTED_AGENT_IDS.has(id)) return; // Safety guard
    setAgents((as) => as.map((a) => {
      if (a.id !== id) return a;
      if (a.status === "ACTIVE") return { ...a, status: "PAUSED", task: "Paused by operator (sample)" };
      if (a.status === "PAUSED") return { ...a, status: "ACTIVE", task: "Resumed — picking up last task (sample)" };
      return a;
    }));
  };

  return (
    <>
      <div className="v3-screen-head">
        <div>
          <h2 className="v3-screen-title">{ownerView ? "Agent Control Center" : "Agent Workspace"}</h2>
          <p className="v3-screen-sub">{active} active · {attention} needs attention · safety-critical agents protected</p>
        </div>
        <TruthChip kind="SAMPLE" title="No authoritative agent execution backend is connected in this phase." />
      </div>

      <div className="v3-grid">
        {agents.length === 0 ? (
          <div className="v3-sp12" style={{ padding: "48px 24px", textAlign: "center", color: "var(--v3-text-dim)" }}>
            No agents registered yet
          </div>
        ) : (
          agents.map((a) => {
            const isProtected = PROTECTED_AGENT_IDS.has(a.id);
            return (
            <div className="v3-agent v3-sp6" key={a.id} style={a.status === "NEEDS_ATTENTION" ? { borderColor: "var(--v3-line-strong)" } : undefined}>
              <div className="v3-agent-top">
                <div style={{ minWidth: 0 }}>
                  <div className="v3-agent-name" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    {a.name}
                    {isProtected && (
                      <span title="Safety-critical system agent">
                        <Icon name="shield" size={13} style={{ color: "var(--v3-warn-text)" }} />
                      </span>
                    )}
                  </div>
                  <div className="v3-agent-purpose">{a.purpose}</div>
                </div>
                {isProtected ? (
                  <span
                    className="v3-chip disabled"
                    style={{
                      borderColor: "var(--v3-warn)",
                      color: "var(--v3-warn-text)",
                      background: "var(--v3-warn-bg)",
                      fontSize: 9.5,
                      fontWeight: 700,
                      letterSpacing: "0.04em",
                    }}
                    title="Safety-critical system agent — PROTECTED / SYSTEM / VIEW ONLY"
                  >
                    PROTECTED · SYSTEM · VIEW ONLY
                  </span>
                ) : (
                  <span className="v3-chip sample">{STATUS_LABEL[a.status]}</span>
                )}
              </div>

              <div className="v3-agent-task">
                <span className="t-label">CURRENT TASK</span>
                <div className="t-text">{a.task}</div>
              </div>

              <div className="v3-row-sub" style={{ margin: 0 }}>
                <span className="v3-ink3">Recent result: </span>
                <span className="v3-ink2">{a.result}</span>
              </div>

              <div className="v3-agent-foot">
                <span className="v3-health">
                  <Dot tone={HEALTH_TONE[a.health]} /> HEALTH {a.health} · {a.model}
                </span>
                <span style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  {isProtected ? (
                    <span
                      className="v3-mono v3-dim"
                      style={{ fontSize: 10.5, display: "flex", alignItems: "center", gap: 4, padding: "3px 6px" }}
                      title="Pause/Stop controls are not exposed for safety-critical system agents"
                    >
                      <Icon name="lock" size={11} /> View Only
                    </span>
                  ) : (
                    (a.status === "ACTIVE" || a.status === "PAUSED") && (
                      <button
                        className="v3-btn ghost mini"
                        onClick={() => toggle(a.id)}
                        title="Toggles local sample state only — analytical agent."
                      >
                        <Icon name={a.status === "ACTIVE" ? "pause" : "play"} size={13} /> {a.status === "ACTIVE" ? "Pause" : "Resume"}
                      </button>
                    )
                  )}
                  <button className="v3-btn ghost mini" onClick={() => setOpenId(a.id)}>
                    <Icon name="activity" size={13} /> History / Detail
                  </button>
                </span>
              </div>
            </div>
          );
          })
        )}

        <div className="v3-concept v3-sp12">
          <Icon name="cpu" size={22} />
          <h3>Agent registry &amp; provider bindings</h3>
          <p>Agent creation, model/provider binding and scheduling join a later phase. Safety-critical agents (Risk Warden, Compliance Ledger, Execution Sentry) remain protected with view-only governance.</p>
          <span className="v3-chip disabled" title="Agent registry backend is not part of the first visual-lab scope.">REGISTRY · DISABLED / UNAVAILABLE</span>
        </div>
      </div>

      <Drawer
        open={selected !== null}
        title={selected?.name ?? ""}
        sub={selected ? `${selected.purpose} · ${selected.model}` : undefined}
        onClose={() => setOpenId(null)}
      >
        {selected && (
          <>
            <dl style={{ margin: "0 0 20px" }}>
              <KV
                k="Governance Tier"
                v={PROTECTED_AGENT_IDS.has(selected.id) ? "PROTECTED / SYSTEM / VIEW ONLY" : "Analytical / User Agent (Sample Control)"}
                vClass={PROTECTED_AGENT_IDS.has(selected.id) ? "v3-warn-text" : undefined}
              />
              <KV k="Status" v={STATUS_LABEL[selected.status]} />
              <KV k="Health" v={selected.health} />
              <KV k="Current task" v={selected.task} />
              <KV k="Recent result" v={selected.result} />
              <KV k="Model / provider" v={selected.model} />
              <KV
                k="Operator Control"
                v={
                  PROTECTED_AGENT_IDS.has(selected.id)
                    ? "Locked — Safety-critical system agent cannot be paused or stopped by normal operator"
                    : "Interactive Sample Toggle"
                }
              />
            </dl>
            <Panel label="History / Log" meta="SAMPLE" truth="SAMPLE">
              <div className="v3-rows">
                {selected.history.map((h, i) => (
                  <div className="v3-row" key={i}>
                    <div className="v3-row-main">
                      <div className="v3-row-sub" style={{ marginTop: 0, color: "var(--v3-ink-2)" }}>{h.text}</div>
                    </div>
                    <span className="v3-mono v3-dim" style={{ fontSize: 10.5, flexShrink: 0 }}>{h.t}</span>
                  </div>
                ))}
              </div>
            </Panel>
          </>
        )}
      </Drawer>
    </>
  );
};
