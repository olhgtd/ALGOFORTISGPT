import React, { useEffect, useMemo, useState } from "react";
import {
  cancelBacktestRun,
  cancelWalkForwardJob,
  createWalkForwardJob,
  executeBacktest,
} from "../../shared/services/integrationClient";
import { loadTestingSurface, type TestingSurfaceData, type UserSurfaceAuthorityState } from "../data/userSurfaceData";
import {
  AuthorityMessage,
  MetricCell,
  SurfacePanel,
  UserSurfaceHeader,
  displayMoney,
  displayNumber,
  displayScalar,
} from "../components/UserSurfacePrimitives";

export interface UserTestingProps {
  loadData?: () => Promise<TestingSurfaceData>;
  executeBacktestAction?: typeof executeBacktest;
  cancelBacktestAction?: typeof cancelBacktestRun;
  createWalkForwardAction?: typeof createWalkForwardJob;
  cancelWalkForwardAction?: typeof cancelWalkForwardJob;
}

const countValue = <T,>(block: { state: UserSurfaceAuthorityState; data: T[] } | undefined) =>
  block?.state === "AVAILABLE" ? block.data.length : "—";

const cancellable = (status: unknown) => ["PENDING", "RUNNING", "QUEUED"].includes(String(status || "").toUpperCase());

const fieldStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))",
  gap: 8,
};

