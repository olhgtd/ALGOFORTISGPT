import { chromium } from "playwright";

const base = "http://127.0.0.1:4173/?surface=dashboard-v3&workspace=user";

const now = "2026-10-05T18:00:00Z";

const backtestRun = (id, status = "PENDING") => ({
  run_id: id,
  user_id: "user-smoke",
  strategy_id: "SMOKE-STRAT",
  strategy_name: "Smoke Strategy",
  version: "v1",
  instrument: "NIFTY",
  timeframe: "5m",
  date_range: "2026-01-05",
  initial_capital: 500000,
  net_profit: 0,
  net_profit_pct: 0,
  win_rate: 0,
  profit_factor: 0,
  sharpe_ratio: 0,
  max_drawdown: 0,
  total_trades: 0,
  winning_trades: 0,
  losing_trades: 0,
  avg_profit_trade: 0,
  avg_win: 0,
  avg_loss: 0,
  status,
  quality_score: 0,
  policy_snapshot: "SMOKE",
  policy_details: { mode: "ATR", distance: 1 },
  data_fingerprint: "smoke-data",
  data_source_name: "SMOKE",
  equity_curve: [],
  created_at_utc: now,
});

const wfJob = (id, status = "RUNNING") => ({
  jobId: id,
  userId: "user-smoke",
  strategyId: "SMOKE-STRAT",
  strategyVersionId: "v1",
  sourceSha256: "smoke-sha",
  datasetId: "SMOKE-DATA",
  instrument: "NIFTY",
  timeframe: "5m",
  isDays: 20,
  oosDays: 5,
  initialCapital: 500000,
  policy: {},
  status,
  cancelRequested: false,
  overall: {},
  error: null,
  windows: [],
  progress: { done: status === "COMPLETED" ? 4 : 1, total: 4 },
  createdAtUtc: now,
  updatedAtUtc: now,
});

const paperSession = (id, status = "INITIALIZED") => ({
  session_id: id,
  user_id: "user-smoke",
  strategy_id: "SMOKE-STRAT",
  strategy_name: "Smoke Strategy",
  strategy_version: "v1",
  instrument: "NIFTY",
  timeframe: "5m",
  initial_capital: 50000,
  current_equity: 50000,
  available_cash: 50000,
  used_capital: 0,
  realized_pnl: 0,
  unrealized_pnl: 0,
  day_pnl: 0,
  total_pnl: 0,
  return_pct: 0,
  trades_count: 0,
  status,
  data_source_mode: "HISTORICAL_REPLAY",
  created_at_utc: now,
  updated_at_utc: now,
});

const deployment = (id, status = "DEPLOYED") => ({
  deploymentId: id,
  userId: "user-smoke",
  strategyId: "SMOKE-STRAT",
  strategyVersionId: "v1",
  connectionId: "SMOKE-CONN",
  instrument: "NIFTY",
  timeframe: "5m",
  executionMode: "LIVE_PAPER",
  status,
  blockReason: null,
  blockAuthority: "NONE",
  createdAtUtc: now,
  updatedAtUtc: now,
});

const strategy = {
  strategy_id: "SMOKE-STRAT",
  version_id: "v1",
  stage: "BACKTESTED",
  archived: false,
  source_sha256: "smoke-sha",
  protective_policy: "POL-SMOKE",
  admin_status: "ACTIVE",
  visibility: "PRIVATE",
};

const readiness = {
  strategyId: "SMOKE-STRAT",
  backtest: { ready: true, code: "READY", reason: "Smoke ready" },
  paper: { ready: true, code: "READY", reason: "Smoke ready" },
  livePaper: { ready: true, code: "READY", reason: "Smoke ready" },
  live: { ready: false, code: "DISARMED", reason: "Live remains disarmed" },
};

function requestBody(req) {
  try {
    return req.postDataJSON();
  } catch {
    return null;
  }
}

function assertRequest(state, method, path, predicate = () => true) {
  const found = state.requests.find((item) => item.method === method && item.path === path && predicate(item.body));
  if (!found) {
    throw new Error(`Missing expected request ${method} ${path}. Seen: ${JSON.stringify(state.requests, null, 2)}`);
  }
}

