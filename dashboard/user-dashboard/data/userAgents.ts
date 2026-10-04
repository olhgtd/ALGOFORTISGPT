/**
 * AlgoFortis User Dashboard — Agents V2 Dev Prototype Data
 */
export interface AgentItem {
  id: string;
  name: string;
  purpose: string;
  task: string;
  status: "ACTIVE" | "PAUSED" | "NEEDS_ATTENTION";
  result: string;
  health: "GOOD" | "WATCH" | "DEGRADED";
  model: string;
  history: { t: string; text: string }[];
}

export const AGENTS: AgentItem[] = [];
