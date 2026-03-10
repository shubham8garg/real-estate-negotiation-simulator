"""
ADK-Native Negotiation Message Types
====================================
Message schema used by Module 4 (Google ADK) without depending on Module 3's
custom A2A implementation.
"""

import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

AgentName = Literal["buyer", "seller"]

MessageType = Literal[
    "OFFER",
    "COUNTER_OFFER",
    "ACCEPT",
    "REJECT",
    "WITHDRAW",
    "INFO",
]

NegotiationStatus = Literal[
    "negotiating",
    "agreed",
    "deadlocked",
    "buyer_walked",
    "seller_rejected",
    "error",
]


class ADKNegotiationPayload(BaseModel):
    price: Optional[float] = None
    conditions: list[str] = Field(default_factory=list)
    closing_timeline_days: Optional[int] = None
    concessions: list[str] = Field(default_factory=list)
    message: str


class ADKNegotiationMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:8]}")
    session_id: str
    from_agent: AgentName
    to_agent: AgentName
    round: int
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    in_reply_to: Optional[str] = None
    message_type: MessageType
    payload: ADKNegotiationPayload

    def is_terminal(self) -> bool:
        return self.message_type in ("ACCEPT", "REJECT", "WITHDRAW")

    def to_summary(self) -> str:
        price_str = f"${self.payload.price:,.0f}" if self.payload.price else "N/A"
        return (
            f"[Round {self.round}] {self.from_agent.upper()} → {self.to_agent.upper()} | "
            f"{self.message_type} @ {price_str}"
        )


def create_offer(
    session_id: str,
    round_num: int,
    price: float,
    message: str,
    conditions: Optional[list[str]] = None,
    closing_days: Optional[int] = None,
    in_reply_to: Optional[str] = None,
) -> ADKNegotiationMessage:
    return ADKNegotiationMessage(
        session_id=session_id,
        from_agent="buyer",
        to_agent="seller",
        round=round_num,
        in_reply_to=in_reply_to,
        message_type="OFFER",
        payload=ADKNegotiationPayload(
            price=price,
            conditions=conditions or ["Contingent on home inspection", "Financing contingency (30 days)"],
            closing_timeline_days=closing_days or 45,
            message=message,
        ),
    )


def create_counter_offer(
    session_id: str,
    round_num: int,
    price: float,
    message: str,
    conditions: Optional[list[str]] = None,
    closing_days: Optional[int] = None,
    in_reply_to: Optional[str] = None,
) -> ADKNegotiationMessage:
    return ADKNegotiationMessage(
        session_id=session_id,
        from_agent="seller",
        to_agent="buyer",
        round=round_num,
        in_reply_to=in_reply_to,
        message_type="COUNTER_OFFER",
        payload=ADKNegotiationPayload(
            price=price,
            conditions=conditions or ["As-is condition", "Standard contingencies"],
            closing_timeline_days=closing_days or 30,
            message=message,
        ),
    )


def create_acceptance(
    session_id: str,
    round_num: int,
    from_agent: AgentName,
    agreed_price: float,
    message: str,
    in_reply_to: Optional[str] = None,
) -> ADKNegotiationMessage:
    to_agent: AgentName = "seller" if from_agent == "buyer" else "buyer"
    return ADKNegotiationMessage(
        session_id=session_id,
        from_agent=from_agent,
        to_agent=to_agent,
        round=round_num,
        in_reply_to=in_reply_to,
        message_type="ACCEPT",
        payload=ADKNegotiationPayload(
            price=agreed_price,
            message=message,
        ),
    )


def create_withdrawal(
    session_id: str,
    round_num: int,
    reason: str,
    in_reply_to: Optional[str] = None,
) -> ADKNegotiationMessage:
    return ADKNegotiationMessage(
        session_id=session_id,
        from_agent="buyer",
        to_agent="seller",
        round=round_num,
        in_reply_to=in_reply_to,
        message_type="WITHDRAW",
        payload=ADKNegotiationPayload(
            message=f"We are withdrawing from this negotiation. {reason}",
        ),
    )
