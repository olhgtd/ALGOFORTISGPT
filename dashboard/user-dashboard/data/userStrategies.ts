/**
 * SentinelX User Dashboard — User Strategies & Templates
 */

export interface StrategyTemplate {
  id: string;
  name: string;
  family: string;
  category?: string;
  summary: string;
  description: string;
  underlying: string;
  recommendedTimeframe: string;
  expectedSharpe: number;
  maxDrawdownPct: number;
  complexity: "Beginner" | "Intermediate" | "Advanced";
}

export const STRATEGY_TEMPLATES: StrategyTemplate[] = [
  {
    id: "tpl-01",
    name: "Systematic Intraday Straddle",
    family: "Volatility Arbitrage",
    summary: "Sells ATM CE + PE at market open and dynamically adjusts stop-loss based on underlying movement.",
    description: "Captures intraday volatility decay with rigid risk thresholds and automated strike adjustments.",
    underlying: "NIFTY / BANKNIFTY",
    recommendedTimeframe: "1-min bars",
    expectedSharpe: 2.14,
    maxDrawdownPct: 4.8,
    complexity: "Intermediate",
  },
  {
    id: "tpl-02",
    name: "Multi-Leg Iron Condor",
    family: "Non-Directional Range",
    summary: "Defines range-bound bounds with long wing hedges for strictly bounded tail risk.",
    description: "Structured options income model with pre-defined max loss envelope and zero margin spike risk.",
    underlying: "NIFTY",
    recommendedTimeframe: "5-min bars",
    expectedSharpe: 1.88,
    maxDrawdownPct: 3.2,
    complexity: "Beginner",
  },
  {
    id: "tpl-03",
    name: "Momentum Gamma Scalper",
    family: "Directional Breakout",
    summary: "Rapid order-book and velocity signal detection for high-delta intraday expansions.",
    description: "Exploits short-duration momentum surges with tick-level stop-loss migration.",
    underlying: "BANKNIFTY",
    recommendedTimeframe: "Tick / 1-sec",
    expectedSharpe: 2.45,
    maxDrawdownPct: 6.5,
    complexity: "Advanced",
  },
];

export const ALERTS: Array<{ level: "ATTENTION" | "INFO"; text: string; time: string }> = [];
