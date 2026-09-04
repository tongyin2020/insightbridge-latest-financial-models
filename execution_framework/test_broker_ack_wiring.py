"""Regression tests for broker acknowledgement wiring."""
from __future__ import annotations

import json

import pytest

from ibkr_order_manager import OrderTicket
from right_side_pipeline import RightSidePipeline


class StubOrderManager:
    def __init__(self, ticket: OrderTicket):
        self.ticket = ticket

    def poll_fill(self, client_ref: str) -> OrderTicket:
        assert client_ref == self.ticket.client_ref
        return self.ticket

    def release(self, symbol: str) -> None:
        pass


def make_pipeline(tmp_path, broker_channel: str = "PAPER"):
    pipe = RightSidePipeline(
        ib=None,
        dry_run=True,
        safety_db=str(tmp_path / "safety.db"),
        account_id="DU-PAPER",
        journal_db=None,
        broker_channel=broker_channel,
    )
    event_id = f"broker-ack-{broker_channel}"
    assert pipe.intent_ledger.reserve_event(
        "DU-PAPER", event_id, 2026).accepted
    reservation = pipe.intent_ledger.reserve_intent(
        "DU-PAPER", event_id, 2026, "MNQ", "BUY", "test-ack")
    assert reservation.accepted
    assert pipe.intent_ledger.advance_intent(reservation.intent_id, "SUBMITTED")
    return pipe, reservation.intent_id


def make_ticket(intent_id: str, state: str, broker_status: str | None,
                parent_id: int | None = 1234,
                filled_quantity: float = 0.0) -> OrderTicket:
    return OrderTicket(
        client_ref=intent_id,
        symbol="MNQ",
        action="BUY",
        quantity=1.0,
        limit_price=18000.0,
        stop_loss=17900.0,
        state=state,
        broker_status=broker_status,
        parent_id=parent_id,
        filled_quantity=filled_quantity,
    )


def test_submitted_status_records_paper_ack(tmp_path):
    pipe, intent_id = make_pipeline(tmp_path)
    pipe.om = StubOrderManager(make_ticket(intent_id, "SUBMITTED", "Submitted"))

    assert pipe.confirm_fill("MNQ", intent_id) == "SUBMITTED"
    row = pipe.intent_ledger.get_intent(intent_id)
    payload = json.loads(row["broker_ack_payload"])
    assert row["broker_ack_state"] == "ACKED_PAPER"
    assert payload["source"] == "broker"
    assert payload["channel"] == "PAPER"


def test_pending_submit_is_not_an_ack(tmp_path):
    pipe, intent_id = make_pipeline(tmp_path)
    pipe.om = StubOrderManager(
        make_ticket(intent_id, "SUBMITTED", "PendingSubmit"))

    pipe.confirm_fill("MNQ", intent_id)
    row = pipe.intent_ledger.get_intent(intent_id)
    assert row["broker_ack_state"] == "PENDING_BROKER_ACK"


def test_cancelled_status_records_cancel_ack(tmp_path):
    pipe, intent_id = make_pipeline(tmp_path)
    pipe.om = StubOrderManager(
        make_ticket(intent_id, "CANCELLED", "Cancelled"))

    assert pipe.confirm_fill("MNQ", intent_id) == "CANCELLED"
    row = pipe.intent_ledger.get_intent(intent_id)
    assert row["broker_ack_state"] == "CANCEL_ACKED"


def test_inactive_status_rejects_ack_without_changing_economic_state(tmp_path):
    pipe, intent_id = make_pipeline(tmp_path)
    pipe.om = StubOrderManager(make_ticket(intent_id, "SUBMITTED", "Inactive"))

    pipe.confirm_fill("MNQ", intent_id)
    row = pipe.intent_ledger.get_intent(intent_id)
    assert row["broker_ack_state"] == "REJECTED"
    assert row["state"] == "SUBMITTED"


def test_filled_status_records_live_ack(tmp_path):
    pipe, intent_id = make_pipeline(tmp_path, broker_channel="LIVE")
    pipe.om = StubOrderManager(
        make_ticket(intent_id, "FILLED", "Filled", filled_quantity=1.0))

    assert pipe.confirm_fill("MNQ", intent_id) == "FILLED"
    row = pipe.intent_ledger.get_intent(intent_id)
    assert row["broker_ack_state"] == "ACKED_LIVE"


def test_invalid_broker_channel_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        RightSidePipeline(
            ib=None,
            dry_run=True,
            safety_db=str(tmp_path / "safety.db"),
            account_id="DU-PAPER",
            journal_db=None,
            broker_channel="X",
        )


def test_broker_ack_is_idempotent(tmp_path):
    pipe, intent_id = make_pipeline(tmp_path)
    pipe.om = StubOrderManager(make_ticket(intent_id, "SUBMITTED", "Submitted"))

    pipe.confirm_fill("MNQ", intent_id)
    first = pipe.intent_ledger.get_intent(intent_id)
    pipe.confirm_fill("MNQ", intent_id)
    second = pipe.intent_ledger.get_intent(intent_id)
    assert first["broker_ack_state"] == "ACKED_PAPER"
    assert second["broker_ack_state"] == "ACKED_PAPER"
    assert second["broker_ack_payload"] == first["broker_ack_payload"]


def test_local_ack_payload_can_be_recorded(tmp_path):
    pipe, intent_id = make_pipeline(tmp_path)

    pipe._record_ack(
        intent_id,
        "REJECTED",
        {"source": "local", "reason": "submit_exception", "error": "boom"},
    )
    row = pipe.intent_ledger.get_intent(intent_id)
    payload = json.loads(row["broker_ack_payload"])
    assert row["broker_ack_state"] == "REJECTED"
    assert payload["source"] == "local"
    assert payload["reason"] == "submit_exception"
    assert payload["error"] == "boom"
