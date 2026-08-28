"""Adaptive polling tests: _needs_fast_poll must switch the runner to the
fast tier whenever an event window, pending order, open position, or active
soft stop exists, and back to the slow tier when nothing is in play.

Regression covered: the main loop used to sleep a fixed 60s every iteration,
so the right-side confirmation window (evidence: information absorbed within
~5 minutes of the event) and hard-cap/soft-stop exits were systematically
late; an always-fast loop would hammer TWS in the idle LEARN state instead.

The runner module has out-of-package dependencies, so the function under
test is extracted from the real source via AST (not copied).
"""
from __future__ import annotations

import ast
from pathlib import Path


def _load_needs_fast_poll():
    src = Path(__file__).with_name("run_tws_continuous.py").read_text()
    tree = ast.parse(src)
    node = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef)
                and n.name == "_needs_fast_poll")
    mod = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(mod)
    ns: dict = {}
    exec(compile(mod, "run_tws_continuous.py", "exec"), ns)
    return ns["_needs_fast_poll"]


needs_fast_poll = _load_needs_fast_poll()


class _StubState:
    def __init__(self, active: bool):
        self.active = active


class _StubPos:
    def __init__(self, state: str):
        self.state = state


class _StubEngine:
    def __init__(self, states=None):
        self.states = states or {}


class _StubOM:
    def __init__(self, pending=None, soft_stops=None):
        self._pending = pending or []
        self.soft_stops = soft_stops or {}

    def pending_tickets(self):
        return list(self._pending)


class _StubLifecycle:
    def __init__(self, positions=None):
        self.positions = positions or {}


class _StubPipe:
    def __init__(self, states=None, pending=None, positions=None, soft_stops=None):
        self.engine = _StubEngine(states)
        self.om = _StubOM(pending, soft_stops)
        self.lifecycle = _StubLifecycle(positions)


def test_idle_is_slow_tier():
    assert needs_fast_poll(_StubPipe()) is False
    # 全部事件已关闭、无订单、无持仓、软止损全部 inactive
    assert needs_fast_poll(_StubPipe(
        states={"MES": _StubState(False), "ZN": _StubState(False)},
        positions={"ref-1": _StubPos("CLOSED")},
        soft_stops={"ref-1": {"active": False}},
    )) is False


def test_active_event_window_is_fast_tier():
    assert needs_fast_poll(_StubPipe(
        states={"MNQ": _StubState(True)})) is True


def test_pending_order_is_fast_tier():
    assert needs_fast_poll(_StubPipe(pending=["ticket-1"])) is True


def test_open_position_is_fast_tier():
    # OPEN / EXIT_SUBMITTED / EXIT_PARTIAL 都要高频盯硬封顶与退出确认
    for state in ("OPEN", "EXIT_SUBMITTED", "EXIT_PARTIAL"):
        assert needs_fast_poll(_StubPipe(
            positions={"ref-9": _StubPos(state)})) is True, state


def test_active_soft_stop_is_fast_tier():
    assert needs_fast_poll(_StubPipe(
        soft_stops={"ref-2": {"active": True}})) is True


def main() -> int:
    test_idle_is_slow_tier()
    test_active_event_window_is_fast_tier()
    test_pending_order_is_fast_tier()
    test_open_position_is_fast_tier()
    test_active_soft_stop_is_fast_tier()
    print("✓ adaptive fast/slow poll tier passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
