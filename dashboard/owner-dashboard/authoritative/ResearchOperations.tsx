import React, { useCallback, useMemo, useState } from "react";
import { Panel } from "../../shared/utilities/V3Chrome";
import { AsyncActionButton, SimpleTable } from "./components";
import { useAsyncResource } from "./hooks";
import {
  cancelOwnerBacktest,
  cancelOwnerWalkForwardJob,
  createOwnerWalkForwardJob,
  listOwnerBacktests,
  listOwnerWalkForwardJobs,
  runOwnerBacktest,
} from "./researchOps";

const rowsFrom = (payload: any, ...keys: string[]): any[] => {
  if (Array.isArray(payload)) return payload;
  for (const key of keys) if (Array.isArray(payload?.[key])) return payload[key];
  return [];
};

export const ResearchOperations: React.FC = () => {
  const load = useCallback(async () => {
    const [backtests, walkforward] = await Promise.all([
      listOwnerBacktests(),
      listOwnerWalkForwardJobs(),
    ]);
    return { backtests, walkforward };
  }, []);
  const { data, loading, error, refresh } = useAsyncResource(load);
  const [strategyId, setStrategyId] = useState("");
  const [datasetId, setDatasetId] = useState("nse-tick-primary");
  const [instrument, setInstrument] = useState("NIFTY");
  const [timeframe, setTimeframe] = useState("1m");
  const [initialCapital, setInitialCapital] = useState(500000);
  const [dateRange, setDateRange] = useState("2026-01-05");
  const [isDays, setIsDays] = useState(20);
  const [oosDays, setOosDays] = useState(5);
  const [maxWindows, setMaxWindows] = useState(12);

  const backtests = useMemo(() => rowsFrom(data?.backtests, "runs", "backtests"), [data]);
  const walkforward = useMemo(() => rowsFrom(data?.walkforward, "jobs", "walkforward"), [data]);
  const canRun = Boolean(strategyId.trim() && datasetId.trim());

  if (loading && !data) return <Panel>Loading research authority…</Panel>;

  return <>
    <div className="v3-screen-head">
      <div>
        <h2 className="v3-screen-title">Backtests / Walk-Forward</h2>
        <p className="v3-screen-sub">Owner research operations reuse canonical Backtest and WFO services. Live remains READ_ONLY / DISARMED.</p>
      </div>
    </div>

    {error && <div className="owner-authority-message unavailable" role="status"><strong>UNAVAILABLE</strong><div>{error}</div></div>}

    <Panel>
      <div className="v3-region-head"><span className="v3-region-title">Research Input</span></div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 8 }}>
        <input className="v3-input" value={strategyId} onChange={(e) => setStrategyId(e.target.value)} placeholder="Strategy ID" />
        <input className="v3-input" value={datasetId} onChange={(e) => setDatasetId(e.target.value)} placeholder="Dataset ID" />
        <input className="v3-input" value={instrument} onChange={(e) => setInstrument(e.target.value)} placeholder="Instrument" />
        <input className="v3-input" value={timeframe} onChange={(e) => setTimeframe(e.target.value)} placeholder="Timeframe" />
        <input className="v3-input" type="number" value={initialCapital} onChange={(e) => setInitialCapital(Number(e.target.value) || 0)} placeholder="Initial capital" />
        <input className="v3-input" value={dateRange} onChange={(e) => setDateRange(e.target.value)} placeholder="Backtest date range" />
        <input className="v3-input" type="number" value={isDays} onChange={(e) => setIsDays(Number(e.target.value) || 1)} placeholder="IS days" />
        <input className="v3-input" type="number" value={oosDays} onChange={(e) => setOosDays(Number(e.target.value) || 1)} placeholder="OOS days" />
        <input className="v3-input" type="number" value={maxWindows} onChange={(e) => setMaxWindows(Number(e.target.value) || 1)} placeholder="Max windows" />
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
        <AsyncActionButton
          label="Run Backtest"
          disabled={!canRun}
          onRun={() => runOwnerBacktest({
            strategy_id: strategyId.trim(), dataset_id: datasetId.trim(), instrument: instrument.trim(),
            timeframe: timeframe.trim(), initial_capital: initialCapital, date_range: dateRange.trim(),
          })}
          onDone={refresh}
        />
        <AsyncActionButton
          label="Run Walk-Forward"
          disabled={!canRun}
          onRun={() => createOwnerWalkForwardJob({
            strategy_id: strategyId.trim(), dataset_id: datasetId.trim(), instrument: instrument.trim(),
            timeframe: timeframe.trim(), initial_capital: initialCapital, is_days: isDays, oos_days: oosDays,
            max_windows: maxWindows,
          })}
          onDone={refresh}
        />
        <button type="button" className="v3-btn ghost mini" onClick={refresh}>Refresh</button>
      </div>
      <div className="v3-region-note" style={{ marginTop: 8 }}>Backend rejection is fail-closed and remains visible as Action rejected.</div>
    </Panel>

    <div className="v3-grid">
      <section className="v3-region v3-sp12">
        <div className="v3-region-head"><span className="v3-region-title">Backtest Runs</span></div>
        <SimpleTable rows={backtests} columns={[
          { key: "run_id", label: "Run" }, { key: "strategy_id", label: "Strategy" },
          { key: "status", label: "Status" }, { key: "instrument", label: "Instrument" },
          { key: "actions", label: "Admin", render: (row) => {
            const runId = String(row.run_id || row.id || "");
            return <AsyncActionButton label="Cancel" tone="warn" disabled={!runId || !["PENDING", "RUNNING"].includes(String(row.status || "").toUpperCase())} onRun={() => cancelOwnerBacktest(runId)} onDone={refresh} />;
          } },
        ]} />
      </section>

      <section className="v3-region v3-sp12">
        <div className="v3-region-head"><span className="v3-region-title">Walk-Forward / OOS Jobs</span></div>
        <SimpleTable rows={walkforward} columns={[
          { key: "job_id", label: "Job" }, { key: "strategy_id", label: "Strategy" },
          { key: "status", label: "Status" }, { key: "instrument", label: "Instrument" },
          { key: "actions", label: "Admin", render: (row) => {
            const jobId = String(row.job_id || row.id || "");
            return <AsyncActionButton label="Cancel" tone="warn" disabled={!jobId || !["PENDING", "RUNNING"].includes(String(row.status || "").toUpperCase())} onRun={() => cancelOwnerWalkForwardJob(jobId)} onDone={refresh} />;
          } },
        ]} />
      </section>
    </div>
  </>;
};