async function installMocks(page, state) {
  await page.addInitScript(() => {
    window.__ALGOFORTIS_SESSION_TOKEN__ = "user-smoke";
    window.__ALGOFORTIS_ENABLE_BACKEND__ = true;
  });

  await page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const p = url.pathname;
    const method = req.method();
    const bodyIn = requestBody(req);
    state.requests.push({ method, path: p, body: bodyIn });

    let status = 200;
    let body = {};

    if (p === "/api/v1/runtime/status") {
      body = { status: "READY", ready: true, available: true };
    } else if (p === "/api/v1/users/current") {
      body = {
        user_id: "user-smoke",
        sx_id: "AF-USER-SMOKE",
        role: "USER",
        lifecycle: "ACTIVE",
        account_status: "ACTIVE",
        activation_status: "REDEEMED",
        service_status: "ACTIVE",
        display_name: "User Smoke",
        namespace: "user",
        workspace_eligibility: { user: true, owner: false },
        effective_access: true,
      };
    } else if (p === "/api/v1/integration/system/health") {
      body = {
        adapter_reachable: true,
        database_connected: true,
        schema_version: 1,
        journal_mode: "WAL",
        audit_store_operational: true,
        audit_event_count: 1,
        trust: "FRESH",
        subsystems: { backend_api: "READY", persistence: "READY", risk_runtime: "READY" },
      };
    } else if (p === "/api/v1/market/chart") {
      const instrument = url.searchParams.get("instrument") || "NIFTY";
      body = {
        instrument,
        timeframe: url.searchParams.get("timeframe") || "5m",
        candles: {
          state: "AVAILABLE",
          value: [
            { time: now, open: 100, high: 102, low: 99, close: 101, volume: 1000 },
            { time: "2026-10-05T18:05:00Z", open: 101, high: 103, low: 100, close: 102, volume: 1100 },
          ],
        },
      };
    } else if (p === "/api/v1/user/connections" && method === "GET") {
      body = { connections: [{
        connectionId: "SMOKE-CONN",
        userId: "user-smoke",
        provider: "SMOKE",
        accountRef: "SMOKE-ACCOUNT",
        hasCredentialRef: true,
        status: "CONNECTED",
        marketDataCapability: "READY",
        executionCapability: "READ_ONLY",
        healthState: "HEALTHY",
        suspended: false,
        suspendReason: null,
        lastVerifiedAtUtc: now,
      }] };
    } else if (p === "/api/v1/user/live-readiness") {
      body = {
        user_id: "user-smoke",
        provider: "SMOKE",
        connection_state: "CONNECTED",
        error: null,
        account: {}, funds: {}, positions: [], orders: [], holdings: [],
        market_data: [], market_data_state: "FRESH", risk_state: "HEALTHY",
        last_success: now, last_failure: null, audit_id: "audit-smoke",
        reconciliation: { state: "CLEAN", differences: [] },
        capabilities: [],
        execution_policy: { arming_state: "READ_ONLY", mutation_allowed: false, global_hold: false, safe_mode: false },
        strategies: [{ id: "SMOKE-STRAT", name: "Smoke Strategy" }],
        instruments: [], intents: [],
      };
    } else if (p === "/api/v1/strategies" && method === "GET") {
      body = { strategies: state.strategies, trust: "FRESH" };
    } else if (p === "/api/v1/strategies" && method === "POST") {
      const newStrategy = {
        strategy_id: "SMOKE-SUBMITTED",
        version_id: "v1",
        stage: "DRAFT",
        archived: false,
        source_sha256: "submitted-sha",
        protective_policy: bodyIn?.protective_policy_identity || "",
        admin_status: "ACTIVE",
        visibility: "PRIVATE",
      };
      state.strategies.push(newStrategy);
      body = newStrategy;
    } else if (/^\/api\/v1\/strategies\/[^/]+\/readiness$/.test(p)) {
      body = { ...readiness, strategyId: decodeURIComponent(p.split("/")[4]) };
    } else if (p === "/api/v1/user/deployments" && method === "GET") {
      body = { deployments: state.deployments };
    } else if (p === "/api/v1/user/deployments" && method === "POST") {
      if (bodyIn?.execution_mode !== "LIVE_PAPER") {
        status = 422;
        body = { detail: "SMOKE_REJECT_NON_LIVE_PAPER" };
      } else {
        const created = deployment("dep-smoke", "DEPLOYED");
        state.deployments = state.deployments.filter((item) => item.deploymentId !== created.deploymentId).concat(created);
        body = { success: true, deployment: created };
      }
    } else if (/^\/api\/v1\/user\/deployments\/[^/]+\/(pause|resume|stop)$/.test(p) && method === "POST") {
      const [, , , , deploymentId, action] = p.split("/");
      const nextStatus = action === "pause" ? "PAUSED" : action === "resume" ? "DEPLOYED" : "STOPPED";
      state.deployments = state.deployments.map((item) => item.deploymentId === deploymentId ? { ...item, status: nextStatus } : item);
      body = { success: true, deployment: state.deployments.find((item) => item.deploymentId === deploymentId) };
    } else if (p === "/api/v1/backtests" && method === "GET") {
      body = state.backtests;
    } else if (p === "/api/v1/backtests" && method === "POST") {
      const created = backtestRun("bt-smoke", "PENDING");
      state.backtests = [created, ...state.backtests.filter((item) => item.run_id !== created.run_id)];
      status = 202;
      body = created;
    } else if (p === "/api/v1/backtests/bt-smoke/cancel" && method === "POST") {
      state.backtests = state.backtests.map((item) => item.run_id === "bt-smoke" ? { ...item, status: "CANCEL_REQUESTED" } : item);
      body = { success: true };
    } else if (p === "/api/v1/walkforward/jobs" && method === "GET") {
      body = { jobs: state.walkForward };
    } else if (p === "/api/v1/walkforward/jobs" && method === "POST") {
      const created = wfJob("wf-smoke", "RUNNING");
      state.walkForward = [created, ...state.walkForward.filter((item) => item.jobId !== created.jobId)];
      status = 202;
      body = { job_id: created.jobId, status: created.status, job: created };
    } else if (p === "/api/v1/walkforward/jobs/wf-smoke/cancel" && method === "POST") {
      const updated = { ...wfJob("wf-smoke", "CANCELLED"), cancelRequested: true };
      state.walkForward = state.walkForward.map((item) => item.jobId === "wf-smoke" ? updated : item);
      body = { job: updated };
    } else if (p === "/api/v1/reports") {
      body = [];
    } else if (p === "/api/v1/paper/sessions" && method === "GET") {
      body = state.paperSessions;
    } else if (p === "/api/v1/paper/sessions" && method === "POST") {
      const created = paperSession("ps-smoke", "INITIALIZED");
      state.paperSessions = [created, ...state.paperSessions.filter((item) => item.session_id !== created.session_id)];
      body = created;
    } else if (p === "/api/v1/paper/sessions/ps-smoke/start" && method === "POST") {
      const updated = paperSession("ps-smoke", "RUNNING");
      state.paperSessions = state.paperSessions.map((item) => item.session_id === "ps-smoke" ? updated : item);
      body = updated;
    } else if (p === "/api/v1/paper/sessions/ps-smoke/stop" && method === "POST") {
      const updated = paperSession("ps-smoke", "STOPPED");
      state.paperSessions = state.paperSessions.map((item) => item.session_id === "ps-smoke" ? updated : item);
      body = updated;
    } else if (p === "/api/v1/user/orders-portfolio") {
      body = {
        execution_mode: url.searchParams.get("mode") || "PAPER",
        availability: "AVAILABLE",
        source: "SMOKE",
        accounts: [], positions: [], orders: [], events: [], aggregate_exposure: null, limitations: [],
      };
    } else {
      body = {};
    }

    await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
  });
}

