export type AnimationStage =
  | "dark_init"     // 0.0 - 0.5s: Dark environment reveals, grid matrix appears
  | "logo_entry"    // 0.4 - 1.2s: SentinelX mark & vertex monogram animate in
  | "headline_rise" // 0.8 - 2.0s: Product identity and headline rise from below
  | "fragments_fly" // 1.5 - 3.2s: Terminal fragments, charts, risk matrix assemble
  | "settling"      // 3.0 - 4.3s: Depth/parallax resolves, borders solidify
  | "settled";      // 4.0 - 5.0s+: Full interaction unlocked, intro completed

export interface MetricCardData {
  title: string;
  value: string;
  sub: string;
  trend: "up" | "down" | "neutral";
  change: string;
  badge: "FRESH" | "STALE" | "SAMPLE";
}

export interface StrategyLifecycleStage {
  id: string;
  name: string;
  order: number;
  status: "LOCKED" | "VERIFIED" | "ACTIVE" | "PENDING";
  description: string;
  gateCriteria: string[];
  color: string;
}

export interface SecurityPillar {
  title: string;
  tag: string;
  icon: string;
  description: string;
  technicalSpecs: string[];
}
