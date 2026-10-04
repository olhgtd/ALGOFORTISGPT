/**
 * AlgoFortis Dashboard V3 — Datasets, Ingestion Readiness & Historical Data Domain
 */
import type { Truth } from "../../shared/data/sharedTypes";
import { STORAGE_KEYS, prototypeFixtureStorage, safeGetJson, safeSetJson } from "../../shared/data/storage";

const localStorage = prototypeFixtureStorage;

export type DatasetAcquisitionStatus = "ACQUIRED" | "DOWNLOADING" | "PARTIAL";
export type DatasetSystemReadiness = "SYSTEM_READY" | "BLOCKED";
export type DatasetOwnerApproval = "APPROVED" | "HOLD" | "REJECTED";
export type DatasetEffectiveReadiness = "READY_FOR_BACKTEST" | "BLOCKED";
export type DatasetGapStatus = "GAPS_CLEAR" | "GAPS_DETECTED";
export type DatasetProvenance = "KNOWN_HASH" | "UNVERIFIED_SOURCE";

export interface OwnerDatasetRow {
  id: string;
  datasetId: string;
  source: string;
  market: string;
  instrument: string;
  segment: string;
  timeframe: string;
  sourceTimezone: string;
  startDate: string;
  endDate: string;
  tradingDays: number;
  rowCount: number;
  format: "PARQUET_V2" | "CSV_NORMALIZED" | "CSV_RAW";
  logicalPath: string;
  gapStatus: DatasetGapStatus;
  gapDetails?: string;
  provenance: DatasetProvenance;
  hashSha256: string;
  acquisitionState: DatasetAcquisitionStatus;
  systemReadiness: DatasetSystemReadiness;
  systemBlockerReason?: string;
  verificationDetails: string;
  ownerApproval: DatasetOwnerApproval;
  ownerHoldReason?: string;
  effectiveBacktestReadiness: DatasetEffectiveReadiness;
  lastUpdated: string;
  history: { time: string; action: string; actor: string; note: string; tone?: "ok" | "warn" | "neg" | "dim" }[];
}

export function computeDatasetEffectiveReadiness(
  systemReadiness: DatasetSystemReadiness,
  ownerApproval: DatasetOwnerApproval,
  systemBlocker?: string
): { status: DatasetEffectiveReadiness; label: string; tone: "ok" | "warn" | "neg" | "dim"; blocker?: string } {
  if (systemReadiness !== "SYSTEM_READY") {
    return {
      status: "BLOCKED",
      label: "BLOCKED (SYSTEM DATA NOT READY)",
      tone: "neg",
      blocker: systemBlocker || "Dataset failed schema validation or trading calendar gap verification.",
    };
  }
  if (ownerApproval !== "APPROVED") {
    return {
      status: "BLOCKED",
      label: `BLOCKED (OWNER ${ownerApproval})`,
      tone: "warn",
      blocker: ownerApproval === "HOLD" ? "Owner placed dataset on administrative hold." : "Owner rejected dataset.",
    };
  }
  return {
    status: "READY_FOR_BACKTEST",
    label: "READY FOR BACKTEST",
    tone: "ok",
  };
}

