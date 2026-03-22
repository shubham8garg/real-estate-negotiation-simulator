"""
LangGraph Negotiation Orchestration
=====================================
Orchestrates the real estate negotiation between buyer and seller agents
using a stateful LangGraph workflow.

LANGGRAPH CONCEPTS DEMONSTRATED:
  1. StateGraph — the main graph with shared typed state
  2. TypedDict state — the single source of truth all nodes share
  3. Annotated reducers — append to history without overwriting
  4. Async nodes — nodes that call async agent functions
  5. Conditional edges — route based on negotiation outcome
  6. Cycles — the negotiation loop (buyer → seller → check → buyer)
  7. Termination guards — max_rounds prevents infinite loops

WORKFLOW TOPOLOGY:
  START
    │
    ▼
  BUYER NODE (makes offer, calls MCP, calls GPT-4o)
    │
    ├── buyer_walked → END
    ├── accepted → END
    │
    ▼
  SELLER NODE (reads offer, calls MCP ×2, calls GPT-4o)
    │
    ├── accepted → END
    ├── rejected → END
    ├── deadlocked → END
    │
    └── continue → BUYER NODE (loop back)

USAGE:
  from m3_langgraph_multiagents.langgraph_flow import create_negotiation_graph, initial_state

  graph = create_negotiation_graph()
  result = await graph.ainvoke(initial_state())
  print(result["status"], result.get("agreed_price"))
"""

import asyncio
import operator
import time
from typing import Annotated, Literal, Optional, TypedDict

from langgraph.graph import StateGraph, END

from m3_langgraph_multiagents.buyer_simple import BuyerAgent
from m3_langgraph_multiagents.seller_simple import SellerAgent
from m3_langgraph_multiagents.negotiation_types import NegotiationStatus


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
    # Wrap message nicely
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
    """Pause between turns if step_mode is active."""
    if state.get("step_mode", False):
        input("  [ENTER: next turn →] ")
    else:
        time.sleep(0.1)


def _negotiation_banner(state: dict) -> None:
    width = 65
    print("\n" + "╔" + "═" * (width - 2) + "╗")
    title = "LangGraph Negotiation — Live Turns"
    pad = (width - 2 - len(title)) // 2
    print("║" + " " * pad + title + " " * (width - 2 - pad - len(title)) + "║")
    print("╚" + "═" * (width - 2) + "╝")
    print(f"""
  Property:      {state.get('property_address', '742 Evergreen Terrace')}
  Listed at:     ${state.get('listing_price', 485_000):,.0f}
  Buyer budget:  ${state.get('buyer_budget', 460_000):,.0f}  (hard ceiling)
  Seller floor:  ${state.get('seller_minimum', 445_000):,.0f}  (mortgage payoff)
  Max rounds:    {state.get('max_rounds', 5)}

  Watch two layers simultaneously:
    AGENT LAYER  — what buyer and seller say + MCP tools they call
    GRAPH LAYER  — which LangGraph node runs + routing decisions
""")


# ─── Shared State ─────────────────────────────────────────────────────────────

