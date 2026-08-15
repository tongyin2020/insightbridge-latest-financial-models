#!/usr/bin/env bash
# Run the InsightBridge Financial Agent System.
# Defaults: observe-only, execution disabled.

set -euo pipefail

REPO_DIR="${AGENT_BASE:-$(cd "$(dirname "$0")/../.." && pwd)}"
PYTHON="${PYTHON:-/opt/anaconda3/envs/oi/bin/python3}"

export AGENT_OBSERVE_ONLY=1
export AGENT_EXECUTION_ENABLED=0

exec "$PYTHON" "$REPO_DIR/agent_system/run_agent_system.py" --run-reflection
