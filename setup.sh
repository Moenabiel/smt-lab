#!/usr/bin/env bash
# macOS / Linux setup:  bash setup.sh
set -euo pipefail
cd "$(dirname "$0")"
PY=$(command -v python3.12 || command -v python3.13 || command -v python3.11 || command -v python3)
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
echo; echo "Running self-tests ..."
.venv/bin/python tests/test_lookahead.py
echo; echo "Setup OK. Smoke test next:"
echo "  .venv/bin/python make_synthetic.py"
echo "  .venv/bin/python run_backtest.py --a data/synth_NQ_1m.parquet --b data/synth_ES_1m.parquet"