class NegotiationState(TypedDict):
    """
    The shared state for the entire LangGraph negotiation workflow.

    LangGraph concept:
    All nodes read from this state and return PARTIAL updates.
    LangGraph merges the updates automatically.

    The `Annotated[list, operator.add]` pattern means:
    - When a node returns {"history": [new_item]}, LangGraph APPENDS
      the new_item to the existing list
    - Without this, the new list would REPLACE the existing one
    - This is critical for accumulating round-by-round history

    DESIGN PRINCIPLES USED HERE:
    1. Immutable inputs (listing_price, buyer_budget, etc.) — set once
    2. Mutable position tracking (current_offer, current_counter)
    3. Status field for routing (determines which edge to take)
    4. Accumulated history (append-only via reducer)
    5. Per-agent LLM context (kept in state for memory across rounds)
    """

    # ── Property context (immutable) ─────────────────────────────────────────
    session_id: str
    property_address: str
    listing_price: float

    # ── Agent constraints (immutable) ─────────────────────────────────────────
    buyer_budget: float
    seller_minimum: float
    max_rounds: int

    # ── Current negotiation positions ─────────────────────────────────────────
    buyer_current_offer: float
    seller_current_counter: float

    # ── Round tracking ────────────────────────────────────────────────────────
    round_number: int

    # ── Negotiation outcome ───────────────────────────────────────────────────
    status: NegotiationStatus
    agreed_price: Optional[float]

    # ── Last negotiation message (for routing) ───────────────────────────────
    # These hold the most recent message from each agent
    # Used to pass information between nodes
    last_buyer_message: Optional[dict]
    last_seller_message: Optional[dict]

    # ── Accumulated history (APPEND-ONLY via reducer) ─────────────────────────
    # Each node returns {"history": [new_entry]} and LangGraph appends it
    # This gives us a complete audit trail of the negotiation
    history: Annotated[list[dict], operator.add]

    # ── Agent-level state ─────────────────────────────────────────────────────
    # These hold references to agent objects across node invocations
    # NOTE: In production, agents would be initialized separately.
    # For this workshop, we store them in state for simplicity.
    # (In a real system, use dependency injection or context variables)
    _buyer_agent_ref: Optional[object]
    _seller_agent_ref: Optional[object]

    # ── Demo control ──────────────────────────────────────────────────────────
    step_mode: bool  # If True, pause and wait for ENTER between turns


def initial_state(
    session_id: str = "neg_001",
    property_address: str = "742 Evergreen Terrace, Austin, TX 78701",
    listing_price: float = 485_000,
    buyer_budget: float = 460_000,
    seller_minimum: float = 445_000,
    max_rounds: int = 5,
    step_mode: bool = False,
) -> dict:
    """
    Create the initial state for a new negotiation.

    LangGraph concept:
    The initial state passed to graph.ainvoke() must include ALL
    required fields, even if they start as empty/None.
    Missing fields cause KeyError in nodes.
    """
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
        "history": [],  # Will be appended to by nodes
        "_buyer_agent_ref": None,
        "_seller_agent_ref": None,
        "step_mode": step_mode,
    }


# ─── Nodes ────────────────────────────────────────────────────────────────────