export const UserTesting: React.FC<UserTestingProps> = ({
  loadData = loadTestingSurface,
  executeBacktestAction = executeBacktest,
  cancelBacktestAction = cancelBacktestRun,
  createWalkForwardAction = createWalkForwardJob,
  cancelWalkForwardAction = cancelWalkForwardJob,
}) => {
  const [data, setData] = useState<TestingSurfaceData | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const [backtestStrategy, setBacktestStrategy] = useState("");
  const [backtestDataset, setBacktestDataset] = useState("");
  const [backtestInstrument, setBacktestInstrument] = useState("NIFTY");
  const [backtestTimeframe, setBacktestTimeframe] = useState("5m");
  const [backtestCapital, setBacktestCapital] = useState(500000);
  const [backtestDateRange, setBacktestDateRange] = useState("2026-01-05");

  const [wfStrategy, setWfStrategy] = useState("");
  const [wfDataset, setWfDataset] = useState("");
  const [wfInstrument, setWfInstrument] = useState("NIFTY");
  const [wfTimeframe, setWfTimeframe] = useState("5m");
  const [wfIsDays, setWfIsDays] = useState(20);
  const [wfOosDays, setWfOosDays] = useState(5);
  const [wfMaxWindows, setWfMaxWindows] = useState(12);
  const [wfCapital, setWfCapital] = useState(500000);

  useEffect(() => {
    let active = true;
    setData(null);
    loadData().then((next) => { if (active) setData(next); }).catch(() => {
      if (active) setData({
        backtests: { state: "UNAVAILABLE", data: [], asOf: null },
        walkForward: { state: "UNAVAILABLE", data: [], asOf: null },
        reports: { state: "UNAVAILABLE", data: [], asOf: null },
      });
    });
    return () => { active = false; };
  }, [loadData]);

  const refreshAfterMutation = async (successMessage: string) => {
    setActionMessage(successMessage);
    try {
      const next = await loadData();
      setData(next);
    } catch {
      setActionMessage(`${successMessage} Refresh unavailable; previous evidence retained.`);
    }
  };

  const recentBacktests = useMemo(() => data?.backtests.state === "AVAILABLE" ? data.backtests.data.slice(0, 12) : [], [data]);
  const recentWalkForward = useMemo(() => data?.walkForward.state === "AVAILABLE" ? data.walkForward.data.slice(0, 10) : [], [data]);
  const reports = useMemo(() => data?.reports.state === "AVAILABLE" ? data.reports.data.slice(0, 12) : [], [data]);
  const backtestAvailable = data?.backtests.state === "AVAILABLE";
  const wfAvailable = data?.walkForward.state === "AVAILABLE";

  const runBacktest = async () => {
    if (!backtestAvailable || pendingAction || !backtestStrategy.trim() || !backtestDataset.trim()) return;
    setPendingAction("backtest-create");
    setActionMessage(null);
    try {
      const result = await executeBacktestAction({
        strategy_id: backtestStrategy.trim(),
        dataset_id: backtestDataset.trim(),
        instrument: backtestInstrument.trim(),
        timeframe: backtestTimeframe.trim(),
        initial_capital: backtestCapital,
        date_range: backtestDateRange.trim(),
      });
      if (!result.ok) {
        setActionMessage(result.error || "Backtest rejected by backend authority.");
        return;
      }
      await refreshAfterMutation(`Backtest accepted${result.data?.run_id ? ` · ${result.data.run_id}` : ""}.`);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "Backtest request failed.");
    } finally {
      setPendingAction(null);
    }
  };

  const cancelBacktest = async (runId: string) => {
    if (pendingAction) return;
    setPendingAction(`backtest-cancel:${runId}`);
    setActionMessage(null);
    try {
      const result = await cancelBacktestAction(runId);
      if (!result.ok) {
        setActionMessage(result.error || "Backtest cancellation rejected.");
        return;
      }
      await refreshAfterMutation(`Backtest cancellation requested · ${runId}.`);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "Backtest cancellation failed.");
    } finally {
      setPendingAction(null);
    }
  };

  const runWalkForward = async () => {
    if (!wfAvailable || pendingAction || !wfStrategy.trim() || !wfDataset.trim()) return;
    setPendingAction("wf-create");
    setActionMessage(null);
    try {
      const result = await createWalkForwardAction({
        strategy_id: wfStrategy.trim(),
        dataset_id: wfDataset.trim(),
        instrument: wfInstrument.trim(),
        timeframe: wfTimeframe.trim(),
        is_days: wfIsDays,
        oos_days: wfOosDays,
        max_windows: wfMaxWindows,
        initial_capital: wfCapital,
      });
      if (!result.success) {
        setActionMessage(result.error || "Walk-forward job rejected by backend authority.");
        return;
      }
      const jobId = result.data?.job_id;
      await refreshAfterMutation(`Walk-forward accepted${jobId ? ` · ${jobId}` : ""}.`);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "Walk-forward request failed.");
    } finally {
      setPendingAction(null);
    }
  };

  const cancelWalkForward = async (jobId: string) => {
    if (pendingAction) return;
    setPendingAction(`wf-cancel:${jobId}`);
    setActionMessage(null);
    try {
      const result = await cancelWalkForwardAction(jobId);
      if (!result.success) {
        setActionMessage(result.error || "Walk-forward cancellation rejected.");
        return;
      }
      await refreshAfterMutation(`Walk-forward cancellation requested · ${jobId}.`);
    } catch (error) {
      setActionMessage(error instanceof Error ? error.message : "Walk-forward cancellation failed.");
    } finally {
      setPendingAction(null);
    }
  };

  return (
    <div className="af-user-surface" data-testid="testing-surface">
      <UserSurfaceHeader
        eyebrow="Research Qualification"
        title="Testing & Validation"
        description="Backend-authoritative backtests, walk-forward/OOS jobs, and validation reports. Missing or stale evidence is never promoted to fresh qualification."
        aside={<div className="af-surface-lock"><span>Promotion</span><strong>FAIL CLOSED</strong></div>}
      />

      <section className="af-surface-metrics-grid">
        <MetricCell label="Backtest runs" value={countValue(data?.backtests)} />
        <MetricCell label="Walk-forward jobs" value={countValue(data?.walkForward)} />
        <MetricCell label="Reports" value={countValue(data?.reports)} />
        <MetricCell label="Validation verdict" value="Authority-driven" />
      </section>

      {actionMessage && <div className="af-surface-inline-note" role="status">{actionMessage}</div>}

      <div className="af-surface-two-col">
        <SurfacePanel eyebrow="Backtest" title="Run Backtest" authority={data?.backtests.state ?? "LOADING"}>
          <div style={fieldStyle}>
            <input className="v3-input" aria-label="Backtest strategy ID" value={backtestStrategy} onChange={(event) => setBacktestStrategy(event.target.value)} placeholder="Strategy ID" />
            <input className="v3-input" aria-label="Backtest dataset ID" value={backtestDataset} onChange={(event) => setBacktestDataset(event.target.value)} placeholder="Dataset ID" />
            <input className="v3-input" aria-label="Backtest instrument" value={backtestInstrument} onChange={(event) => setBacktestInstrument(event.target.value)} placeholder="Instrument" />
            <input className="v3-input" aria-label="Backtest timeframe" value={backtestTimeframe} onChange={(event) => setBacktestTimeframe(event.target.value)} placeholder="Timeframe" />
            <input className="v3-input" aria-label="Backtest initial capital" type="number" value={backtestCapital} onChange={(event) => setBacktestCapital(Number(event.target.value) || 0)} />
            <input className="v3-input" aria-label="Backtest date range" value={backtestDateRange} onChange={(event) => setBacktestDateRange(event.target.value)} placeholder="YYYY-MM-DD or backend range" />
          </div>
          <button
            type="button"
            className="v3-button"
            style={{ marginTop: 10 }}
            disabled={!backtestAvailable || Boolean(pendingAction) || !backtestStrategy.trim() || !backtestDataset.trim() || backtestCapital <= 0}
            onClick={() => { void runBacktest(); }}
          >{pendingAction === "backtest-create" ? "Running…" : "Run Backtest"}</button>
          {!backtestAvailable && <p className="af-surface-inline-note">Backtest mutation is disabled until authority is AVAILABLE.</p>}
        </SurfacePanel>

        <SurfacePanel eyebrow="Walk-Forward / OOS" title="Run Walk-Forward" authority={data?.walkForward.state ?? "LOADING"}>
          <div style={fieldStyle}>
            <input className="v3-input" aria-label="Walk-forward strategy ID" value={wfStrategy} onChange={(event) => setWfStrategy(event.target.value)} placeholder="Strategy ID" />
            <input className="v3-input" aria-label="Walk-forward dataset ID" value={wfDataset} onChange={(event) => setWfDataset(event.target.value)} placeholder="Dataset ID" />
            <input className="v3-input" aria-label="Walk-forward instrument" value={wfInstrument} onChange={(event) => setWfInstrument(event.target.value)} placeholder="Instrument" />
            <input className="v3-input" aria-label="Walk-forward timeframe" value={wfTimeframe} onChange={(event) => setWfTimeframe(event.target.value)} placeholder="Timeframe" />
            <input className="v3-input" aria-label="Walk-forward IS days" type="number" value={wfIsDays} onChange={(event) => setWfIsDays(Number(event.target.value) || 1)} />
            <input className="v3-input" aria-label="Walk-forward OOS days" type="number" value={wfOosDays} onChange={(event) => setWfOosDays(Number(event.target.value) || 1)} />
            <input className="v3-input" aria-label="Walk-forward max windows" type="number" value={wfMaxWindows} onChange={(event) => setWfMaxWindows(Number(event.target.value) || 1)} />
            <input className="v3-input" aria-label="Walk-forward initial capital" type="number" value={wfCapital} onChange={(event) => setWfCapital(Number(event.target.value) || 0)} />
          </div>
          <button
            type="button"
            className="v3-button"
            style={{ marginTop: 10 }}
            disabled={!wfAvailable || Boolean(pendingAction) || !wfStrategy.trim() || !wfDataset.trim() || wfCapital <= 0}
            onClick={() => { void runWalkForward(); }}
          >{pendingAction === "wf-create" ? "Running…" : "Run Walk-Forward"}</button>
          {!wfAvailable && <p className="af-surface-inline-note">Walk-forward mutation is disabled until authority is AVAILABLE.</p>}
        </SurfacePanel>
      </div>

      <div className="af-surface-two-col">
        <SurfacePanel eyebrow="Backtest" title="Authoritative Runs" authority={data?.backtests.state ?? "LOADING"}>
          {!data ? (
            <AuthorityMessage state="LOADING" title="Backtest runs" unavailable="" />
          ) : data.backtests.state !== "AVAILABLE" ? (
            <AuthorityMessage
              state={data.backtests.state}
              title="Backtest runs"
              unavailable="Backtest authority is unavailable. No sample run or numeric result is shown."
              stale="Backtest evidence is stale. Stale run rows and metrics are withheld until fresh backend evidence is available."
              unknown="Backtest authority trust is unknown. No run, metric, or validation outcome is inferred."
            />
          ) : recentBacktests.length === 0 ? (
            <AuthorityMessage state="AVAILABLE" isEmpty title="Backtest runs" unavailable="" empty="No authoritative backtest runs are recorded." />
          ) : (
            <div className="af-surface-table-wrap">
              <table className="af-surface-table">
                <thead><tr><th>Strategy</th><th>Instrument</th><th>Status</th><th>Trades</th><th>Net P&L</th><th>Max DD</th><th>Control</th></tr></thead>
                <tbody>
                  {recentBacktests.map((run) => (
                    <tr key={run.run_id}>
                      <td><strong>{displayScalar(run.strategy_name || run.strategy_id)}</strong><small>{displayScalar(run.version)} · {run.run_id}</small></td>
                      <td>{displayScalar(run.instrument)} · {displayScalar(run.timeframe)}</td>
                      <td><span className="af-status-text">{displayScalar(run.status)}</span></td>
                      <td>{displayScalar(run.total_trades)}</td>
                      <td>{displayMoney(run.net_profit)}</td>
                      <td>{typeof run.max_drawdown === "number" ? `${displayNumber(run.max_drawdown)}%` : "—"}</td>
                      <td>{cancellable(run.status) ? <button type="button" aria-label={`Cancel backtest ${run.run_id}`} disabled={Boolean(pendingAction)} onClick={() => { void cancelBacktest(run.run_id); }}>Cancel</button> : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SurfacePanel>

        <SurfacePanel eyebrow="Walk-Forward / OOS" title="Validation Jobs" authority={data?.walkForward.state ?? "LOADING"}>
          {!data ? (
            <AuthorityMessage state="LOADING" title="Walk-forward jobs" unavailable="" />
          ) : data.walkForward.state !== "AVAILABLE" ? (
            <AuthorityMessage
              state={data.walkForward.state}
              title="Walk-forward jobs"
              unavailable="Walk-forward/OOS authority is unavailable. No completion or success state is inferred."
              stale="Walk-forward/OOS evidence is stale. Job progress and completion states are withheld until fresh evidence is available."
              unknown="Walk-forward/OOS trust is unknown. No completion, success, or promotion state is inferred."
            />
          ) : recentWalkForward.length === 0 ? (
            <AuthorityMessage state="AVAILABLE" isEmpty title="Walk-forward jobs" unavailable="" empty="No authoritative walk-forward jobs are recorded." />
          ) : (
            <div className="af-testing-job-list">
              {recentWalkForward.map((job) => {
                const total = Number(job.progress?.total ?? 0);
                const done = Number(job.progress?.done ?? 0);
                const progress = total > 0 ? Math.min(100, Math.max(0, (done / total) * 100)) : null;
                return (
                  <div className="af-testing-job" key={job.jobId}>
                    <div className="af-testing-job-head">
                      <div><strong>{job.strategyId}</strong><span>{job.instrument} · {job.timeframe}</span></div>
                      <span className="af-status-text">{job.status}</span>
                    </div>
                    <div className="af-testing-progress"><i style={{ width: progress === null ? "0%" : `${progress}%` }} /></div>
                    <div className="af-testing-job-foot"><span>Progress {progress === null ? "—" : `${done}/${total}`}</span><span>OOS {displayScalar(job.oosDays)} days</span></div>
                    {job.error && <p>{job.error}</p>}
                    {cancellable(job.status) && <button type="button" aria-label={`Cancel walk-forward ${job.jobId}`} disabled={Boolean(pendingAction)} onClick={() => { void cancelWalkForward(job.jobId); }}>Cancel</button>}
                  </div>
                );
              })}
            </div>
          )}
        </SurfacePanel>
      </div>

      <SurfacePanel eyebrow="Evidence" title="Validation / Robustness Reports" authority={data?.reports.state ?? "LOADING"}>
        {!data ? (
          <AuthorityMessage state="LOADING" title="Validation reports" unavailable="" />
        ) : data.reports.state !== "AVAILABLE" ? (
          <AuthorityMessage
            state={data.reports.state}
            title="Validation reports"
            unavailable="Report authority is unavailable. No validation, robustness, OOS, or readiness verdict is fabricated."
            stale="Validation report evidence is stale. Stale verdicts are withheld and are not treated as current qualification."
            unknown="Validation report trust is unknown. No robustness, OOS, or readiness verdict is inferred."
          />
        ) : reports.length === 0 ? (
          <AuthorityMessage state="AVAILABLE" isEmpty title="Validation reports" unavailable="" empty="No authoritative validation reports are recorded." />
        ) : (
          <div className="af-report-grid">
            {reports.map((report) => (
              <article className="af-report-card" key={report.id}>
                <div><span>{displayScalar(report.category)}</span><strong>{displayScalar(report.status)}</strong></div>
                <h3>{report.title}</h3>
                <p>{report.summary}</p>
                <footer><span>{displayScalar(report.period)}</span><time>{displayScalar(report.generatedAt)}</time></footer>
              </article>
            ))}
          </div>
        )}
      </SurfacePanel>
    </div>
  );
};
