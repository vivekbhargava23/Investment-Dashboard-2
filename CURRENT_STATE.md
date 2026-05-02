# CURRENT_STATE.md

## Directory Tree Structure

```text
.
├── app/
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── behaviour.py
│   │   ├── lot.py
│   │   ├── portfolio.py
│   │   ├── position.py
│   │   ├── risk.py
│   │   ├── tax.py
│   │   └── transaction.py
│   ├── data/
│   │   ├── seeds/
│   │   │   ├── portfolio.json
│   │   │   └── portfolio.json.pre-tx-migration
│   │   ├── __init__.py
│   │   └── repository.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── finnhub_client.py
│   │   ├── history_service.py
│   │   ├── price_service.py
│   │   └── yfinance_client.py
│   ├── ui/
│   │   ├── components/
│   │   │   ├── __init__.py
│   │   │   ├── disposal_simulator.py
│   │   │   ├── harvest_table.py
│   │   │   ├── lot_table.py
│   │   │   ├── performance_chart.py
│   │   │   ├── position_table.py
│   │   │   ├── summary_bar.py
│   │   │   └── tax_summary.py
│   │   ├── pages/
│   │   │   ├── __init__.py
│   │   │   ├── behavioural_ledger.py
│   │   │   ├── decision_gates.py
│   │   │   ├── lot_ledger.py
│   │   │   ├── manage_portfolio.py
│   │   │   ├── overview.py
│   │   │   ├── performance.py
│   │   │   └── tax_dashboard.py
│   │   └── __init__.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── formatting.py
│   │   └── logger.py
│   ├── __init__.py
│   └── main.py
├── Claude Related/
│   ├── CLAUDE.md
│   └── CLAUDE_PROJECT_INSTRUCTIONS.md
├── data/
│   ├── portfolio.json
│   ├── portfolio.json.backup-phase1
│   └── portfolio.json.pre-tx-migration
├── docs/
│   ├── CLAUDE.md
│   ├── methodology.md
│   ├── phase1_foundation.md
│   ├── phase2_domain_models.md
│   ├── phase3_price_engine.md
│   ├── phase4_overview_ui.md
│   ├── phase5_fifo_ledger.md
│   ├── phase6_tax_dashboard.md
│   ├── phase7_performance_charts.md
│   ├── phase8_decision_gates.md
│   └── phase9_behavioural_ledger.md
├── scripts/
│   ├── migrate_to_transactions.py
│   ├── recompute_tax_year.py
│   └── verify_data_integrity.py
├── tests/
│   ├── __init__.py
│   ├── test_fifo.py
│   ├── test_repository.py
│   ├── test_tax.py
│   └── test_transaction.py
├── CLAUDE.md
├── EXECUTION_PLAN.md
├── instructions.md
├── pyproject.toml
├── README.md
├── REFACTOR_LOG.md
├── requirements-dev.txt
├── requirements.txt
├── run.sh
└── toggle.sh
```

## Python File Summaries

### Root / Main
- **app/main.py**: The entry point for the Streamlit application, configuring the page layout and initializing settings.

### Config
- **app/config/settings.py**: Manages application configuration using Pydantic BaseSettings, loading values from environment variables.

### Core Domain Models
- **app/core/transaction.py**: Defines the append-only event log for BUY and SELL transactions from which all state is derived.
- **app/core/position.py**: Models individual tickers, their transactions, and live-price-derived calculations like unrealised gain.
- **app/core/lot.py**: Implements the FIFO disposal engine and OpenLot models for German tax compliance.
- **app/core/tax.py**: Contains the German capital gains tax engine, implementing Abgeltungsteuer rules and annual allowance tracking.
- **app/core/portfolio.py**: Aggregates all positions into a portfolio with summary metrics and weighting calculations.
- **app/core/behaviour.py**: Models the behavioural ledger, tracking recurring investor patterns and session logs.
- **app/core/risk.py**: Implements risk domain models, including catalyst calendars, active risk flags, and pre-trade checklists.

### Data Management
- **app/data/repository.py**: Handles loading and saving portfolio and tax data to JSON storage, with fallback to seed data.

### Services
- **app/services/price_service.py**: Unified service for fetching live prices via Finnhub or yfinance and performing EUR conversions.
- **app/services/finnhub_client.py**: REST client for US-listed ticker prices using the Finnhub API with caching.
- **app/services/history_service.py**: Reconstructs historical portfolio values and fetches OHLCV data via yfinance.
- **app/services/yfinance_client.py**: Wrapper for the yfinance API to fetch prices for exchange-suffixed tickers (e.g., Frankfurt, Tokyo).

### UI Components
- **app/ui/components/summary_bar.py**: Renders a top-of-page summary strip with portfolio totals and tax allowance status.
- **app/ui/components/harvest_table.py**: Calculator for tax exposure and tax-loss harvesting opportunities based on current holdings.
- **app/ui/components/tax_summary.py**: Displays a year-to-date summary of tax allowance usage, realised P&L, and loss pots.
- **app/ui/components/lot_table.py**: Renders a detailed table of open lots for a single position in FIFO order.
- **app/ui/components/position_table.py**: Displays a live overview of all portfolio positions with key performance metrics.
- **app/ui/components/performance_chart.py**: Provides Plotly-based visualizations for portfolio and individual ticker performance history.
- **app/ui/components/disposal_simulator.py**: Interactive tool to simulate the tax and cash impact of selling specific share amounts.

### UI Pages
- **app/ui/pages/overview.py**: Live position overview page showing the current portfolio state and performance.
- **app/ui/pages/manage_portfolio.py**: Page for managing portfolio holdings, including adding new positions and transactions.
- **app/ui/pages/tax_dashboard.py**: Central dashboard for tracking tax-year state, realised gains, and harvesting opportunities.
- **app/ui/pages/lot_ledger.py**: Detailed FIFO lot ledger and pre-trade disposal simulator for per-position analysis.
- **app/ui/pages/performance.py**: Visual history of portfolio value and individual position price movements.
- **app/ui/pages/decision_gates.py**: Dashboard for managing catalysts, active risk flags, and pre-trade checklists.
- **app/ui/pages/behavioural_ledger.py**: Ledger for tracking and resolving behavioural biases and logging review sessions.

### Utilities
- **app/utils/formatting.py**: Centralized utilities for formatting currency, percentages, and gains for the UI.
- **app/utils/logger.py**: Configures structured logging using `structlog` for application-wide use.

### Scripts
- **scripts/verify_data_integrity.py**: Utility script to validate the runtime JSON data structure and consistency.
- **scripts/recompute_tax_year.py**: One-shot script to rebuild the tax year state from historical transaction records.
- **scripts/migrate_to_transactions.py**: Migration tool to convert legacy lot-based JSON data to the new transaction-log schema.

### Tests
- **tests/test_repository.py**: Integration tests for data persistence and repository fallback logic.
- **tests/test_transaction.py**: Unit tests for the transaction model and FIFO replay logic.
- **tests/test_fifo.py**: Exhaustive tests for the FIFO disposal engine using complex real-world sequences.
- **tests/test_tax.py**: Validation of the German tax engine's gain calculations and allowance logic.
