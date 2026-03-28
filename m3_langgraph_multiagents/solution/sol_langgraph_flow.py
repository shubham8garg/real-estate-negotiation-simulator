"""
MODULE 3 — EXERCISES 1 & 2 SOLUTION: LangGraph Flow with Deadlock Detection
and Convergence Auto-Accept
=============================================================================
This is langgraph_flow.py with BOTH M3 exercise solutions applied.
The original langgraph_flow.py is NOT modified.

EXERCISE 1 SOLUTION — Stale-Price Deadlock Detection in route_after_seller():
  If the last 4 history entries all have the same price, neither party is moving.
  route_after_seller() detects this and returns "end" (deadlocked).
  Without this fix: negotiation loops forever if agents keep repeating prices.

EXERCISE 2 SOLUTION — Convergence Auto-Accept at Midpoint in seller_node():
  If the gap between buyer's offer and seller's counter is ≤ 2%,
  seller automatically accepts at the midpoint instead of counter-offering.
  Without this fix: agents never close even when they're close.

SEARCH FOR "EXERCISE 1 SOLUTION" and "EXERCISE 2 SOLUTION" to find the changes.

HOW TO RUN:
  python m3_langgraph_multiagents/solution/sol_run.py
  python m3_langgraph_multiagents/solution/sol_run.py --fast
  python m3_langgraph_multiagents/solution/sol_run.py --rounds 3
"""

import asyncio
import operator
import time
from typing import Annotated, Literal, Optional, TypedDict

from langgraph.graph import StateGraph, END

from m3_langgraph_multiagents.buyer_simple import BuyerAgent
from m3_langgraph_multiagents.seller_simple import SellerAgent
from m3_langgraph_multiagents.negotiation_types import (
    NegotiationStatus,
    create_acceptance,
)


# ─── Turn Display Helpers ─────────────────────────────────────────────────────