const browser = await chromium.launch({ headless: true });

try {
  const state = {
    requests: [],
    strategies: [strategy],
    deployments: [],
    backtests: [],
    walkForward: [],
    paperSessions: [],
  };

  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  await installMocks(page, state);

  await page.goto(`${base}#strategies`);
  await page.getByRole("heading", { name: "Strategies" }).waitFor({ state: "visible", timeout: 15000 });
  await page.getByLabel("Strategy source").fill("class SmokeStrategy {}");
  await page.getByLabel("Protective policy identity").fill("POL-SMOKE");
  await page.getByRole("button", { name: "Submit Strategy" }).click();
  await page.getByText(/Strategy submitted/).waitFor({ state: "visible", timeout: 5000 });
  assertRequest(state, "POST", "/api/v1/strategies", (body) => body?.source === "class SmokeStrategy {}" && body?.protective_policy_identity === "POL-SMOKE");

  await page.getByLabel("Deployment connection ID SMOKE-STRAT").fill("SMOKE-CONN");
  await page.getByLabel("Deployment instrument SMOKE-STRAT").fill("NIFTY");
  await page.getByLabel("Deployment timeframe SMOKE-STRAT").fill("5m");
  await page.getByLabel("Deployment risk ref SMOKE-STRAT").fill("risk-smoke");
  await page.getByLabel("Create LIVE_PAPER deployment SMOKE-STRAT").click();
  await page.getByText(/LIVE_PAPER deployment accepted/).waitFor({ state: "visible", timeout: 5000 });
  assertRequest(state, "POST", "/api/v1/user/deployments", (body) => body?.execution_mode === "LIVE_PAPER" && body?.connection_id === "SMOKE-CONN");
  if (await page.getByLabel("Deployment execution mode").count()) throw new Error("Unsafe execution-mode selector exists");

  await page.getByLabel("Pause deployment dep-smoke").click();
  await page.getByText(/Deployment pause accepted/).waitFor({ state: "visible", timeout: 5000 });
  await page.getByLabel("Resume deployment dep-smoke").click();
  await page.getByText(/Deployment resume accepted/).waitFor({ state: "visible", timeout: 5000 });
  await page.getByLabel("Stop deployment dep-smoke").click();
  await page.getByText(/Deployment stop accepted/).waitFor({ state: "visible", timeout: 5000 });
  assertRequest(state, "POST", "/api/v1/user/deployments/dep-smoke/pause");
  assertRequest(state, "POST", "/api/v1/user/deployments/dep-smoke/resume");
  assertRequest(state, "POST", "/api/v1/user/deployments/dep-smoke/stop");

  await page.goto(`${base}#testing`);
  await page.getByRole("heading", { name: "Testing & Validation" }).waitFor({ state: "visible", timeout: 10000 });
  await page.getByLabel("Backtest strategy ID").fill("SMOKE-STRAT");
  await page.getByLabel("Backtest dataset ID").fill("SMOKE-DATA");
  await page.getByRole("button", { name: "Run Backtest" }).click();
  await page.getByText(/Backtest accepted/).waitFor({ state: "visible", timeout: 5000 });
  assertRequest(state, "POST", "/api/v1/backtests", (body) => body?.strategy_id === "SMOKE-STRAT" && body?.dataset_id === "SMOKE-DATA");
  await page.getByLabel("Cancel backtest bt-smoke").click();
  assertRequest(state, "POST", "/api/v1/backtests/bt-smoke/cancel");

  await page.getByLabel("Walk-forward strategy ID").fill("SMOKE-STRAT");
  await page.getByLabel("Walk-forward dataset ID").fill("SMOKE-DATA");
  await page.getByRole("button", { name: "Run Walk-Forward" }).click();
  await page.getByText(/Walk-forward accepted/).waitFor({ state: "visible", timeout: 5000 });
  assertRequest(state, "POST", "/api/v1/walkforward/jobs", (body) => body?.strategy_id === "SMOKE-STRAT" && body?.dataset_id === "SMOKE-DATA");
  await page.getByLabel("Cancel walk-forward wf-smoke").click();
  assertRequest(state, "POST", "/api/v1/walkforward/jobs/wf-smoke/cancel");

  await page.goto(`${base}#trades`);
  await page.getByRole("heading", { name: "Trades" }).waitFor({ state: "visible", timeout: 10000 });
  await page.getByLabel("Paper strategy ID").fill("SMOKE-STRAT");
  await page.getByLabel("Paper dataset ID").fill("SMOKE-DATA");
  await page.getByRole("button", { name: "Create Paper Session" }).click();
  await page.getByText(/Paper session created/).waitFor({ state: "visible", timeout: 5000 });
  assertRequest(state, "POST", "/api/v1/paper/sessions", (body) => body?.strategy_id === "SMOKE-STRAT" && body?.data_source_mode === "HISTORICAL_REPLAY");
  await page.getByLabel("Start paper session ps-smoke").click();
  await page.getByText(/Paper session started/).waitFor({ state: "visible", timeout: 5000 });
  await page.getByLabel("Stop paper session ps-smoke").click();
  await page.getByText(/Paper session stopped/).waitFor({ state: "visible", timeout: 5000 });
  assertRequest(state, "POST", "/api/v1/paper/sessions/ps-smoke/start");
  assertRequest(state, "POST", "/api/v1/paper/sessions/ps-smoke/stop");

  await page.getByText("READ_ONLY / DISARMED").first().waitFor({ state: "visible", timeout: 5000 });
  if (await page.getByRole("button", { name: /Arm Live/i }).count()) throw new Error("Arm Live control exposed");
  if (state.requests.some((item) => item.path === "/api/v1/live/arm" || item.path.startsWith("/api/v1/live/orders") || item.path.startsWith("/api/v1/broker/orders"))) {
    throw new Error("Forbidden Live/broker mutation request observed");
  }

  console.log("USER_ACTION_CONTROL_SMOKE=PASS");
} finally {
  await browser.close();
}
