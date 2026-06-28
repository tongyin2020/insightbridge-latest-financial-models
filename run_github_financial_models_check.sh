#!/bin/zsh

set -euo pipefail

REPO_BASE="/Users/tongyin/Desktop/InsightBridge_Financial_Models_Latest"
TMP_BASE="/private/tmp/insightbridge_financial_origin_main_run"
PYTHON_BIN="${PYTHON_BIN:-/opt/anaconda3/bin/python3}"

RUN_TWS_CHECK=0
RUN_PAPER_CHECK=0

for arg in "$@"; do
  case "$arg" in
    --with-tws-check)
      RUN_TWS_CHECK=1
      ;;
    --with-paper-check)
      RUN_PAPER_CHECK=1
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: bash $0 [--with-tws-check] [--with-paper-check]" >&2
      exit 1
      ;;
  esac
done

echo "InsightBridge GitHub Financial Models Check"
echo "============================================================"
echo "repo: $REPO_BASE"

LOCAL_HEAD="$(git -C "$REPO_BASE" rev-parse --short HEAD)"
git -C "$REPO_BASE" fetch origin >/dev/null 2>&1 || true
REMOTE_HEAD="$(git -C "$REPO_BASE" rev-parse --short origin/main)"

echo "local_head:  $LOCAL_HEAD"
echo "remote_head: $REMOTE_HEAD"

rm -rf "$TMP_BASE"
mkdir -p "$TMP_BASE"
git -C "$REPO_BASE" archive origin/main | tar -x -C "$TMP_BASE"

echo "snapshot: $TMP_BASE"
echo "python:   $PYTHON_BIN"
echo "------------------------------------------------------------"
echo "[1/3] Offline dry-run framework self-check"
"$PYTHON_BIN" "$TMP_BASE/execution_framework/test_pipeline_dryrun.py"

if [[ "$RUN_TWS_CHECK" -eq 1 ]]; then
  echo "------------------------------------------------------------"
  echo "[2/3] TWS paper channel readiness"
  "$PYTHON_BIN" "$TMP_BASE/check_tws_paper_channel.py"
fi

if [[ "$RUN_PAPER_CHECK" -eq 1 ]]; then
  echo "------------------------------------------------------------"
  echo "[3/3] IBKR paper execution framework check"
  "$PYTHON_BIN" "$TMP_BASE/execution_framework/run_tws_paper.py" --check --symbols BTC,MES,ZN
fi

echo "------------------------------------------------------------"
echo "Done."
echo
echo "Useful direct commands:"
echo "  Offline self-check:"
echo "    $PYTHON_BIN $TMP_BASE/execution_framework/test_pipeline_dryrun.py"
echo
echo "  TWS paper readiness:"
echo "    $PYTHON_BIN $TMP_BASE/check_tws_paper_channel.py"
echo
echo "  Paper framework contract/account check:"
echo "    $PYTHON_BIN $TMP_BASE/execution_framework/run_tws_paper.py --check --symbols BTC,MES,ZN"
echo
echo "  Dry-run execution intent:"
echo "    $PYTHON_BIN $TMP_BASE/execution_framework/run_tws_paper.py --dry-run --symbols MES"