def _turn_header(agent: str, round_num: int, width: int = 65) -> None:
    icon = "🏠 BUYER" if agent == "buyer" else "🏡 SELLER"
    label = f"  Round {round_num} — {icon}  "
    bar = "═" * ((width - len(label)) // 2)
    print(f"\n╔{bar}{label}{bar}╗")


def _turn_box(speaker: str, price: Optional[float], msg_type: str, message: str,
              mcp_calls: list[str] = None, reasoning: str = None) -> None:
    width = 63
    price_str = f"  💰 Price:    ${price:,.0f}" if price else ""
    print(f"  ┌─ {speaker} ({'offer' if speaker == 'Buyer' else 'counter'}) " + "─" * (width - len(speaker) - 14))
    print(f"  │  Type:     {msg_type}")
    if price_str:
        print(f"  │{price_str}")
    if mcp_calls:
        print(f"  │  MCP:      {', '.join(mcp_calls)}")
    words = message.split()
    lines, current = [], []
    for word in words:
        if sum(len(w) + 1 for w in current) + len(word) > 55:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    for i, line in enumerate(lines[:4]):
        prefix = "  │  Message: " if i == 0 else "  │           "
        print(f"{prefix}{line}")
    if reasoning:
        short_reasoning = reasoning[:70] + ("..." if len(reasoning) > 70 else "")
        print(f"  │  Reasoning:{short_reasoning}")
    print(f"  └" + "─" * width)


def _wait_step(state: dict) -> None:
    if state.get("step_mode", False):
        input("  [ENTER: next turn →] ")
    else:
        time.sleep(0.1)


def _negotiation_banner(state: dict) -> None:
    width = 65
    print("\n" + "╔" + "═" * (width - 2) + "╗")
    title = "LangGraph Negotiation — With Deadlock Detection + Convergence"
    pad = (width - 2 - len(title)) // 2
    print("║" + " " * pad + title + " " * (width - 2 - pad - len(title)) + "║")
    print("╚" + "═" * (width - 2) + "╝")
    print(f"""
  Property:      {state.get('property_address', '742 Evergreen Terrace')}
  Listed at:     ${state.get('listing_price', 485_000):,.0f}
  Buyer budget:  ${state.get('buyer_budget', 460_000):,.0f}  (hard ceiling)
  Seller floor:  ${state.get('seller_minimum', 445_000):,.0f}  (mortgage payoff)
  Max rounds:    {state.get('max_rounds', 5)}

  Solutions active:
    Ex1: Stale-price deadlock detection (route_after_seller)
    Ex2: Convergence auto-accept at midpoint (seller_node)
""")


# ─── Shared State ─────────────────────────────────────────────────────────────

class NegotiationState(TypedDict):
    """Identical to langgraph_flow.py — shared state for the LangGraph workflow."""

    session_id: str
    property_address: str
    listing_price: float

    buyer_budget: float
    seller_minimum: float
    max_rounds: int

    buyer_current_offer: float
    seller_current_counter: float

    round_number: int

    status: NegotiationStatus
    agreed_price: Optional[float]

    last_buyer_message: Optional[dict]
    last_seller_message: Optional[dict]

    history: Annotated[list[dict], operator.add]

    _buyer_agent_ref: Optional[object]
    _seller_agent_ref: Optional[object]

    step_mode: bool


def initial_state(
    session_id: str = "neg_sol_001",
    property_address: str = "742 Evergreen Terrace, Austin, TX 78701",
    listing_price: float = 485_000,
    buyer_budget: float = 460_000,
    seller_minimum: float = 445_000,
    max_rounds: int = 5,
    step_mode: bool = False,
) -> dict:
    return {
        "session_id": session_id,
        "property_address": property_address,
        "listing_price": listing_price,
        "buyer_budget": buyer_budget,
        "seller_minimum": seller_minimum,
        "max_rounds": max_rounds,
        "buyer_current_offer": 0.0,
        "seller_current_counter": listing_price,
        "round_number": 0,
        "status": "negotiating",
        "agreed_price": None,
        "last_buyer_message": None,
        "last_seller_message": None,
        "history": [],
        "_buyer_agent_ref": None,
        "_seller_agent_ref": None,
        "step_mode": step_mode,
    }


# ─── Nodes ────────────────────────────────────────────────────────────────────

async def initialize_agents_node(state: dict) -> dict:
    session_id = state["session_id"]

    _negotiation_banner(state)

    print("  [Graph] INIT NODE: Creating BuyerAgent and SellerAgent...")
    print("  [Graph] Both agents will connect to MCP servers on demand.")
    print("  [Graph] This node runs ONCE — agents are reused across all rounds.")
    if state.get("step_mode"):
        input("\n  [ENTER: start negotiation →] ")

    buyer_agent = BuyerAgent(session_id=session_id)
    seller_agent = SellerAgent(session_id=session_id)

    print("  [Graph] Agents initialized. Graph will now route: init → buyer → seller → ...")

    return {
        "_buyer_agent_ref": buyer_agent,
        "_seller_agent_ref": seller_agent,
    }


async def buyer_node(state: dict) -> dict:
    """Buyer agent node — identical to langgraph_flow.py."""
    buyer_agent: BuyerAgent = state["_buyer_agent_ref"]
    round_number = state["round_number"]
    last_seller_msg_dict = state.get("last_seller_message")
    this_round = round_number + 1

    _turn_header("buyer", this_round)
    print(f"  [Graph] BUYER NODE — LangGraph routed here from {'init' if last_seller_msg_dict is None else 'seller'}")
    print(f"  [Graph] Buyer agent will call MCP tools, then GPT-4o decides the offer")

    try:
        if last_seller_msg_dict is None:
            buyer_message = await buyer_agent.make_initial_offer()
        else:
            buyer_message = await buyer_agent.respond_to_counter(last_seller_msg_dict)

    except Exception as e:
        print(f"  [Graph] ERROR in buyer agent: {e}")
        return {
            "status": "error",
            "history": [{"round": this_round, "agent": "buyer", "error": str(e)}],
        }

    new_status = state["status"]
    if buyer_message["message_type"] == "WITHDRAW":
        new_status = "buyer_walked"
    elif buyer_message["message_type"] == "ACCEPT":
        new_status = "agreed"

    mcp_calls = ["get_market_price", "calculate_discount"] if this_round == 1 else ["calculate_discount"]
    _turn_box(
        speaker="Buyer",
        price=buyer_message.get("price"),
        msg_type=buyer_message["message_type"],
        message=buyer_message.get("message", ""),
        mcp_calls=mcp_calls,
    )

    route = "END (walk-away)" if new_status == "buyer_walked" else \
            "END (accepted)" if new_status == "agreed" else \
            "→ seller node"
    print(f"\n  [Graph] route_after_buyer() → {route}")
    _wait_step(state)

    history_entry = {
        "round": buyer_message["round"],
        "agent": "buyer",
        "message_type": buyer_message["message_type"],
        "price": buyer_message.get("price"),
        "message": buyer_message.get("message", "")[:200],
    }

    return {
        "buyer_current_offer": buyer_message.get("price") or state["buyer_current_offer"],
        "round_number": buyer_message["round"],
        "status": new_status,
        "agreed_price": buyer_message.get("price") if new_status == "agreed" else state.get("agreed_price"),
        "last_buyer_message": buyer_message,
        "history": [history_entry],
    }


async def seller_node(state: dict) -> dict:
    """
    Seller agent node — with EXERCISE 2 SOLUTION: convergence auto-accept.

    EXERCISE 2 SOLUTION:
    Before calling the LLM, check if buyer and seller positions are within 2%.
    If gap <= 2%, auto-accept at the midpoint instead of counter-offering.
    This breaks the "so close but never closing" pattern.
    """
    seller_agent: SellerAgent = state["_seller_agent_ref"]
    round_number = state["round_number"]
    last_buyer_msg_dict = state.get("last_buyer_message")

    _turn_header("seller", round_number)
    print(f"  [Graph] SELLER NODE — LangGraph routed here from buyer node")
    print(f"  [Graph] Seller connects to BOTH MCP servers (pricing + inventory)")
    print(f"  [Graph] Seller's floor price is seller-confidential — buyer can't see it")

    if last_buyer_msg_dict is None:
        print("  [Graph] WARN: No buyer message to respond to")
        return {"status": "error"}

    # ── EXERCISE 2 SOLUTION: Convergence auto-accept at midpoint ────────────
    buyer_price = last_buyer_msg_dict.get("price") or 0.0
    seller_counter = state.get("seller_current_counter") or state.get("listing_price", 485_000)

    if buyer_price > 0 and seller_counter > 0:
        gap_pct = abs(seller_counter - buyer_price) / seller_counter
        if gap_pct <= 0.02:  # within 2% — converge at midpoint
            midpoint = int((buyer_price + seller_counter) / 2)
            print(f"  [Graph] EXERCISE 2: Gap is {gap_pct*100:.1f}% (≤2%) → auto-accept at midpoint ${midpoint:,}")

            acceptance_msg = create_acceptance(
                session_id=state["session_id"],
                round_num=round_number,
                from_agent="seller",
                agreed_price=midpoint,
                message=(
                    f"After careful consideration, I'm accepting at ${midpoint:,} — "
                    f"the midpoint between your offer of ${buyer_price:,.0f} and "
                    f"my position of ${seller_counter:,.0f}. We're too close not to close."
                ),
                in_reply_to=last_buyer_msg_dict.get("message_id"),
            )

            _turn_box(
                speaker="Seller",
                price=midpoint,
                msg_type="ACCEPT (convergence)",
                message=acceptance_msg.get("message", ""),
            )
            print(f"\n  [Graph] route_after_seller() → END (deal via convergence!)")
            _wait_step(state)

            history_entry = {
                "round": round_number,
                "agent": "seller",
                "message_type": "ACCEPT",
                "price": midpoint,
                "message": acceptance_msg.get("message", "")[:200],
                "convergence": True,
            }
            return {
                "seller_current_counter": midpoint,
                "status": "agreed",
                "agreed_price": midpoint,
                "last_seller_message": acceptance_msg,
                "history": [history_entry],
            }
    # ── End Exercise 2 Solution ──────────────────────────────────────────────

    try:
        seller_message = await seller_agent.respond_to_offer(last_buyer_msg_dict)

    except Exception as e:
        print(f"  [Graph] ERROR in seller agent: {e}")
        return {
            "status": "error",
            "history": [{"round": round_number, "agent": "seller", "error": str(e)}],
        }

    new_status = state["status"]
    agreed_price = state.get("agreed_price")

    if seller_message["message_type"] == "ACCEPT":
        new_status = "agreed"
        agreed_price = last_buyer_msg_dict.get("price")
    elif seller_message["message_type"] == "REJECT":
        new_status = "seller_rejected"

    if round_number >= state["max_rounds"] and new_status == "negotiating":
        new_status = "deadlocked"

    mcp_calls = ["get_market_price", "get_inventory_level", "get_minimum_acceptable_price"]
    _turn_box(
        speaker="Seller",
        price=seller_message.get("price"),
        msg_type=seller_message["message_type"],
        message=seller_message.get("message", ""),
        mcp_calls=mcp_calls,
    )

    route = "END (deal!)" if new_status == "agreed" else \
            "END (rejected)" if new_status in ("seller_rejected", "deadlocked") else \
            "→ buyer node (loop)"
    print(f"\n  [Graph] route_after_seller() → {route}")
    _wait_step(state)

    history_entry = {
        "round": seller_message["round"],
        "agent": "seller",
        "message_type": seller_message["message_type"],
        "price": seller_message.get("price"),
        "message": seller_message.get("message", "")[:200],
    }

    return {
        "seller_current_counter": seller_message.get("price") or state["seller_current_counter"],
        "status": new_status,
        "agreed_price": agreed_price,
        "last_seller_message": seller_message,
        "history": [history_entry],
    }


# ─── Routing Functions ────────────────────────────────────────────────────────

def route_after_buyer(state: dict) -> Literal["to_seller", "end"]:
    """Identical to langgraph_flow.py — no changes needed for M3 exercises."""
    status = state.get("status", "negotiating")

    if status in ("buyer_walked", "agreed", "error"):
        return "end"

    return "to_seller"


def route_after_seller(state: dict) -> Literal["continue", "end"]:
    """
    EXERCISE 1 SOLUTION: Stale-price deadlock detection added here.

    Original behavior: route to "continue" if status == "negotiating" and
    round_number < max_rounds. Route to "end" for all terminal states.

    EXERCISE 1 ADDITION:
    Before returning "continue", check if the last 4 history entries all
    have the same price. If so, no one is moving — route to "end" (deadlocked).
    """
    status = state.get("status", "negotiating")

    if status != "negotiating":
        return "end"

    round_number = state.get("round_number", 0)
    max_rounds = state.get("max_rounds", 5)

    if round_number >= max_rounds:
        return "end"

    # ── EXERCISE 1 SOLUTION: Stale-price deadlock detection ─────────────────
    history = state.get("history", [])
    if len(history) >= 4:
        recent_prices = [
            h.get("price")
            for h in history[-4:]
            if h.get("price") is not None
        ]
        if len(recent_prices) >= 4 and len(set(recent_prices)) == 1:
            # All 4 recent messages repeat the same price — deadlocked.
            print(f"  [Graph] EXERCISE 1: Stale-price deadlock detected!")
            print(f"  [Graph] Last 4 prices: {recent_prices} — all the same.")
            print(f"  [Graph] Routing to END (deadlocked).")
            return "end"
    # ── End Exercise 1 Solution ──────────────────────────────────────────────

    return "continue"


# ─── Graph Assembly ───────────────────────────────────────────────────────────

def create_negotiation_graph() -> StateGraph:
    """Build and compile the LangGraph negotiation workflow — with both solutions."""
    workflow = StateGraph(NegotiationState)

    workflow.add_node("init", initialize_agents_node)
    workflow.add_node("buyer", buyer_node)
    workflow.add_node("seller", seller_node)

    workflow.set_entry_point("init")

    workflow.add_edge("init", "buyer")

    workflow.add_conditional_edges(
        "buyer",
        route_after_buyer,
        {
            "to_seller": "seller",
            "end": END,
        }
    )

    workflow.add_conditional_edges(
        "seller",
        route_after_seller,
        {
            "continue": "buyer",
            "end": END,
        }
    )

    graph = workflow.compile()
    return graph


# ─── Results Display ──────────────────────────────────────────────────────────

def print_negotiation_results(final_state: dict) -> None:
    width = 65
    print("\n" + "╔" + "═" * (width - 2) + "╗")
    title = "NEGOTIATION COMPLETE — Solution: Deadlock Detection + Convergence"
    pad = (width - 2 - len(title)) // 2
    print("║" + " " * pad + title + " " * (width - 2 - pad - len(title)) + "║")
    print("╚" + "═" * (width - 2) + "╝")

    status = final_state.get("status", "unknown")
    agreed_price = final_state.get("agreed_price")
    listing_price = final_state.get("listing_price", 485_000)
    history = final_state.get("history", [])
    rounds_used = final_state.get("round_number", 0)

    outcome_map = {
        "agreed":          "  DEAL REACHED",
        "buyer_walked":    "  BUYER WALKED AWAY",
        "deadlocked":      "  DEADLOCK — stale-price detection triggered",
        "seller_rejected": "  SELLER REJECTED",
        "error":           "  ERROR",
    }
    print(f"\n  Outcome:    {outcome_map.get(status, status.upper())}")
    print(f"  Rounds:     {rounds_used} of {final_state.get('max_rounds', 5)} used")
    print(f"  Messages:   {len(history)}")

    if agreed_price:
        savings = listing_price - agreed_price
        savings_pct = savings / listing_price * 100
        print(f"\n  Listed at:  ${listing_price:,.0f}")
        print(f"  Agreed at:  ${agreed_price:,.0f}")
        print(f"  Buyer saved: ${savings:,.0f}  ({savings_pct:.1f}% below listing)")

    if history:
        print(f"\n  {'Rnd':>3}  {'Agent':>8}  {'Type':>16}  {'Price':>12}")
        print("  " + "─" * 46)
        for entry in history:
            price_str = f"${entry.get('price', 0):,.0f}" if entry.get("price") else "—"
            print(
                f"  {entry.get('round', 0):>3}  "
                f"{entry.get('agent', ''):>8}  "
                f"{entry.get('message_type', ''):>16}  "
                f"{price_str:>12}"
                + (" ← convergence" if entry.get("convergence") else "")
            )

    print("\n" + "╔" + "═" * (width - 2) + "╗")
    print("║  Solutions demonstrated:                                      ║")
    print("║    Ex1: route_after_seller — stale-price deadlock detection   ║")
    print("║    Ex2: seller_node — convergence auto-accept at midpoint     ║")
    print("╚" + "═" * (width - 2) + "╝")


# ─── Standalone Runner ────────────────────────────────────────────────────────

async def run_negotiation(
    session_id: str = "neg_sol_001",
    property_address: str = "742 Evergreen Terrace, Austin, TX 78701",
    listing_price: float = 485_000,
    buyer_budget: float = 460_000,
    seller_minimum: float = 445_000,
    max_rounds: int = 5,
    step_mode: bool = False,
) -> dict:
    """Run a complete negotiation with both exercise solutions applied."""
    graph = create_negotiation_graph()

    state = initial_state(
        session_id=session_id,
        property_address=property_address,
        listing_price=listing_price,
        buyer_budget=buyer_budget,
        seller_minimum=seller_minimum,
        max_rounds=max_rounds,
        step_mode=step_mode,
    )

    final_state = await graph.ainvoke(state)
    print_negotiation_results(final_state)
    return final_state
