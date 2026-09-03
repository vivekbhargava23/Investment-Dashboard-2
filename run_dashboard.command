#!/bin/bash
# Double-click this file in Finder to set up and launch the dashboard.

set -eu

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_NAME="investment-dashboard"
CONDA_EXE=""
ENV_PREFIX=""

cd "$REPO_DIR"

pause_before_exit() {
    echo ""
    read -r -p "Press Enter to close this window..." _unused || true
}
trap pause_before_exit EXIT

# Finder does not load the interactive shell PATH, so check the common macOS
# installation locations explicitly. Checking every installation also handles
# machines that have both Anaconda and Miniforge.
for CANDIDATE in \
    "/opt/homebrew/Caskroom/miniforge/base/bin/conda" \
    "$HOME/miniforge3/bin/conda" \
    "$HOME/opt/anaconda3/bin/conda" \
    "$HOME/miniconda3/bin/conda" \
    "$HOME/anaconda3/bin/conda" \
    "/opt/anaconda3/bin/conda" \
    "/opt/homebrew/anaconda3/bin/conda" \
    "/opt/homebrew/bin/conda"; do
    if [ ! -x "$CANDIDATE" ]; then
        continue
    fi

    if [ -z "$CONDA_EXE" ]; then
        CONDA_EXE="$CANDIDATE"
    fi

    FOUND_PREFIX="$($CANDIDATE env list 2>/dev/null | awk -v suffix="/$ENV_NAME" \
        '$NF ~ (suffix "$") { print $NF; exit }')"
    if [ -n "$FOUND_PREFIX" ] && [ -x "$FOUND_PREFIX/bin/python" ]; then
        CONDA_EXE="$CANDIDATE"
        ENV_PREFIX="$FOUND_PREFIX"
        break
    fi
done

if [ -z "$CONDA_EXE" ]; then
    echo "Could not find Conda. Install Anaconda or Miniforge, then try again."
    exit 1
fi

# Project environments are disposable: environment.yml is their source of truth.
# If core imports fail, replace the damaged environment instead of applying a
# partial package upgrade that can leave mixed Conda/Pip files behind.
if [ -n "$ENV_PREFIX" ] && ! "$ENV_PREFIX/bin/python" -c \
    "import pydantic; import streamlit" >/dev/null 2>&1; then
    echo "The '$ENV_NAME' environment is damaged and will be rebuilt."
    "$CONDA_EXE" env remove --prefix "$ENV_PREFIX" --yes
    ENV_PREFIX=""
fi

# A missing environment is the only time the launcher changes Python packages.
# environment.yml already installs this project and its dependencies.
if [ -z "$ENV_PREFIX" ]; then
    echo "First launch: creating the '$ENV_NAME' environment."
    echo "This can take several minutes, but it only happens once."
    "$CONDA_EXE" env create --file "$REPO_DIR/environment.yml"

    CONDA_BASE="$($CONDA_EXE info --base)"
    ENV_PREFIX="$CONDA_BASE/envs/$ENV_NAME"
fi

if [ ! -x "$ENV_PREFIX/bin/python" ]; then
    echo "The '$ENV_NAME' environment is incomplete: $ENV_PREFIX"
    echo "Remove or repair that environment, then launch again."
    exit 1
fi

if ! "$ENV_PREFIX/bin/python" -c "import pydantic; import streamlit" >/dev/null 2>&1; then
    echo "The new environment was created, but its core packages cannot be imported."
    echo "No application data was changed. Check the Conda output above for details."
    exit 1
fi

if [ ! -f .env ] && [ -f .env.example ]; then
    cp .env.example .env
    echo "Created .env from .env.example. Add API keys there when needed."
fi

echo ""
echo "Starting Investment Dashboard..."
echo "Your browser should open automatically."
echo "To stop the dashboard, return to this window and press Ctrl+C."
echo ""

# Use the environment's Python directly. This avoids name-resolution problems
# when another Conda installation owns the currently active base environment.
"$ENV_PREFIX/bin/python" -m streamlit run "$REPO_DIR/app/ui/main.py"
