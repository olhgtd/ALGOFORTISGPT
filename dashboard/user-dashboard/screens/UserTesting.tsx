import React, { useEffect, useMemo, useState } from "react";
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
}

const countValue = <T,>(block: { state: UserSurfaceAuthorityState; data: T[] } | undefined) =>
  block?.state === "AVAILABLE" ? block.data.length : "—";

export const UserTesting: React.FC<UserTestingProps> = ({ loadData = loadTestingSurface }) => {
  const [data, setData] = useState<TestingSurfaceData | null>(null);

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

  const recentBacktests = useMemo(() => data?.backtests.state === "AVAILABLE" ? data.backtests.data.slice(0, 12) : [], [data]);
  const recentWalkForward = useMemo(() => data?.walkForward.state === "AVAILABLE" ? data.walkForward.data.slice(0, 10) : [], [data]);
  const reports = useMemo(() => data?.reports.state === "AVAILABLE" ? data.reports.data.slice(0, 12) : [], [data]);

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
                <thead><tr><th>Strategy</th><th>Instrument</th><th>Status</th><th>Trades</th><th>Net P&L</th><th>Max DD</th></tr></thead>
                <tbody>
                  {recentBacktests.map((run) => (
                    <tr key={run.run_id}>
                      <td><strong>{displayScalar(run.strategy_name || run.strategy_id)}</strong><small>{displayScalar(run.version)}</small></td>
                      <td>{displayScalar(run.instrument)} · {displayScalar(run.timeframe)}</td>
                      <td><span className="af-status-text">{displayScalar(run.status)}</span></td>
                      <td>{displayScalar(run.total_trades)}</td>
                      <td>{displayMoney(run.net_profit)}</td>
                      <td>{typeof run.max_drawdown === "number" ? `${displayNumber(run.max_drawdown)}%` : "—"}</td>
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
