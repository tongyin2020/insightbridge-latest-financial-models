"""Session-window tests: exchange-local sessions must follow DST, fixed-UTC
sessions must keep working for backward compatibility.

Regression covered: DEFAULT_RULES used to hardcode 13:30-20:00 UTC for MES/MNQ
RTH. In winter (EST) that window drifts to 10:30-17:00 ET, so a CPI release at
8:30 ET (13:30 UTC) would sit exactly on a wrong session boundary.
"""
from __future__ import annotations

from datetime import datetime, time, timezone

from event_right_side_engine import AssetRule, RightSideEventEngine, DEFAULT_RULES


def _in_session(rule: AssetRule, now: datetime) -> bool:
    return RightSideEventEngine._in_session(rule, now)


def test_index_session_follows_new_york_dst():
    mes = DEFAULT_RULES["MES"]
    # 夏季（EDT, UTC-4）：9:30-16:00 ET = 13:30-20:00 UTC
    assert _in_session(mes, datetime(2026, 8, 27, 13, 30, tzinfo=timezone.utc))
    assert _in_session(mes, datetime(2026, 8, 27, 19, 59, tzinfo=timezone.utc))
    assert not _in_session(mes, datetime(2026, 8, 27, 13, 29, tzinfo=timezone.utc))
    assert not _in_session(mes, datetime(2026, 8, 27, 20, 1, tzinfo=timezone.utc))
    # 冬季（EST, UTC-5）：窗口必须整体平移到 14:30-21:00 UTC，
    # 旧写死 UTC 的实现会在这里失效（13:30 UTC = 8:30 ET 盘前被误放行）
    assert _in_session(mes, datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc))
    assert not _in_session(mes, datetime(2026, 1, 15, 13, 30, tzinfo=timezone.utc))
    assert not _in_session(mes, datetime(2026, 1, 15, 21, 1, tzinfo=timezone.utc))


def test_treasury_session_follows_new_york_dst():
    zn = DEFAULT_RULES["ZN"]  # 3:00-16:00 ET
    # 夏季：7:00-20:00 UTC
    assert _in_session(zn, datetime(2026, 8, 27, 7, 0, tzinfo=timezone.utc))
    assert not _in_session(zn, datetime(2026, 8, 27, 6, 59, tzinfo=timezone.utc))
    # 冬季：8:00-21:00 UTC；旧写死 7:00 UTC 会在冬季 2:00 ET 提前放行
    assert _in_session(zn, datetime(2026, 1, 15, 8, 0, tzinfo=timezone.utc))
    assert not _in_session(zn, datetime(2026, 1, 15, 7, 0, tzinfo=timezone.utc))
    # CPI 8:30 ET 事件前后都在时段内（夏 12:30 UTC / 冬 13:30 UTC）
    assert _in_session(zn, datetime(2026, 8, 12, 12, 45, tzinfo=timezone.utc))
    assert _in_session(zn, datetime(2026, 1, 13, 13, 45, tzinfo=timezone.utc))


def test_24h_symbol_always_in_session():
    eurusd = DEFAULT_RULES["EURUSD"]  # FX，无 session 配置
    assert _in_session(eurusd, datetime(2026, 1, 15, 3, 0, tzinfo=timezone.utc))
    assert _in_session(eurusd, datetime(2026, 8, 27, 3, 0, tzinfo=timezone.utc))


def test_legacy_utc_fields_still_honored():
    rule = AssetRule("LEG", "INDEX", 5, 30, tick_size=0.25,
                     session_start_utc=time(13, 30), session_end_utc=time(20, 0))
    assert _in_session(rule, datetime(2026, 1, 15, 14, 0, tzinfo=timezone.utc))
    assert not _in_session(rule, datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc))
    # 本地字段优先于 UTC 字段
    both = AssetRule("BOTH", "INDEX", 5, 30, tick_size=0.25,
                     session_start_utc=time(0, 0), session_end_utc=time(1, 0),
                     session_start_local=time(9, 30), session_end_local=time(16, 0))
    assert _in_session(both, datetime(2026, 8, 27, 13, 30, tzinfo=timezone.utc))
    assert not _in_session(both, datetime(2026, 8, 27, 0, 30, tzinfo=timezone.utc))


def test_cross_midnight_local_window():
    rule = AssetRule("XM", "INDEX", 5, 30, tick_size=0.25,
                     session_start_local=time(22, 0), session_end_local=time(6, 0))
    # 23:00 ET 夏令时 = 次日 03:00 UTC
    assert _in_session(rule, datetime(2026, 8, 27, 3, 0, tzinfo=timezone.utc))
    # 12:00 ET = 16:00 UTC 不在窗口
    assert not _in_session(rule, datetime(2026, 8, 27, 16, 0, tzinfo=timezone.utc))


def test_naive_datetime_rejected_for_local_session():
    try:
        _in_session(DEFAULT_RULES["MES"], datetime(2026, 8, 27, 13, 30))
    except ValueError:
        pass
    else:
        raise AssertionError("naive datetime must be rejected")


def main() -> int:
    test_index_session_follows_new_york_dst()
    test_treasury_session_follows_new_york_dst()
    test_24h_symbol_always_in_session()
    test_legacy_utc_fields_still_honored()
    test_cross_midnight_local_window()
    test_naive_datetime_rejected_for_local_session()
    print("✓ DST-safe exchange-local session windows passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
