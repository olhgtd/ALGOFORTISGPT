# SentinelX — Algorithmic Trading Platform

SentinelX is a professional institutional algorithmic trading and portfolio risk management platform engineered for Windows with fail-closed security and private NTFS ACL runtime isolation.

## Architecture Layout

- `dashboard/`: FastAPI runtime backend, authenticated owner/user visual control centers, and Vite/React web client.
- `engine/`: Modular trading engine spanning execution, risk governance, market data feeds, paper trading, and audit reconciliation.
- `strategies/`: Execution strategies and algorithms.
- `config/`: System, execution, risk, and paper trading configurations.
- `data/`: Built-in deterministic market data fixtures and ingestion pipeline root.
- `docs/`: Product architecture specifications, contracts, and requirements.

## Starting SentinelX

In production, run the windowless launcher:

```powershell
pythonw START_SENTINELX.pyw
```

This starts the authoritative local backend with per-user private ACL runtime data in `%LOCALAPPDATA%\SentinelX` and opens the browser interface.
