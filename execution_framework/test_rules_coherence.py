"""Coherence tests for DEFAULT_RULES: every wired product must have a valid
lifecycle cap, positive tick, sane cooldown/wait, and a coherent session.

Regression covered: the COMMODITY hard cap existed in position_lifecycle but
no COMMODITY product (CL/WTI, model #4) had an entry rule in DEFAULT_RULES,
so one of the five models had no live wiring.
"""
from __future__ import annotations

from event_right_side_engine import DEFAULT_RULES
from ibkr_contract_resolver import FUT_SPECS, CRYPTO_SPECS, FX_SPECS
from enabled_symbols import ENABLED_SYMBOLS
from position_lifecycle import PROVISIONAL_PAPER_CAP_SECONDS


def test_commodity_product_is_wired():
    assert "CL" in DEFAULT_RULES
    rule = DEFAULT_RULES["CL"]
    assert rule.asset_class == "COMMODITY"
    assert rule.tick_size == 0.01          # NYMEX WTI: $0.01/bbl, 1000 bbl
    assert rule.session_start_local is not None
    assert rule.session_end_local is not None


def test_every_rule_has_lifecycle_cap():
    for sym, rule in DEFAULT_RULES.items():
        assert rule.asset_class in PROVISIONAL_PAPER_CAP_SECONDS, (
            f"{sym}: asset_class {rule.asset_class} has no hard cap")


def test_rule_parameters_are_sane():
    for sym, rule in DEFAULT_RULES.items():
        assert rule.tick_size > 0, sym
        assert 0 < rule.min_cooldown_minutes < rule.max_wait_minutes, sym
        assert rule.max_spread_ticks > 0 and rule.max_slippage_ticks > 0, sym
        has_local = (rule.session_start_local is not None
                     or rule.session_end_local is not None)
        has_utc = (rule.session_start_utc is not None
                   or rule.session_end_utc is not None)
        # session 要么完整配置（本地或 UTC），要么完全缺省（24h），不许半配
        if has_local:
            assert rule.session_start_local is not None
            assert rule.session_end_local is not None
            assert rule.session_start_local != rule.session_end_local, sym
        if has_utc:
            assert rule.session_start_utc is not None
            assert rule.session_end_utc is not None
            assert rule.session_start_utc != rule.session_end_utc, sym


def test_all_five_model_families_present():
    families = {rule.asset_class for rule in DEFAULT_RULES.values()}
    for expected in ("FX", "INDEX", "TREASURY", "RATES",
                     "CRYPTO_FUT", "CRYPTO_SPOT", "COMMODITY"):
        assert expected in families, f"missing family {expected}"


def test_enabled_symbols_have_resolver_specs():
    """每个启用且有规则的品种，在合约解析器里必须有规格表条目。

    回归覆盖：CL 有 DEFAULT_RULES 且已启用，但 FUT_SPECS 缺条目，
    连续运行器报"未知品种: CL"跳过该品种——五模型实际只剩四路。
    """
    for sym in ENABLED_SYMBOLS:
        if sym not in DEFAULT_RULES:
            continue  # 无规则的品种（如现货 FX/加密走软止损通道）不经过规则解析
        spec_tables = {**FUT_SPECS, **CRYPTO_SPECS, **FX_SPECS}
        assert sym in spec_tables, f"{sym}: enabled + ruled but no resolver spec"


def main() -> int:
    test_commodity_product_is_wired()
    test_every_rule_has_lifecycle_cap()
    test_rule_parameters_are_sane()
    test_all_five_model_families_present()
    test_enabled_symbols_have_resolver_specs()
    print("✓ DEFAULT_RULES coherence (incl. CL wiring + resolver specs) passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
