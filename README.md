# Investment Dashboard

Personal investment dashboard for tracking a Scalable Capital portfolio — German tax-aware (FIFO, Sparerpauschbetrag), FX-aware, with live valuations and decision-support tooling.

## Setup

### 1. Create and activate the conda environment

```bash
conda env create -f environment.yml
conda activate investment-dashboard
```

### 2. Install the package in editable mode with dev dependencies

```bash
pip install -e ".[dev]"
```

### 3. Setup secrets

```bash
cp .env.example .env
# Edit .env and fill in your API keys (Finnhub, etc.)
```

The `.env` file is git-ignored and never committed. See `.env.example` for the required variables.

## Run

```bash
streamlit run app/ui/main.py
```

## Tests

```bash
pytest
```

## Lint and type-check

```bash
ruff check .
mypy app/
lint-imports
```

## Docs

- [Project state](docs/PROJECT_STATE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Methodology](docs/METHODOLOGY.md)
- [Session log](docs/SESSION_LOG.md)
