# AlgoFortis V2 G6 — Broker / Exchange / Regulatory Engineering Review

**Review date:** 2026-09-27  
**Selected first broker:** Angel One SmartAPI  
**Purpose:** OD-V2-09 engineering/compliance input for Phase-6 DISARMED/read-only design  
**Status:** CURRENT INPUT FOR DESIGN; MUST BE RECHECKED BEFORE G6 EXIT  

## Scope and limitation

This record captures the current public broker/exchange/regulatory inputs used to shape AlgoFortis Phase 6. It is an engineering/compliance input, not legal advice and not authorization for real-money execution.

Phase 6 remains `READ_ONLY / DISARMED`. A G6 pass does not enable broker mutation.

## Sources reviewed

1. Angel One SmartAPI — Exchange Regulations  
   `https://smartapi.angelone.in/exchange-regulations`
2. Angel One SmartAPI — User/API documentation and throttling table  
   `https://smartapi.angelone.in/docs/User`
3. SEBI — Circular dated 2025-09-30, `SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/132`, Extension of timeline for implementation of the 2025-02-04 retail-algo circular.
4. NSE — Retail Algo FAQ dated 2025-11-03, `FAQ_Retail Algo_03112025_NSE.pdf`.

## Current findings used by the design

### 1. Static-IP requirement

Angel One's current exchange-regulations page states that effective **2026-04-01**, API order execution is accepted only when it originates from the registered Static IP.

**Engineering consequence:**

- Phase-6 configuration must model static-IP eligibility as explicit versioned evidence.
- Missing/stale/unverified required evidence fails closed.
- Static-IP evidence cannot become arm authority.
- G6 does not need to place an order to prove the policy seam.

### 2. SmartAPI order throttling

Angel One's current API documentation states that place-order, modify-order, and cancel-order requests share a **combined 9 requests/second** order-API cap and also documents minute/hour limits.

**Engineering consequence:**

- Do not embed these values as unversioned source constants.
- Preserve them in a dated/versioned broker-rate policy/evidence profile.
- Phase 6 consumes injected policy.
- Missing policy blocks unbounded retry.
- G6 contains no callable real mutation path, so mutation limits are qualification metadata only at this stage.

### 3. Retail-algo framework applicability

SEBI's 2025-09-30 circular states that from **2026-04-01**, the retail-algo framework specified in the 2025-02-04 circular, together with exchange implementation standards and operational modalities, is applicable for all stock brokers.

**Engineering consequence:**

- Historical pre-framework assumptions cannot be used as current G6 truth.
- The rule review must be re-run before G6 exit and later again before any mutation/pilot authorization.

### 4. API orders and algo tagging / OPS framework

The reviewed NSE FAQ states that orders received through client APIs are considered Algo orders and require appropriate tagging, including standardized tagging for cases within the **10 OPS** threshold framework.

**Engineering consequence:**

- Order/API eligibility metadata must be policy-driven and versioned.
- The G6 read-only adapter does not synthesize or guess tags.
- Any future mutation design must consume a current exchange/broker-approved tagging policy rather than hard-coded legacy values.

### 5. Market Orders

The reviewed NSE FAQ states that algorithmic orders with order type **Market Order are not permitted**.

**Engineering consequence:**

- G6 policy validation/probes fail closed for `MARKET` on the selected retail-algo path.
- No silent conversion from Market to Limit is permitted.
- This must be re-verified before a later mutation release because exchange rules can change.

## Legacy Angel adapter observations relevant to Phase 6

The existing `engine/broker_adapters/angel_adapter.py` is not selected as the Phase-6 production authority path. The 2026-09-27 review found legacy behaviors that are inappropriate for the isolated V2 Live boundary, including:

- legacy base host `https://apiconnect.angelbroking.com` rather than the current profile being treated as versioned external configuration;
- fallback/default header values for API/client network identity fields;
- a mock-success response path when no HTTP client is supplied;
- mutation methods and observation methods co-located in one concrete adapter.

These observations justify the Owner-approved Option B: a separate isolated read-only Angel One V2 boundary rather than patching/promoting the legacy adapter.

## Recheck gate before G6 exit

Before declaring OD-V2-09 evidence current for G6 exit:

- re-open the authoritative Angel One SmartAPI docs/regulations pages;
- re-open current SEBI circulars applicable to retail API algorithmic trading;
- re-open current NSE implementation circulars/FAQ and check for superseding revisions;
- record the new review date and document identifiers;
- update the versioned broker/rate/order-policy evidence if any rule changed;
- keep Live DISARMED regardless of a successful review.

Any material uncertainty is a fail-closed G6 blocker, not a reason to infer a permissive rule.
