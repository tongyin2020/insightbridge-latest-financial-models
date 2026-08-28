"""Offline tests for broker-backed hard-risk account inputs."""
from __future__ import annotations

from types import SimpleNamespace

from run_tws_continuous import _account_risk_snapshot


class _Journal:
    def current_consecutive_losses(self):
        return 2


class _IB:
    def accountValues(self):
        return [
            SimpleNamespace(account="DU1", tag="NetLiquidation",
                            currency="BASE", value="50000"),
            SimpleNamespace(account="DU1", tag="DailyPnL",
                            currency="BASE", value="-500"),
        ]

    def positions(self):
        contract = SimpleNamespace(localSymbol="MNQU6", symbol="MNQ")
        return [SimpleNamespace(contract=contract, position=2)]


def main() -> int:
    sess = SimpleNamespace(ib=_IB())
    snapshot = _account_risk_snapshot(sess, "DU1", _Journal(), feed_lag_ms=42)
    assert snapshot is not None
    assert snapshot["equity"] == 50000
    assert snapshot["daily_pnl_pct"] == -0.01
    assert snapshot["consec_losses"] == 2
    assert snapshot["active_position"] == 1
    assert snapshot["feed_lag_ms"] == 42

    sess.ib.accountValues = lambda: []
    assert _account_risk_snapshot(sess, "DU1", _Journal()) is None
    print("✓ broker-backed account risk snapshot and fail-closed semantics passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
