"""
Google ADK A2A Demo
===================
Focused demonstration of agent-to-agent (A2A) messaging using Google ADK agents.

WHAT THIS SHOWS:
  - Buyer and seller are both Google ADK LlmAgents (Gemini)
  - Orchestrator mediates messages between agents each round
  - Messages remain structured via shared A2AMessage schema
  - Round-by-round transcript of the ADK-mediated A2A exchange

RUN:
  python m4_adk_multiagents/a2a_adk_demo.py --rounds 3

REQUIRES:
  - GOOGLE_API_KEY environment variable
"""

import argparse
import asyncio
import os
import sys
import uuid

from m4_adk_multiagents.buyer_adk import BuyerAgentADK
from m4_adk_multiagents.seller_adk import SellerAgentADK
from m4_adk_multiagents.messaging_adk import NegotiationSession


def _check_environment() -> None:
    if not os.environ.get("GOOGLE_API_KEY"):
        print("Missing GOOGLE_API_KEY.")
        print("Set it before running this demo, e.g. in .env or shell environment.")
        raise SystemExit(1)


def _print_config(session_id: str, rounds: int) -> None:
    print("\n" + "═" * 68)
    print("GOOGLE ADK A2A DEMO")
    print("═" * 68)
    print("Architecture: Buyer ADK Agent ↔ Orchestrator ↔ Seller ADK Agent")
    print("Transport: ADK runner/session mediation (not m3 in-memory bus)")
    print(f"Session ID: {session_id}")
    print(f"Max rounds: {rounds}")
    print("Model: Gemini 2.0 Flash")
    print("═" * 68)


def _print_message(prefix: str, message) -> None:
    print(f"\n[{prefix}] {message.to_summary()}")
    if message.payload.message:
        print(f"  ↳ {message.payload.message[:200]}")


async def run_demo(max_rounds: int = 3, session_id: str | None = None) -> dict:
    session_id = session_id or f"adk_a2a_{uuid.uuid4().hex[:8]}"

    session = NegotiationSession(
        session_id=session_id,
        property_address="742 Evergreen Terrace, Austin, TX 78701",
        listing_price=485_000,
        buyer_budget=460_000,
        seller_minimum=445_000,
        max_rounds=max_rounds,
    )

    _print_config(session_id, max_rounds)

    async with BuyerAgentADK(session_id=f"{session_id}_buyer") as buyer:
        async with SellerAgentADK(session_id=f"{session_id}_seller") as seller:
            print("\n[Orchestrator] ADK agents initialized. Starting A2A exchange...")

            for round_num in range(1, max_rounds + 1):
                if round_num == 1:
                    buyer_message = await buyer.make_initial_offer()
                else:
                    last_seller_message = session.message_history[-1]
                    buyer_message = await buyer.respond_to_counter(last_seller_message)

                session.record_message(buyer_message)
                _print_message("A2A BUYER→SELLER", buyer_message)

                if session.is_concluded():
                    break

                seller_message = await seller.respond_to_offer(buyer_message)
                session.record_message(seller_message)
                _print_message("A2A SELLER→BUYER", seller_message)

                if session.is_concluded():
                    break

            if not session.is_concluded():
                session.status = "deadlocked"

    print("\n" + "─" * 68)
    print(f"Final status: {session.status}")
    if session.agreed_price:
        print(f"Agreed price: ${session.agreed_price:,.0f}")
    print(f"Rounds used: {session.current_round}/{session.max_rounds}")
    print(f"Messages exchanged: {len(session.message_history)}")
    print("─" * 68)

    return {
        "status": session.status,
        "agreed_price": session.agreed_price,
        "rounds_used": session.current_round,
        "messages": len(session.message_history),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Google ADK A2A demo")
    parser.add_argument("--rounds", type=int, default=3, help="Maximum negotiation rounds")
    parser.add_argument("--session", type=str, default=None, help="Optional session ID")
    args = parser.parse_args()

    _check_environment()

    try:
        await run_demo(max_rounds=args.rounds, session_id=args.session)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        raise SystemExit(0)
    except Exception as error:
        print(f"\nADK A2A demo failed: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    if sys.version_info < (3, 10):
        print("Python 3.10+ is required.")
        raise SystemExit(1)

    asyncio.run(main())
