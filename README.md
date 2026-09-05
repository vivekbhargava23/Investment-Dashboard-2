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

## Import

**Sync with Scalable** is the one door for broker data. Drop your Scalable Capital
CSV export on it and every trade that is new by reference is imported on the spot,
with no further click. Anything that needs a decision — a holding with no price
feed, a share count that disagrees, a row that looks like a duplicate of something
you entered by hand — is listed above the holdings table as a numbered task, each
with the buttons that settle it. **Undo last sync** puts `portfolio.json` and
`isin_map.json` back exactly as they were before the upload, including every change
you made while the file was open.

## Run

The easiest way on macOS is to double-click `run_dashboard.command` in Finder.
It finds the correct Conda installation, creates the project environment on the
first launch if needed, automatically rebuilds it if its core packages are
damaged, and opens the dashboard in your browser. To stop it, return to the
Terminal window and press **Ctrl+C**.

You can also launch the same shortcut from a terminal:

```bash
./run_dashboard.command
```

The launcher uses the environment's full path, so it also works when multiple
Conda installations (such as Anaconda and Miniforge) are installed. For manual
development, activate the environment that belongs to the intended installation
and run `streamlit run app/ui/main.py`.

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