export const INITIAL_OWNER_DATASETS: OwnerDatasetRow[] = [
  {
    id: "ds-01",
    datasetId: "DS-NIFTY-5M-2024-2026",
    source: "TrueData Historical API",
    market: "NSE_INDEX",
    instrument: "NIFTY",
    segment: "Index Spot",
    timeframe: "5m",
    sourceTimezone: "Asia/Kolkata",
    startDate: "2024-01-01",
    endDate: "2026-08-25",
    tradingDays: 652,
    rowCount: 48900,
    format: "PARQUET_V2",
    logicalPath: "data/parquet/nse/nifty/spot/5m/nifty_5m.parquet",
    gapStatus: "GAPS_CLEAR",
    gapDetails: "0 missing candles against NSE Calendar Authority (652 trading sessions verified)",
    provenance: "KNOWN_HASH",
    hashSha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    acquisitionState: "ACQUIRED",
    systemReadiness: "SYSTEM_READY",
    verificationDetails: "Parquet v2 format valid · SHA-256 sealed · 0 NSE Calendar gaps",
    ownerApproval: "APPROVED",
    effectiveBacktestReadiness: "READY_FOR_BACKTEST",
    lastUpdated: "2026-08-26 18:00 UTC",
    history: [
      { time: "2026-08-26 18:00 UTC", action: "OWNER_APPROVAL_GRANTED", actor: "OWNER-001", note: "Approved for Authoritative Backtest Replays", tone: "ok" },
      { time: "2026-08-26 17:30 UTC", action: "SYSTEM_GAP_SCAN_PASSED", actor: "SYSTEM_CALENDAR", note: "Verified against NSE Calendar (0 gaps across 652 sessions)", tone: "ok" },
      { time: "2026-08-26 17:00 UTC", action: "FORMAT_NORMALIZED", actor: "PARQUET_INGEST", note: "Converted to Parquet v2 (48,900 rows)", tone: "ok" },
    ],
  },
  {
    id: "ds-02",
    datasetId: "DS-BANKNIFTY-1M-2025-2026",
    source: "NSE Official Tick Master",
    market: "NSE_INDEX",
    instrument: "BANKNIFTY",
    segment: "Index Spot",
    timeframe: "1m",
    sourceTimezone: "Asia/Kolkata",
    startDate: "2025-01-01",
    endDate: "2026-08-28",
    tradingDays: 412,
    rowCount: 154500,
    format: "PARQUET_V2",
    logicalPath: "data/parquet/nse/banknifty/spot/1m/banknifty_1m.parquet",
    gapStatus: "GAPS_CLEAR",
    gapDetails: "0 missing candles (412 trading sessions verified)",
    provenance: "KNOWN_HASH",
    hashSha256: "7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
    acquisitionState: "ACQUIRED",
    systemReadiness: "SYSTEM_READY",
    verificationDetails: "Parquet v2 format valid · SHA-256 sealed · 0 NSE Calendar gaps",
    ownerApproval: "APPROVED",
    effectiveBacktestReadiness: "READY_FOR_BACKTEST",
    lastUpdated: "2026-08-29 09:15 UTC",
    history: [
      { time: "2026-08-29 09:15 UTC", action: "OWNER_APPROVAL_GRANTED", actor: "OWNER-001", note: "Approved for High-Density 1m Strategy Replay", tone: "ok" },
      { time: "2026-08-29 09:00 UTC", action: "SYSTEM_VERIFIED", actor: "SYSTEM_CALENDAR", note: "Verified against NSE Calendar (0 gaps across 412 sessions)", tone: "ok" },
    ],
  },
  {
    id: "ds-03",
    datasetId: "DS-NIFTY-OPT-WEEKLY-2026",
    source: "Historical CSV Ingestion (data/incoming/)",
    market: "NSE_FNO",
    instrument: "NIFTY",
    segment: "Options (Multi-Expiry CE/PE)",
    timeframe: "1m",
    sourceTimezone: "Asia/Kolkata",
    startDate: "2026-01-01",
    endDate: "2026-06-30",
    tradingDays: 124,
    rowCount: 892000,
    format: "CSV_NORMALIZED",
    logicalPath: "data/parquet/nse/nifty/options/2026/",
    gapStatus: "GAPS_DETECTED",
    gapDetails: "14 missing 1-minute bars on 2026-06-12 (Special Disaster Recovery Session)",
    provenance: "KNOWN_HASH",
    hashSha256: "9b71d224bd62f3785d96d46ad3ea3d73319bfbc2890caadae2dff72519673ca72",
    acquisitionState: "ACQUIRED",
    systemReadiness: "BLOCKED",
    systemBlockerReason: "14 missing bars detected on 2026-06-12 special session. Requires gap backfill.",
    verificationDetails: "Verification Incomplete: Calendar gap detected on 2026-06-12",
    ownerApproval: "HOLD",
    ownerHoldReason: "Awaiting gap backfill for 2026-06-12 special session before backtest sign-off",
    effectiveBacktestReadiness: "BLOCKED",
    lastUpdated: "2026-07-02 11:00 UTC",
    history: [
      { time: "2026-07-02 11:05 UTC", action: "GAP_SCAN_FLAGGED", actor: "SYSTEM_CALENDAR", note: "14 missing bars detected on 2026-06-12", tone: "warn" },
      { time: "2026-07-02 11:00 UTC", action: "ACQUISITION_INGESTED", actor: "AUTO_IMPORTER", note: "Ingested from data/incoming/nifty_opt_h1_2026.csv (892k rows)", tone: "ok" },
    ],
  },
  {
    id: "ds-04",
    datasetId: "DS-FINNIFTY-5M-2025-2026",
    source: "Angel One Historical API",
    market: "NSE_INDEX",
    instrument: "FINNIFTY",
    segment: "Index Spot",
    timeframe: "5m",
    sourceTimezone: "Asia/Kolkata",
    startDate: "2025-06-01",
    endDate: "2026-08-15",
    tradingDays: 298,
    rowCount: 22350,
    format: "PARQUET_V2",
    logicalPath: "data/parquet/nse/finnifty/spot/5m/finnifty_5m.parquet",
    gapStatus: "GAPS_CLEAR",
    gapDetails: "0 missing candles",
    provenance: "KNOWN_HASH",
    hashSha256: "1f82c6424b912f71887e45dd98d363720743b17926b0a1d47155694a11f2f012",
    acquisitionState: "ACQUIRED",
    systemReadiness: "SYSTEM_READY",
    verificationDetails: "Parquet v2 format valid · SHA-256 sealed · 0 NSE Calendar gaps",
    ownerApproval: "APPROVED",
    effectiveBacktestReadiness: "READY_FOR_BACKTEST",
    lastUpdated: "2026-08-16 14:00 UTC",
    history: [
      { time: "2026-08-16 14:00 UTC", action: "OWNER_APPROVAL_GRANTED", actor: "OWNER-001", note: "Approved for Backtest Replays", tone: "ok" },
      { time: "2026-08-16 13:30 UTC", action: "SYSTEM_VERIFIED", actor: "SYSTEM_CALENDAR", note: "0 gaps across 298 sessions", tone: "ok" },
    ],
  },
  {
    id: "ds-05",
    datasetId: "DS-SENSEX-TICK-RAW-2026",
    source: "Third-Party Raw Drop",
    market: "BSE_INDEX",
    instrument: "SENSEX",
    segment: "Index Spot",
    timeframe: "tick",
    sourceTimezone: "Asia/Kolkata",
    startDate: "2026-08-01",
    endDate: "2026-08-20",
    tradingDays: 14,
    rowCount: 1450000,
    format: "CSV_RAW",
    logicalPath: "data/incoming/sensex_aug2026_raw.csv",
    gapStatus: "GAPS_DETECTED",
    gapDetails: "Unverified timestamp formatting; missing volume field on 4 dates",
    provenance: "UNVERIFIED_SOURCE",
    hashSha256: "01ba4719c80b6fe911b091a7c05124b64eeece964e09c058ef8f9805daca546b",
    acquisitionState: "PARTIAL",
    systemReadiness: "BLOCKED",
    systemBlockerReason: "Failed Phase 1 Importer OHLCV schema validation. Non-standard timestamp format.",
    verificationDetails: "Verification FAILED: Schema invalid",
    ownerApproval: "REJECTED",
    ownerHoldReason: "Failed Phase 1 Importer OHLCV schema verification",
    effectiveBacktestReadiness: "BLOCKED",
    lastUpdated: "2026-08-21 16:30 UTC",
    history: [
      { time: "2026-08-21 16:30 UTC", action: "SCHEMA_REJECTED", actor: "AUTO_IMPORTER", note: "Quarantined: Non-standard column headers detected", tone: "neg" },
    ],
  },
];

