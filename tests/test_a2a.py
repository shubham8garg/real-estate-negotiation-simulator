"""
Tests for negotiation message helpers (Module 3).

Validates typed message creation for the pure LangGraph module without any
in-memory A2A bus dependency. No API keys required.

Run: pytest tests/test_a2a.py -v
"""
from m3_langgraph_multiagents.negotiation_types import (
    create_acceptance,
    create_counter_offer,
    create_offer,
    create_withdrawal,
)

SESSION = "test_session_001"


# ─── Message creation helpers ─────────────────────────────────────────────────

def make_offer(round_num: int = 1, price: float = 425_000.0, reply_to=None) -> dict:
    return create_offer(
        session_id=SESSION,
        round_num=round_num,
        price=price,
        message="Test offer",
        in_reply_to=reply_to,
    )


def make_counter(round_num: int = 1, price: float = 477_000.0, reply_to=None) -> dict:
    return create_counter_offer(
        session_id=SESSION,
        round_num=round_num,
        price=price,
        message="Test counter",
        in_reply_to=reply_to,
    )


def make_acceptance(round_num: int = 1, price: float = 451_000.0, from_agent="seller") -> dict:
    return create_acceptance(
        session_id=SESSION,
        round_num=round_num,
        from_agent=from_agent,
        agreed_price=price,
        message="We have a deal.",
    )


# ─── Message schema ───────────────────────────────────────────────────────────

class TestMessageSchema:
    def test_offer_message_fields(self):
        msg = make_offer(price=425_000.0)
        assert msg["from_agent"] == "buyer"
        assert msg["to_agent"] == "seller"
        assert msg["message_type"] == "OFFER"
        assert msg["price"] == 425_000.0
        assert msg["session_id"] == SESSION

    def test_counter_offer_fields(self):
        msg = make_counter(price=477_000.0)
        assert msg["from_agent"] == "seller"
        assert msg["to_agent"] == "buyer"
        assert msg["message_type"] == "COUNTER_OFFER"

    def test_message_id_is_unique(self):
        msg1 = make_offer()
        msg2 = make_offer()
        assert msg1["message_id"] != msg2["message_id"]

    def test_withdrawal_is_terminal(self):
        msg = create_withdrawal(session_id=SESSION, round_num=1, reason="Too expensive.")
        assert msg["message_type"] == "WITHDRAW"
        assert "withdrawing" in msg["message"].lower()

    def test_acceptance_message_fields(self):
        msg = make_acceptance(round_num=2, price=451_000.0, from_agent="seller")
        assert msg["message_type"] == "ACCEPT"
        assert msg["from_agent"] == "seller"
        assert msg["to_agent"] == "buyer"
        assert msg["price"] == 451_000.0

    def test_withdrawal_message_fields(self):
        msg = create_withdrawal(session_id=SESSION, round_num=3, reason="Too expensive.")
        assert msg["message_type"] == "WITHDRAW"
        assert msg["from_agent"] == "buyer"
        assert msg["to_agent"] == "seller"
        assert "withdrawing" in msg["message"].lower()

    def test_reply_chain_field_is_set(self):
        offer = make_offer(round_num=1)
        counter = make_counter(round_num=1, reply_to=offer["message_id"])
        assert counter["in_reply_to"] == offer["message_id"]