async def initialize_agents_node(state: dict) -> dict:
    """
    Initialize buyer and seller agents before the negotiation starts.

    LangGraph concept:
    Nodes can do any work — including creating objects, making API calls,
    reading files. This node creates the agent objects once and stores
    references in state so subsequent nodes can reuse them.

    WHY A SEPARATE INIT NODE?
    We could initialize agents in the first buyer/seller node, but that
    would reinitialize them every iteration of the loop. Better to have
    a dedicated initialization node that runs exactly once.
    """
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
    """
    Buyer agent node — makes or updates an offer.

    LangGraph concept:
    This node reads from state, calls the async buyer agent, and returns
    a PARTIAL state update. LangGraph merges this with the existing state.

    Key state updates this node makes:
    - buyer_current_offer: the new offer price
    - round_number: increments
    - status: may change to "buyer_walked"
    - last_buyer_message: the latest buyer message for seller to read
    - history: appends this round's data (via reducer)

    ASYNC NODE:
    LangGraph supports async nodes natively. Since our agents make
    async MCP calls and async LLM calls, we need async nodes.
    """
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

    # Determine status from message type
    new_status = state["status"]
    if buyer_message["message_type"] == "WITHDRAW":
        new_status = "buyer_walked"
    elif buyer_message["message_type"] == "ACCEPT":
        new_status = "agreed"

    # Display the turn visually
    mcp_calls = ["get_market_price", "calculate_discount"] if this_round == 1 else ["calculate_discount"]
    _turn_box(
        speaker="Buyer",
        price=buyer_message.get("price"),
        msg_type=buyer_message["message_type"],
        message=buyer_message.get("message", ""),
        mcp_calls=mcp_calls,
    )

    # Show routing decision
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
    Seller agent node — responds to buyer's offer.

    LangGraph concept:
    Notice how the seller node reads last_buyer_message from state
    (set by buyer_node) and writes last_seller_message for buyer_node
    to read in the next iteration.

    This is the fundamental data flow pattern in LangGraph:
    Nodes don't call each other directly — they communicate through state.
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

    try:
        seller_message = await seller_agent.respond_to_offer(last_buyer_msg_dict)

    except Exception as e:
        print(f"  [Graph] ERROR in seller agent: {e}")
        return {
            "status": "error",
            "history": [{"round": round_number, "agent": "seller", "error": str(e)}],
        }

    # Determine terminal/continuing status from seller message type.
    new_status = state["status"]
    agreed_price = state.get("agreed_price")

    if seller_message["message_type"] == "ACCEPT":
        new_status = "agreed"
        agreed_price = last_buyer_msg_dict.get("price")
    elif seller_message["message_type"] == "REJECT":
        new_status = "seller_rejected"

    # Deadlock guard: if still negotiating at round limit, force terminal state.
    if round_number >= state["max_rounds"] and new_status == "negotiating":
        new_status = "deadlocked"

    # Display the turn visually
    mcp_calls = ["get_market_price", "get_inventory_level", "get_minimum_acceptable_price"]
    _turn_box(
        speaker="Seller",
        price=seller_message.get("price"),
        msg_type=seller_message["message_type"],
        message=seller_message.get("message", ""),
        mcp_calls=mcp_calls,
    )

    # Show routing decision
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
    """
    Determine next step after buyer node runs.

    LangGraph concept:
    Router functions ONLY read state and return a string key.
    They should be fast, pure functions with no side effects.
    The string they return maps to a node name in add_conditional_edges().

    Route to "end" if:
    - Buyer walked away
    - Buyer accepted seller's counter
    - An error occurred

    Otherwise route to "to_seller" to continue negotiation.
    """
    # Router decisions are driven only by state, never by side effects.
    status = state.get("status", "negotiating")

    if status in ("buyer_walked", "agreed", "error"):
        return "end"

    return "to_seller"


def route_after_seller(state: dict) -> Literal["continue", "end"]:
    """
    Determine next step after seller node runs.

    Route to "continue" (loops back to buyer) if negotiation is still active.
    Route to "end" for all terminal states.
    """
    # If seller emitted any terminal status, stop graph execution.
    status = state.get("status", "negotiating")

    if status != "negotiating":
        return "end"

    # Secondary termination guard in case status was not flipped by a node.
    round_number = state.get("round_number", 0)
    max_rounds = state.get("max_rounds", 5)

    if round_number >= max_rounds:
        return "end"

    return "continue"


# ─── Graph Assembly ───────────────────────────────────────────────────────────

def create_negotiation_graph() -> StateGraph:
    """
    Build and compile the LangGraph negotiation workflow.

    LangGraph concept — graph structure:
    We build the graph in 4 steps:
    1. Create StateGraph with state schema
    2. Add nodes (the processing functions)
    3. Add edges (the connections between nodes)
    4. Compile the graph (validates and optimizes it)

    The resulting graph looks like:
      START → init → buyer → seller → (check) → buyer (loop)
                                             ↓
                                            END
    """
    # Use the declared state schema so LangGraph merges partial node updates
    # instead of replacing the entire state with each node return value.
    workflow = StateGraph(NegotiationState)

    # ── Add nodes ─────────────────────────────────────────────────────────────
    workflow.add_node("init", initialize_agents_node)
    workflow.add_node("buyer", buyer_node)
    workflow.add_node("seller", seller_node)

    # ── Set entry point ────────────────────────────────────────────────────────
    workflow.set_entry_point("init")

    # ── Add edges ──────────────────────────────────────────────────────────────

    # init always goes to buyer (unconditional edge)
    workflow.add_edge("init", "buyer")

    # buyer → seller OR end (conditional based on buyer's decision)
    workflow.add_conditional_edges(
        "buyer",           # Source node
        route_after_buyer, # Router function
        {
            "to_seller": "seller",  # "to_seller" → go to seller node
            "end": END,             # "end" → terminate graph
        }
    )

    # seller → buyer (loop) OR end (conditional based on seller's decision)
    workflow.add_conditional_edges(
        "seller",
        route_after_seller,
        {
            "continue": "buyer",  # "continue" → loop back to buyer
            "end": END,           # "end" → terminate graph
        }
    )

    # ── Compile ────────────────────────────────────────────────────────────────
    # Compilation validates the graph structure and prepares it for execution
    graph = workflow.compile()

    return graph