const OWNER_DATASETS_KEY = STORAGE_KEYS.OWNER_DATASETS;

export function getStoredOwnerDatasets(): OwnerDatasetRow[] {
  try {
    const raw = localStorage.getItem(OWNER_DATASETS_KEY);
    if (!raw) {
      localStorage.setItem(OWNER_DATASETS_KEY, JSON.stringify(INITIAL_OWNER_DATASETS));
      return INITIAL_OWNER_DATASETS;
    }
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed) && parsed.length > 0) return parsed;
    return INITIAL_OWNER_DATASETS;
  } catch {
    return INITIAL_OWNER_DATASETS;
  }
}

export function saveOwnerDatasets(datasets: OwnerDatasetRow[]): void {
  try {
    localStorage.setItem(OWNER_DATASETS_KEY, JSON.stringify(datasets));
  } catch (err) {
    console.error("Failed to save datasets", err);
  }
}

export function updateDatasetApproval(
  datasetId: string,
  approval: DatasetOwnerApproval,
  reason?: string,
  actor: string = "OWNER-001"
): { success: boolean; effective: DatasetEffectiveReadiness; message: string } {
  const current = getStoredOwnerDatasets();
  const index = current.findIndex((d) => d.id === datasetId || d.datasetId === datasetId);
  if (index === -1) return { success: false, effective: "BLOCKED", message: "Dataset not found" };

  const ds = { ...current[index] };
  ds.ownerApproval = approval;
  if (approval === "HOLD") {
    ds.ownerHoldReason = reason || `Placed on hold by ${actor}`;
  } else {
    delete ds.ownerHoldReason;
  }

  const computed = computeDatasetEffectiveReadiness(ds.systemReadiness, ds.ownerApproval, ds.systemBlockerReason);
  ds.effectiveBacktestReadiness = computed.status;

  // Append new history entry without erasing existing evidence
  ds.history = [
    {
      time: new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC",
      action: `OWNER_APPROVAL_${approval}`,
      actor,
      note: `Owner set approval to ${approval} (Effective: ${computed.label})`,
      tone: computed.status === "READY_FOR_BACKTEST" ? "ok" : "warn",
    },
    ...ds.history,
  ];

  current[index] = ds;
  saveOwnerDatasets(current);

  let msg = `Dataset "${ds.datasetId}" Owner Approval set to ${approval}.`;
  if (approval === "APPROVED" && computed.status === "BLOCKED") {
    msg += ` Effective readiness remains BLOCKED (${computed.blocker}).`;
  }
  return { success: true, effective: computed.status, message: msg };
}

