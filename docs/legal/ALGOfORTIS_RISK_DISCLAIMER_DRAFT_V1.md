# AlgoFortis V1 — Risk Disclosure & Disclaimer (Draft)

> [!CAUTION]
> **HIGH-RISK FINANCIAL DISCLOSURE:**  
> Quantitative analysis, algorithmic modeling, and trading in financial markets involve substantial risk of capital loss. This document is a draft risk disclosure prepared for release readiness and beta testing.

**LAST UPDATED:** `[EFFECTIVE_DATE]`  
**ISSUED BY:** `[LEGAL_ENTITY_NAME]`  
**REGISTERED ADDRESS:** `[REGISTERED_ADDRESS]`  
**INQUIRIES:** `[LEGAL_EMAIL]`  

---

## 1. Substantial Risk of Financial Loss

Trading in financial markets—including but not limited to equities, indices, exchange-traded derivatives (futures and options), commodities, and foreign exchange—carries a high level of risk and may not be suitable for all persons. 

Before using AlgoFortis or designing quantitative trading strategies, you should carefully evaluate your investment objectives, financial situation, trading experience, and appetite for risk. **You may sustain a total loss of your initial capital and, in leveraged markets, may incur obligations exceeding your account balance.**

---

## 2. SEBI Mandated Risk Disclosures (Derivatives Trading)

In compliance with advisories published by the Securities and Exchange Board of India (SEBI) regarding trading in equity futures and options (F&O):
1. **High Loss Probability:** Studies conducted by SEBI demonstrate that **9 out of 10 individual traders in the equity F&O segment incur net financial losses**.
2. **Substantial Negative Payoff:** On average, loss-makers registered net trading losses in addition to significant transaction costs, exchange levies, clearing fees, and statutory taxes (STT/GST).
3. **Overtrading & Leverage:** Derivative contracts are inherently leveraged instruments. Leverage amplifies both gains and losses rapidly.

---

## 3. Backtesting & Hypothetical Performance Disclaimer

1. **Simulated Nature:** Backtested performance results are generated through retrospective application of mathematical algorithms to historical market data. They do **not** represent actual trading.
2. **Inherent Limitations of Historical Models:**
   - **Overfitting & Curve-Fitting:** Strategies optimized on past market cycles may fail to perform in unobserved future market regimes.
   - **Market Impact & Liquidity:** Backtests assume trade execution at model prices; they cannot simulate actual order book impact, queue position, or illiquidity.
   - **Slippage & Latency:** Real-world execution is subject to exchange latency, routing delays, network jitter, and price slippage, none of which can be perfectly replicated in offline backtesting.
   - **Exchange & Broker Fees:** Unless custom fee models are accurately configured, backtests may exclude brokerage charges, stamp duty, transaction taxes, and slippage.
3. **No Representation:** No representation or guarantee is being made that any account will or is likely to achieve profits or losses similar to those simulated in AlgoFortis.

---

## 4. Paper Trading / Simulated Execution Disclaimer

1. **Virtual Capital Only:** The Paper Trading Engine in AlgoFortis operates entirely with simulated virtual balances. No actual currency, securities, or capital are at risk during paper trading.
2. **Execution Discrepancy:** Simulated fills do not interact with exchange matching engines. An order that appears filled in simulated paper trading might not execute or might execute at a vastly different price in live market conditions.

---

## 5. Live Trading Permanently Disarmed in V1

1. **Fail-Closed Architecture:** AlgoFortis Local V1 is strictly built and certified with:
   ```ini
   READ_ONLY=true
   DISARMED=true
   live_global_hold=true
   broker mutation=ZERO
   real broker connection=NONE
   ```
2. **Zero Real Broker Connectivity:** The Software contains **no** capability to connect to live brokerage execution gateways, place real exchange orders, or handle real capital. Any attempt to invoke live trading endpoints is rejected with HTTP 403 `EXECUTION_DISABLED`.
3. **No Liability for Third-Party Modifications:** The Company assumes zero liability if any user modifies, tampers with, or connects third-party execution software to AlgoFortis outputs.

---

## 6. Software & Technical Risks

1. **System & Environmental Failures:** Software operation is subject to technical risks, including hardware malfunctions, operating system updates, database lockouts, network disconnects, and power outages.
2. **Third-Party Data Accuracy:** AlgoFortis utilizes historical datasets and market feeds supplied by third-party data vendors. The Company makes no warranty regarding the completeness, timeliness, accuracy, or continuity of third-party market data.
3. **Software Defects:** While AlgoFortis V1 has completed extensive regression certification, software inherently contains the possibility of latent defects, mathematical rounding anomalies, or unexpected exceptions.

---

## 7. Sole Responsibility of User

You acknowledge and agree that:
- You are solely responsible for all research, analytical assumptions, strategy algorithms, risk parameters, and financial decisions developed using AlgoFortis.
- `[LEGAL_ENTITY_NAME]`, its founders, developers, officers, and contributors are **not** liable for any financial losses or damages resulting directly or indirectly from your use of the Software.