# ─── Results Display ──────────────────────────────────────────────────────────

def print_negotiation_results(final_state: dict) -> None:
    """Display the final negotiation results and history."""
    width = 65
    print("\n" + "╔" + "═" * (width - 2) + "╗")
    title = "NEGOTIATION COMPLETE — LangGraph Orchestrated"
    pad = (width - 2 - len(title)) // 2
    print("║" + " " * pad + title + " " * (width - 2 - pad - len(title)) + "║")
    print("╚" + "═" * (width - 2) + "╝")

    status = final_state.get("status", "unknown")
    agreed_price = final_state.get("agreed_price")
    listing_price = final_state.get("listing_price", 485_000)
    history = final_state.get("history", [])
    rounds_used = final_state.get("round_number", 0)

    # Outcome banner
    outcome_map = {
        "agreed":          "  DEAL REACHED",
        "buyer_walked":    "  BUYER WALKED AWAY",
        "deadlocked":      "  DEADLOCK — MAX ROUNDS REACHED",
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

    # History table
    if history:
        print(f"\n  {'Rnd':>3}  {'Agent':>8}  {'Type':>16}  {'Price':>12}")
        print("  " + "─" * 46)
        for entry in history:
            price_str = f"${entry.get('price', 0):,.0f}" if entry.get("price") else "—"
            msg_preview = entry.get("message", "")[:30] + "..." if entry.get("message") else ""
            print(
                f"  {entry.get('round', 0):>3}  "
                f"{entry.get('agent', ''):>8}  "
                f"{entry.get('message_type', ''):>16}  "
                f"{price_str:>12}"
            )

    print("\n" + "╔" + "═" * (width - 2) + "╗")
    print("║  LangGraph concepts demonstrated:                             ║")
    print("║    StateGraph  — one shared state, all nodes read/write it    ║")
    print("║    Reducer     — history[] appended, never replaced           ║")
    print("║    Cond. edges — route_after_buyer/seller picked each turn    ║")
    print("║    Async nodes — MCP + LLM calls inside async def node()      ║")
    print("╚" + "═" * (width - 2) + "╝")


# ─── Standalone Runner ────────────────────────────────────────────────────────

async def run_negotiation(
    session_id: str = "neg_001",
    property_address: str = "742 Evergreen Terrace, Austin, TX 78701",
    listing_price: float = 485_000,
    buyer_budget: float = 460_000,
    seller_minimum: float = 445_000,
    max_rounds: int = 5,
    step_mode: bool = False,
) -> dict:
    """
    Run a complete negotiation using the LangGraph workflow.

    This function:
    1. Creates the graph
    2. Creates the initial state
    3. Invokes the graph asynchronously
    4. Displays and returns the final state

    LangGraph concept — ainvoke:
    graph.ainvoke() runs the entire graph from START to END,
    following all conditional edges until a terminal state is reached.
    The returned dict is the FINAL state after all nodes have run.
    """
    # Build the graph
    graph = create_negotiation_graph()

    # Create initial state
    state = initial_state(
        session_id=session_id,
        property_address=property_address,
        listing_price=listing_price,
        buyer_budget=buyer_budget,
        seller_minimum=seller_minimum,
        max_rounds=max_rounds,
        step_mode=step_mode,
    )

    # Run the graph
    # ainvoke() runs the full graph asynchronously
    # It handles the buyer→seller→buyer loop automatically
    # It stops when route_after_seller returns "end"
    final_state = await graph.ainvoke(state)

    # Display results
    print_negotiation_results(final_state)

    return final_state


if __name__ == "__main__":
    # Can be run directly for testing
    asyncio.run(run_negotiation())