export function simulateDatasetVerification(datasetId: string, actor: string = "OWNER-001"): { success: boolean; message: string } {
  const current = getStoredOwnerDatasets();
  const index = current.findIndex((d) => d.id === datasetId || d.datasetId === datasetId);
  if (index === -1) return { success: false, message: "Dataset not found" };

  const ds = { ...current[index] };
  const scanTime = new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC";

  ds.history = [
    {
      time: scanTime,
      action: "PROTOTYPE_REVERIFY_REQUESTED",
      actor,
      note: `Simulated re-verification triggered (Current System Readiness: ${ds.systemReadiness})`,
      tone: ds.systemReadiness === "SYSTEM_READY" ? "ok" : "warn",
    },
    ...ds.history,
  ];

  current[index] = ds;
  saveOwnerDatasets(current);
  return {
    success: true,
    message: `Triggered simulated re-verification for "${ds.datasetId}". Evidence logged to history.`,
  };
}

export function simulateDatasetGapRepair(datasetId: string, actor: string = "OWNER-001"): { success: boolean; message: string } {
  const current = getStoredOwnerDatasets();
  const index = current.findIndex((d) => d.id === datasetId || d.datasetId === datasetId);
  if (index === -1) return { success: false, message: "Dataset not found" };

  const ds = { ...current[index] };
  const scanTime = new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC";

  ds.history = [
    {
      time: scanTime,
      action: "PROTOTYPE_GAP_REPAIR_SIMULATED",
      actor,
      note: `Simulated calendar gap backfill requested against NSE Calendar Authority`,
      tone: "ok",
    },
    ...ds.history,
  ];

  current[index] = ds;
  saveOwnerDatasets(current);
  return {
    success: true,
    message: `Initiated simulated gap repair for "${ds.datasetId}". Action appended to lifecycle history.`,
  };
}
