/**
 * AlgoFortis User Dashboard — Option Chains & Strike Selection Policy
 */
import { type Truth, type OptionMoneyness, type GreeksAuthority, UNDERLYINGS } from "../../shared/data/sharedTypes";

export type MoneynessMode = "ATM" | "OTM" | "ITM";
export type StrikeDistance = 0 | 1 | 2 | 3 | 4;

export interface GlobalStrikePolicy {
  mode: MoneynessMode;
  distance: StrikeDistance;
}

export const DEFAULT_GLOBAL_STRIKE_POLICY: GlobalStrikePolicy = {
  mode: "OTM",
  distance: 1,
};

/**
 * Resolves ATM Strike from spot price, contract strike interval, and nearest-strike rounding rule.
 * E.g., NIFTY Spot 22,514.80 with 50pt interval resolves to 22,500 ATM strike.
 */
export function resolveAtmStrike(spot: number, step: number): number {
  return Math.round(spot / step) * step;
}

export interface ResolvedPolicyStrikes {
  atmStrike: number;
  ceStrike: number;
  peStrike: number;
  ceMoneyness: OptionMoneyness;
  peMoneyness: OptionMoneyness;
  policyDescription: string;
}

/**
 * Resolves Call (CE) and Put (PE) strike prices based on the unified Global Option Strike Policy.
 * 
 * Rules:
 * - ATM: Distance = 0 -> CE = ATM, PE = ATM
 * - OTM: CE = ATM + (Distance * Step), PE = ATM - (Distance * Step)
 * - ITM: CE = ATM - (Distance * Step), PE = ATM + (Distance * Step)
 */
export function resolveStrikesFromPolicy(
  spot: number,
  step: number,
  policy: GlobalStrikePolicy
): ResolvedPolicyStrikes {
  const atmStrike = resolveAtmStrike(spot, step);
  const effectiveDistance = policy.mode === "ATM" ? 0 : policy.distance;

  let ceStrike = atmStrike;
  let peStrike = atmStrike;
  let ceMoneyness: OptionMoneyness = "ATM";
  let peMoneyness: OptionMoneyness = "ATM";

  if (policy.mode === "ATM" || effectiveDistance === 0) {
    ceStrike = atmStrike;
    peStrike = atmStrike;
    ceMoneyness = "ATM";
    peMoneyness = "ATM";
  } else if (policy.mode === "OTM") {
    ceStrike = atmStrike + effectiveDistance * step;
    ceMoneyness = "OTM";
    peStrike = atmStrike - effectiveDistance * step;
    peMoneyness = "OTM";
  } else if (policy.mode === "ITM") {
    ceStrike = atmStrike - effectiveDistance * step;
    ceMoneyness = "ITM";
    peStrike = atmStrike + effectiveDistance * step;
    peMoneyness = "ITM";
  }

  const distText = policy.mode === "ATM" ? "ATM (0 strikes)" : `${policy.mode} (${policy.distance} strike${policy.distance === 1 ? "" : "s"})`;

  return {
    atmStrike,
    ceStrike,
    peStrike,
    ceMoneyness,
    peMoneyness,
    policyDescription: distText,
  };
}

export interface OptionLegData {
  ltp: number;
  change: number;
  changePct: number;
  bid: number;
  ask: number;
  volume: string;
  oi: string;
  oiChange: string;
  iv: string;
  delta: number;
  theta: number;
  gamma: number;
  vega: number;
  moneyness: OptionMoneyness;
  greeksAuthority: GreeksAuthority;
}

export interface StrikeRow {
  strike: number;
  call: OptionLegData;
  put: OptionLegData;
  isAtm: boolean;
}

export interface SelectedOptionContract {
  underlying: string;
  expiry: string;
  strike: number;
  optionType: "CE" | "PE";
  moneyness: OptionMoneyness;
  ltp: number;
  change: number;
  changePct: number;
  bid: number;
  ask: number;
  volume: string;
  oi: string;
  oiChange: string;
  iv: string;
  delta: number;
  theta: number;
  gamma: number;
  vega: number;
  lotSize: number;
  greeksAuthority: GreeksAuthority;
}

