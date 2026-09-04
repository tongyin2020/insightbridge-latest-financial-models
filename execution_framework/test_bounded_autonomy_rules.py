"""Offline tests for persistent bounded-autonomy controls."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bounded_autonomy_rules import (
    BLOCKED_BY_UPSTREAM,
    DISABLED_REQUIRES_MANUAL_RESET,
    FATAL,
    RETRYABLE,
    BoundedAutonomyController,
    PreTradeLimits,
)


def test_throttle_survives_restart_and_requires_manual_reset(tmp_path: Path):
    db = tmp_path / "bounded.db"
    audit = tmp_path / "audit.jsonl"
    scope = ("DU-PAPER", "CPI", "right-side")
    first = BoundedAutonomyController(
        str(db), live_mode=True, throttle_limits={scope: 1},
        audit_log_path=str(audit), algo_version="v-test")
    decision = first.authorize_autonomous_action(*scope, event_id="evt-1")
    assert decision.allowed
    assert decision.status == DISABLED_REQUIRES_MANUAL_RESET

    restarted = BoundedAutonomyController(
        str(db), live_mode=True, throttle_limits={scope: 1},
        audit_log_path=str(audit), algo_version="v-test")
    blocked = restarted.authorize_autonomous_action(*scope, event_id="evt-2")
    assert not blocked.allowed
    assert blocked.status == DISABLED_REQUIRES_MANUAL_RESET
    assert restarted.manual_reset(
        "ops-17", "reviewed persisted throttle",
        account_id=scope[0], event_family=scope[1], strategy_path=scope[2],
        approved_by="risk-4")
    assert restarted.autonomy_status(*scope)["status"] == "ENABLED"
    assert restarted.authorize_autonomous_action(*scope).allowed

    rows = [json.loads(line) for line in audit.read_text().splitlines()]
    reset = [row for row in rows
             if row["change_nature"] == "MANUAL_AUTONOMY_RESET"][0]
    assert reset["algo_version"] == "v-test"
    assert reset["operator_id"] == "ops-17"
    assert reset["changed_by"] == "ops-17"
    assert reset["approved_by"] == "risk-4"


def test_missing_limits_and_unknown_upstream_fail_closed(tmp_path: Path):
    controller = BoundedAutonomyController(
        str(tmp_path / "bounded.db"), live_mode=True,
        throttle_limit=2, account_id="A", event_family="E", strategy_path="S")
    missing = controller.check_pre_trade(
        account_id="A", venue="CME", product_group="INDEX",
        price=100, reference_price=100, quantity=1)
    assert not missing.allowed
    assert missing.reason == "missing_pre_trade_limits"
    unknown = controller.query_upstream("CME", "INDEX")
    assert not unknown.allowed
    assert unknown.status == "UNKNOWN"


def test_pretrade_upstream_submission_count_kill_and_rejections(tmp_path: Path):
    controller = BoundedAutonomyController(
        str(tmp_path / "bounded.db"),
        live_mode=True,
        pre_trade_limits=PreTradeLimits(
            max_price_deviation_pct=0.02,
            max_order_value=10_000,
            max_quantity=3,
            max_messages=1,
        ),
        rejection_mapping={"TEMP": RETRYABLE},
    )
    controller.set_upstream_blocked(
        "CME", "INDEX", "venue notice", operator_id="feed-gateway")
    blocked = controller.query_upstream("CME", "INDEX")
    assert not blocked.allowed and blocked.status == BLOCKED_BY_UPSTREAM
    with pytest.raises(ValueError):
        controller.clear_upstream("CME", "INDEX", "", "no operator")
    controller.clear_upstream(
        "CME", "INDEX", "ops-1", "venue notice resolved")
    allowed = controller.check_pre_trade(
        account_id="A", venue="CME", product_group="INDEX",
        price=101, reference_price=100, quantity=2, multiplier=10)
    assert allowed.allowed
    assert controller.record_submitted_order("A", "CME", "INDEX") == 1
    message_block = controller.check_pre_trade(
        account_id="A", venue="CME", product_group="INDEX",
        price=101, reference_price=100, quantity=2, multiplier=10)
    assert not message_block.allowed
    assert message_block.reason == "max_messages_exceeded"

    controller.engage_kill("A", "local safety test")
    intents = controller.generate_cancel_intents(
        "A", [{"order_id": "12", "symbol": "MNQ"}])
    assert intents[0]["broker_action_performed"] is False
    assert controller.classify_rejection("TEMP") == RETRYABLE
    assert controller.classify_rejection("NEVER_SEEN") == FATAL


def test_trusted_upstream_sources_whitelist_enforced(tmp_path: Path):
    audit = tmp_path / "audit.jsonl"
    controller = BoundedAutonomyController(
        str(tmp_path / "bounded.db"), live_mode=True,
        trusted_upstream_sources={"venue-feed-gateway", "ops-console"},
        audit_log_path=str(audit))
    # Missing source is fail-closed when a whitelist is configured.
    with pytest.raises(ValueError):
        controller.set_upstream_blocked(
            "CME", "INDEX", "venue notice", operator_id="feed")
    # Untrusted source is rejected.
    with pytest.raises(ValueError):
        controller.set_upstream_blocked(
            "CME", "INDEX", "venue notice", operator_id="feed",
            source="unknown-service")
    # Trusted source succeeds and is written to audit.
    controller.set_upstream_blocked(
        "CME", "INDEX", "venue notice", operator_id="feed",
        source="venue-feed-gateway")
    lines = [json.loads(l) for l in audit.read_text().splitlines()]
    assert any(row["details"].get("source") == "venue-feed-gateway"
               for row in lines)
    controller.clear_upstream(
        "CME", "INDEX", "ops-1", "resolved", source="ops-console")


def test_default_behavior_when_whitelist_not_set(tmp_path: Path):
    # Absent whitelist -> old behavior: source omitted is accepted.
    controller = BoundedAutonomyController(
        str(tmp_path / "bounded.db"), live_mode=True)
    controller.set_upstream_blocked(
        "CME", "INDEX", "venue notice", operator_id="feed")
    status = controller.query_upstream("CME", "INDEX")
    assert status.status == BLOCKED_BY_UPSTREAM
