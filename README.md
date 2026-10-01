# AlgoFortis — Trading Research & Risk Platform

AlgoFortis is a Windows-focused trading research, backtest, paper-trading, portfolio-risk, and governance platform with fail-closed safety boundaries and private per-user runtime isolation.

The current product name is **AlgoFortis**. `SentinelX` names that remain in explicitly historical V1 artifacts are retained only for compatibility/history and are not the current product identity.

## Architecture Layout

- `dashboard/`: FastAPI runtime backend, authenticated owner/user visual control centers, and Vite/React web client.
- `engine/`: Modular research/trading engine spanning market data, backtest, paper execution, risk governance, audit, reconciliation, and AI/Laya decision intelligence.
- `strategies/`: Strategy implementations and research interfaces.
- `config/`: System, execution, risk, deployment, and paper-trading configurations.
- `data/`: Deterministic market-data fixtures and ingestion pipeline root.
- `docs/`: Product architecture specifications, frozen decisions, qualification evidence, contracts, and requirements.

## Starting AlgoFortis

For the current local Windows product, use the windowless launcher:

```powershell
pythonw START_ALGOFORTIS.pyw
```

The launcher prefers the native `AlgoFortis.exe` desktop shell when present and otherwise starts the governed local runtime controller.

## Safety State

- `RiskGateV2` remains the sole `ApprovedOrder` authority.
- Live remains `READ_ONLY/DISARMED` in the current qualified product.
- AI/Laya decision intelligence is scoped to research/backtest/paper workflows and does not directly mint executable orders.
