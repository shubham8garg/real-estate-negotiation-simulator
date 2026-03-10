from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional, TypedDict

MessageType = Literal["OFFER", "COUNTER_OFFER", "ACCEPT", "REJECT", "WITHDRAW", "INFO"]
NegotiationStatus = Literal["negotiating", "agreed", "deadlocked", "buyer_walked", "seller_rejected", "error"]


class NegotiationMessage(TypedDict):
    message_id: str
    session_id: str
    from_agent: Literal["buyer", "seller"]
    to_agent: Literal["buyer", "seller"]
    round: int
    timestamp: str
    in_reply_to: Optional[str]
    message_type: MessageType
    price: Optional[float]
    conditions: list[str]
    closing_timeline_days: Optional[int]
    message: str


def _base_message(
    session_id: str,
    from_agent: Literal["buyer", "seller"],
    to_agent: Literal["buyer", "seller"],
    round_num: int,
    message_type: MessageType,
    message: str,
    price: Optional[float] = None,
    conditions: Optional[list[str]] = None,
    closing_days: Optional[int] = None,
    in_reply_to: Optional[str] = None,
) -> NegotiationMessage:
    return {
        "message_id": f"msg_{uuid.uuid4().hex[:8]}",
        "session_id": session_id,
        "from_agent": from_agent,
        "to_agent": to_agent,
        "round": round_num,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "in_reply_to": in_reply_to,
        "message_type": message_type,
        "price": price,
        "conditions": conditions or [],
        "closing_timeline_days": closing_days,
        "message": message,
    }


def create_offer(session_id: str, round_num: int, price: float, message: str, in_reply_to: Optional[str] = None) -> NegotiationMessage:
    return _base_message(
        session_id=session_id,
        from_agent="buyer",
        to_agent="seller",
        round_num=round_num,
        message_type="OFFER",
        price=price,
        conditions=["Contingent on home inspection", "Financing contingency (30 days)"],
        closing_days=45,
        message=message,
        in_reply_to=in_reply_to,
    )


def create_counter_offer(session_id: str, round_num: int, price: float, message: str, in_reply_to: Optional[str] = None) -> NegotiationMessage:
    return _base_message(
        session_id=session_id,
        from_agent="seller",
        to_agent="buyer",
        round_num=round_num,
        message_type="COUNTER_OFFER",
        price=price,
        conditions=["As-is condition", "Standard contingencies"],
        closing_days=30,
        message=message,
        in_reply_to=in_reply_to,
    )


def create_acceptance(
    session_id: str,
    round_num: int,
    from_agent: Literal["buyer", "seller"],
    agreed_price: float,
    message: str,
    in_reply_to: Optional[str] = None,
) -> NegotiationMessage:
    to_agent: Literal["buyer", "seller"] = "seller" if from_agent == "buyer" else "buyer"
    return _base_message(
        session_id=session_id,
        from_agent=from_agent,
        to_agent=to_agent,
        round_num=round_num,
        message_type="ACCEPT",
        price=agreed_price,
        message=message,
        in_reply_to=in_reply_to,
    )


def create_withdrawal(session_id: str, round_num: int, reason: str, in_reply_to: Optional[str] = None) -> NegotiationMessage:
    return _base_message(
        session_id=session_id,
        from_agent="buyer",
        to_agent="seller",
        round_num=round_num,
        message_type="WITHDRAW",
        message=f"We are withdrawing from this negotiation. {reason}",
        in_reply_to=in_reply_to,
    )