export function generateOptionChain(symbol: string, expiry: string): StrikeRow[] {
  const cfg = UNDERLYINGS[symbol] || UNDERLYINGS.NIFTY;
  const spot = cfg.spot;
  const step = cfg.step;
  const resolvedAtm = resolveAtmStrike(spot, step);
  const numStrikesEachSide = 8;
  const rows: StrikeRow[] = [];

  for (let i = -numStrikesEachSide; i <= numStrikesEachSide; i++) {
    const strike = resolvedAtm + i * step;
    const isAtm = strike === resolvedAtm;

    // CALL Moneyness: Strike == ATM -> ATM, Strike < Spot -> ITM, Strike > Spot -> OTM
    const callMoneyness: OptionMoneyness = isAtm ? "ATM" : strike < spot ? "ITM" : "OTM";
    // PUT Moneyness:  Strike == ATM -> ATM, Strike > Spot -> ITM, Strike < Spot -> OTM
    const putMoneyness: OptionMoneyness = isAtm ? "ATM" : strike > spot ? "ITM" : "OTM";

    // Call Pricing simulation
    const callIntrinsic = Math.max(0, spot - strike);
    const callTimeVal = Math.max(8, 140 - Math.abs(strike - resolvedAtm) * 0.12);
    const callLtp = Number((callIntrinsic + callTimeVal).toFixed(2));
    const callChg = Number((callLtp * 0.08 - (strike > spot ? 6 : 2)).toFixed(2));
    const callChgPct = Number(((callChg / (callLtp - callChg || 1)) * 100).toFixed(2));

    // Put Pricing simulation
    const putIntrinsic = Math.max(0, strike - spot);
    const putTimeVal = Math.max(8, 135 - Math.abs(strike - resolvedAtm) * 0.12);
    const putLtp = Number((putIntrinsic + putTimeVal).toFixed(2));
    const putChg = Number((-putLtp * 0.06 + (strike < spot ? 4 : -2)).toFixed(2));
    const putChgPct = Number(((putChg / (putLtp - putChg || 1)) * 100).toFixed(2));

    // Estimated Greeks (Clearly labeled DEV_SAMPLE_ESTIMATED — non-authoritative simulation)
    const distNorm = (strike - spot) / 500;
    const callDelta = Number((1 / (1 + Math.exp(distNorm))).toFixed(2));
    const putDelta = Number((callDelta - 1).toFixed(2));
    const iv = (13.5 + Math.abs(i) * 0.35).toFixed(1) + "%";

    rows.push({
      strike,
      isAtm,
      call: {
        ltp: callLtp,
        change: callChg,
        changePct: callChgPct,
        bid: Number((callLtp - 0.5).toFixed(2)),
        ask: Number((callLtp + 0.5).toFixed(2)),
        volume: `${(1.2 + Math.max(0, 10 - Math.abs(i)) * 0.8).toFixed(1)}L`,
        oi: `${(15.4 + Math.max(0, 10 - Math.abs(i)) * 2.4).toFixed(1)}L`,
        oiChange: `+${(0.8 + Math.abs(i) * 0.2).toFixed(1)}L`,
        iv,
        delta: callDelta,
        theta: Number((-12.4 + Math.abs(i) * 0.4).toFixed(1)),
        gamma: 0.0018,
        vega: 14.2,
        moneyness: callMoneyness,
        greeksAuthority: "DEV_SAMPLE_ESTIMATED",
      },
      put: {
        ltp: putLtp,
        change: putChg,
        changePct: putChgPct,
        bid: Number((putLtp - 0.5).toFixed(2)),
        ask: Number((putLtp + 0.5).toFixed(2)),
        volume: `${(1.1 + Math.max(0, 10 - Math.abs(i)) * 0.7).toFixed(1)}L`,
        oi: `${(18.2 + Math.max(0, 10 - Math.abs(i)) * 2.1).toFixed(1)}L`,
        oiChange: `-${(0.4 + Math.abs(i) * 0.1).toFixed(1)}L`,
        iv,
        delta: putDelta,
        theta: Number((-11.8 + Math.abs(i) * 0.4).toFixed(1)),
        gamma: 0.0018,
        vega: 14.0,
        moneyness: putMoneyness,
        greeksAuthority: "DEV_SAMPLE_ESTIMATED",
      },
    });
  }

  return rows;
}

export const DEFAULT_SELECTED_CONTRACT: SelectedOptionContract = {
  underlying: "NIFTY",
  expiry: "03 SEP 2026",
  strike: 22500,
  optionType: "CE",
  moneyness: "ATM",
  ltp: 142.50,
  change: 14.80,
  changePct: 11.59,
  bid: 142.00,
  ask: 143.00,
  volume: "9.2L",
  oi: "39.4L",
  oiChange: "+2.8L",
  iv: "13.8%",
  delta: 0.52,
  theta: -12.4,
  gamma: 0.0018,
  vega: 14.2,
  lotSize: 50,
  greeksAuthority: "DEV_SAMPLE_ESTIMATED",
};
