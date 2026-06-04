# Investment Dashboard

## Working on this project

If you're Vivek (or any future maintainer), start with [`docs/VIVEK.md`](docs/VIVEK.md). It's a one-page reference covering the entire workflow.

Ticket workflow is documented in `docs/VIVEK.md`. The GitHub Projects board at https://github.com/users/vivekbhargava23/projects/2 is the source of truth for ticket state and ordering.

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

### 4. First-time portfolio setup

To populate the application with an initial set of data, you can run the seed script which imports a reference CSV:

```bash
python -m app.scripts.seed_portfolio
```

This will create a `data/portfolio.json` file. You can then run the dashboard to view the data.

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

- [Architecture](docs/ARCHITECTURE.md)
- [Methodology](docs/METHODOLOGY.md)
