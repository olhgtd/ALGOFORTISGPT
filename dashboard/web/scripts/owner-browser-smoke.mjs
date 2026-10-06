import { chromium } from "playwright";

const base = "http://127.0.0.1:4173/?surface=dashboard-v3&workspace=owner";

const authority = {
  source: "BACKEND",
  trust: "FRESH",
  live_state: "READ_ONLY/DISARMED",
  broker_mutation: "ABSENT",
  surfaces: {
    health: { authority_state: "AVAILABLE", status: "OK" },
    access: { authority_state: "AVAILABLE", records: [] },
    strategies: { authority_state: "AVAILABLE", strategies: [] },
    connections: { authority_state: "AVAILABLE", connections: [] },
    datasets: { authority_state: "AVAILABLE", datasets: [] },
    security: { authority_state: "AVAILABLE" },
    ai: { authority_state: "AVAILABLE" },
  },
  incidents: [],
};

const productOps = {
  unresolved_incidents: 0,
  alert_health: "OK",
  privacy_requests: [],
  stale_policy_count: 0,
  backup_status: "UNAVAILABLE",
  restore_status: "UNAVAILABLE",
  rollback_status: "UNAVAILABLE",
  active_policy_versions: [],
  runbook_status: "UNAVAILABLE",
  live_state: "READ_ONLY/DISARMED",
  ai_authority: "INDEPENDENT_CANDIDATE_SOURCE",
};

async function installMocks(page, state) {
  await page.addInitScript(() => {
    window.__ALGOFORTIS_SESSION_TOKEN__ = "owner-smoke";
    Object.defineProperty(window, "PublicKeyCredential", {
      value: function PublicKeyCredential() {},
      configurable: true,
    });
  });

  await page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const p = new URL(req.url()).pathname;
    let status = 200;
    let body = {};

    if (p === "/api/v1/users/current") {
      body = {
        user_id: "00000000-0000-0000-0000-000000000001",
        sx_id: "SX-OWNER",
        role: "OWNER",
        lifecycle: "ACTIVE",
        account_status: "ACTIVE",
        display_name: "Owner Smoke",
        namespace: "owner",
        workspace_eligibility: { user: true, owner: true },
        effective_access: true,
      };
    } else if (p === "/api/v1/runtime/status") {
      body = { status: "READY", ready: true, available: true };
    } else if (p === "/api/v1/owner/admin/authority") {
      body = authority;
    } else if (p === "/api/v1/owner/backtests") {
      body = [];
    } else if (p === "/api/v1/owner/walkforward/jobs") {
      body = { jobs: [] };
    } else if (p === "/api/v1/owner/paper/sessions") {
      body = [];
    } else if (p === "/api/v1/owner/deployments") {
      body = { deployments: [] };
    } else if (p === "/api/v1/owner/deployments/recovery") {
      body = { state: "AVAILABLE", rows: [] };
    } else if (p === "/api/v1/owner/historical/providers") {
      body = { providers: [] };
    } else if (p === "/api/v1/owner/historical/sync/jobs") {
      body = { jobs: [] };
    } else if (p === "/api/v1/owner/safety") {
      body = {
        authority_state: "AVAILABLE",
        safe_mode: { state: "AVAILABLE", enabled: false },
        global_hold: { state: "AVAILABLE", enabled: true },
        risk_gate: { state: "UNAVAILABLE", reason: "RISK_SNAPSHOT_AUTHORITY_UNAVAILABLE" },
        live_state: "READ_ONLY/DISARMED",
        broker_mutation: "ABSENT",
        kill_switch: {
          state: "NOT_CONNECTED",
          reason: "CANONICAL_KILL_SWITCH_BRIDGE_NOT_ATTACHED",
        },
      };
    } else if (p === "/api/v1/product-ops/owner/health") {
      body = productOps;
    } else if (p === "/api/v1/owner/admin/incidents") {
      body = { incidents: [] };
    } else if (p === "/api/v1/integration/audit/events") {
      body = { events: [] };
    } else if (p.endsWith("/owner/admin/step-up/options")) {
      state.stepUpSeen = true;
      status = 403;
      body = { detail: "SMOKE_STEP_UP_REQUIRED" };
    } else if (p === "/api/v1/backtests" && req.method() === "POST") {
      status = 422;
      body = { detail: "SMOKE_REJECTION" };
    }

    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

const browser = await chromium.launch({ headless: true });

try {
  const desktop = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const dstate = { stepUpSeen: false };
  await installMocks(desktop, dstate);
  await desktop.goto(base);
  await desktop
    .getByRole("button", { name: /^Overview/i })
    .first()
    .waitFor({ state: "visible", timeout: 15000 });

  for (const label of [
    "Backtests / Walk-Forward",
    "Paper Trading",
    "Deployments",
    "Connections & Data",
    "Risk & Safety",
    "System Health",
  ]) {
    await desktop
      .getByRole("button", {
        name: new RegExp(`^${label.replace(/[.*+?^${}()|[\\]\\]/g, "\\$&")}`, "i"),
      })
      .first()
      .click();
  }

  await desktop.getByRole("button", { name: /^Backtests \/ Walk-Forward/i }).first().click();
  await desktop.getByPlaceholder("Strategy ID").fill("SMOKE-STRAT");
  await desktop.getByPlaceholder("Dataset ID").fill("SMOKE-DATA");
  await desktop.getByRole("button", { name: "Run Backtest" }).click();
  await desktop.getByText("SMOKE_REJECTION").waitFor({ state: "visible", timeout: 5000 });

  await desktop.getByRole("button", { name: /^Risk & Safety/i }).first().click();
  await desktop.getByRole("button", { name: "Release Global Hold" }).click();
  await desktop
    .getByText("SMOKE_STEP_UP_REQUIRED")
    .waitFor({ state: "visible", timeout: 5000 });
  if (!dstate.stepUpSeen) {
    throw new Error("step-up options route was not requested");
  }

  const mobile = await browser.newPage({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
  });
  const mstate = { stepUpSeen: false };
  await installMocks(mobile, mstate);
  await mobile.goto(base);
  await mobile
    .getByRole("button", { name: /^OVERVIEW/i })
    .waitFor({ state: "visible", timeout: 15000 });
  await mobile.getByRole("button", { name: /^MORE/i }).click();
  await mobile
    .getByRole("dialog", { name: "More Owner screens" })
    .waitFor({ state: "visible" });
  await mobile.getByRole("button", { name: /^Connections & Data/i }).click();
  await mobile
    .getByRole("heading", { name: "Connections & Data" })
    .waitFor({ state: "visible", timeout: 5000 });

  console.log("OWNER_BROWSER_SMOKE=PASS");
} finally {
  await browser.close();
}
