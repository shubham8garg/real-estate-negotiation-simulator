"""
Main Entry Point — LangGraph Multi-Agent Version
==================================================
Runs the real estate negotiation using OpenAI GPT-4o agents
orchestrated by LangGraph.

WHAT THIS DEMONSTRATES:
  1. NegotiationMessage TypedDict — typed contract replacing raw strings
  2. BuyerAgent + SellerAgent — GPT-4o + MCP tool calls, ReAct-style planning
  3. LangGraph graph — StateGraph, conditional edges, async nodes, reducers
  4. Information asymmetry — seller sees floor price, buyer cannot

ARCHITECTURE:
    main_langgraph_multiagent.py
    └── m3_langgraph_multiagents/langgraph_flow.py  (manages the negotiation loop)
          ├── m3_langgraph_multiagents/buyer_simple.py  (GPT-4o + MCP)
          │     └── m2_mcp/pricing_server.py (MCP tools)
          └── m3_langgraph_multiagents/seller_simple.py (GPT-4o + MCP)
                ├── m2_mcp/pricing_server.py (MCP tools)
                └── m2_mcp/inventory_server.py (MCP tools)

HOW TO RUN:
  # Full demo with walkthroughs + live negotiation, step-by-step:
  python m3_langgraph_multiagents/main_langgraph_multiagent.py --demo

  # Demo without pausing (runs fast):
  python m3_langgraph_multiagents/main_langgraph_multiagent.py --demo --fast

  # Skip code walkthroughs, go straight to negotiation:
  python m3_langgraph_multiagents/main_langgraph_multiagent.py --demo --skip-code

  # Just run the negotiation:
  python m3_langgraph_multiagents/main_langgraph_multiagent.py

OPTIONAL FLAGS:
  --demo         Show agent code walkthrough before running negotiation
  --fast         Disable step-mode pauses (runs without ENTER prompts)
  --skip-code    Skip code walkthroughs, go straight to negotiation
  --rounds N     Set maximum negotiation rounds (default: 5)
  --session ID   Set session identifier (default: auto-generated)
"""

import argparse
import asyncio
import inspect
import os
import sys
import textwrap
import time
import uuid
from pathlib import Path


# ─── Display Helpers ──────────────────────────────────────────────────────────

def _wait(step_mode: bool, prompt: str = "  [ENTER to continue →] ") -> None:
    if step_mode:
        input(prompt)
    else:
        time.sleep(0.5)


def _header(title: str, width: int = 65) -> None:
    print("\n" + "╔" + "═" * (width - 2) + "╗")
    pad = (width - 2 - len(title)) // 2
    print("║" + " " * pad + title + " " * (width - 2 - pad - len(title)) + "║")
    print("╚" + "═" * (width - 2) + "╝")


def _section(title: str, width: int = 65) -> None:
    print("\n" + "─" * width)
    print("  " + title)
    print("─" * width)


def _print_source(method, notes: list[str] = None) -> None:
    """Pretty-print a method's source with line numbers and teaching notes."""
    try:
        raw = inspect.getsource(method)
        src = textwrap.dedent(raw)
        lines = src.splitlines()
        print()
        for i, line in enumerate(lines, 1):
            print(f"  {i:>3} │ {line}")
        print()
        if notes:
            print("  Teaching notes:")
            for note in notes:
                print(f"    • {note}")
        print()
    except (OSError, TypeError):
        print(f"  [source unavailable for {method}]")


# ─── Code Walkthroughs ────────────────────────────────────────────────────────

def _show_fsm_to_langgraph_bridge(step_mode: bool) -> None:
    """Part 0: Show the conceptual bridge from M1 FSM to M3 LangGraph."""
    _header("Part 0 — From FSM (M1) to LangGraph (M3): What Changed?")
    print("""
  M1 state_machine.py had a NegotiationFSM with:
    - 4 states: IDLE, NEGOTIATING, AGREED, FAILED
    - A TRANSITIONS dict: each state maps to its valid next states
    - A loop: while not fsm.is_terminal(): ...
    - Agents: NaiveBuyer / NaiveSeller (raw string messages)

  M3 LangGraph replaces the FSM with a StateGraph. Same concept, richer:
    - States  → NegotiationState TypedDict (full dict, not just a status enum)
    - TRANSITIONS dict → conditional edges (route_after_buyer, route_after_seller)
    - while not is_terminal() → graph.ainvoke(state) — LangGraph handles the loop
    - Agents: BuyerAgent / SellerAgent (GPT-4o + MCP tools, TypedDict messages)

  LangGraph IS a state machine. It just adds:
    • Async node execution       (MCP + LLM calls inside nodes)
    • Annotated reducers         (append-only history without overwriting)
    • Schema-validated state     (TypedDict catches wrong field names)
    • Built-in cycle detection   (no accidental infinite loops)
""")
    _wait(step_mode, "  [ENTER: see the comparison table →] ")

    _section("What changed vs what stayed the same — M1 → M3")
    print("""
  ╔══════════════════════════╦══════════════════════════╦══════════════════════════╗
  ║ Concern                  ║ M1 FSM                   ║ M3 LangGraph             ║
  ╠══════════════════════════╬══════════════════════════╬══════════════════════════╣
  ║ State type               ║ NegotiationState Enum    ║ NegotiationState TypedDict║
  ║ State fields             ║ 5 fields (FSMContext)    ║ 14+ fields (full history) ║
  ║ Transition table         ║ TRANSITIONS dict         ║ conditional edges         ║
  ║ Loop control             ║ while not is_terminal()  ║ graph.ainvoke() — hidden  ║
  ║ Termination guarantee    ║ empty transition sets    ║ END node, no outgoing edge║
  ║ Inter-agent messages     ║ raw strings              ║ NegotiationMessage dict   ║
  ║ Agent intelligence       ║ regex + heuristics       ║ GPT-4o + MCP tools        ║
  ║ Tool access              ║ hardcoded strings        ║ MCP servers (live data)   ║
  ║ History tracking         ║ FSMContext.turn_count    ║ history[] reducer         ║
  ╚══════════════════════════╩══════════════════════════╩══════════════════════════╝

  KEY INSIGHT:
    The FSM gave us safe lifecycle control.
    LangGraph gives us the same guarantee PLUS a workflow engine for
    multi-step, async, tool-calling agents.
""")
    _wait(step_mode, "  [ENTER: Part 1 — NegotiationMessage TypedDict →] ")


def _show_negotiation_types_code(step_mode: bool) -> None:
    """Part 1: Show NegotiationMessage TypedDict + factory functions — actual source."""
    _header("Part 1 — Typed Messages: NegotiationMessage TypedDict")
    print("""
  M1 (naive): agents passed RAW STRINGS.
    buyer  → "I offer $425,000 for the property"
    seller → "Counter: $477,000. The kitchen alone cost $45K."
    Problem: regex breaks if LLM rephrases. No round number, no type, no ID.

  M3: agents pass NegotiationMessage TYPED DICTS.
    buyer  → {"message_type": "OFFER", "price": 425000, "round": 1, ...}
    seller → {"message_type": "COUNTER_OFFER", "price": 477000, "round": 1, ...}
    Any field read by name — no parsing, no regex. LangGraph stores it in state.

  File: m3_langgraph_multiagents/negotiation_types.py
""")
    _wait(step_mode, "  [ENTER: show NegotiationMessage class source →] ")

    _section("Step 1 of 3: NegotiationMessage — the typed contract")
    try:
        from m3_langgraph_multiagents.negotiation_types import NegotiationMessage
        _print_source(NegotiationMessage, notes=[
            "message_id: unique per message — enables threading (in_reply_to links)",
            "message_type: OFFER | COUNTER_OFFER | ACCEPT | REJECT | WITHDRAW — no string parsing",
            "price: Optional[float] — None for WITHDRAW/REJECT, set for OFFER/ACCEPT",
            "LangGraph stores this entire dict in last_buyer_message / last_seller_message",
            "Compare M1: buyer.respond_to_counter(message: str) — no type, no fields",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: show create_offer() factory function →] ")

    _section("Step 2 of 3: create_offer() — factory that fills required fields")
    try:
        from m3_langgraph_multiagents.negotiation_types import create_offer
        _print_source(create_offer, notes=[
            "Buyer calls this to produce a guaranteed-valid OFFER message",
            "All required fields are populated — no chance of missing message_type",
            "conditions=[] default — inspection contingency pre-filled",
            "in_reply_to links this offer to the seller's previous message_id",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: show create_acceptance() — terminal message →] ")

    _section("Step 3 of 3: create_acceptance() — terminal message type")
    try:
        from m3_langgraph_multiagents.negotiation_types import create_acceptance
        _print_source(create_acceptance, notes=[
            "Used by BOTH buyer and seller — from_agent determines direction",
            "message_type='ACCEPT' → LangGraph router sees this and routes to END",
            "agreed_price set here — LangGraph stores it in state.agreed_price",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: Part 2 — BuyerAgent code →] ")


def _show_buyer_agent_code(step_mode: bool) -> None:
    """Part 2: Show BuyerAgent actual source — __init__, MCP planning, make_initial_offer."""
    _header("Part 2 — BuyerAgent: GPT-4o + ReAct MCP Planning")
    print("""
  M1 NaiveBuyer:  __init__ stores asking_price + max_price (no LLM, no MCP)
  M3 BuyerAgent:  __init__ stores OpenAI client + conversation history + MCP cache

  Two-layer mechanism (this is what makes it an AGENT, not a script):
    Layer 1 PLANNER:  GPT-4o reads context → {"tool_calls": [{"tool": "get_market_price", ...}]}
    Layer 2 EXECUTOR: agent calls those exact MCP tools → returns data to GPT-4o

  M4 (ADK): Gemini does both layers automatically inside MCPToolset.
  M3: we write both layers explicitly — so you can SEE what the agent decides.

  File: m3_langgraph_multiagents/buyer_simple.py
""")
    _wait(step_mode, "  [ENTER: show BuyerAgent.__init__ →] ")

    _section("Step 1 of 4: BuyerAgent.__init__ — sets up OpenAI client + conversation history")
    try:
        from m3_langgraph_multiagents.buyer_simple import BuyerAgent
        _print_source(BuyerAgent.__init__, notes=[
            "self.client = AsyncOpenAI(...) — this is the LLM connection",
            "self.llm_messages = [system_prompt] — conversation history starts with system role",
            "Each round: user message appended, assistant reply appended → GPT-4o sees FULL history",
            "_market_data: Optional[dict] = None — cached after first MCP call",
            "Compare M1 NaiveBuyer.__init__: just stores budget numbers, no LLM, no history",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: show _plan_mcp_tool_calls — the ReAct planner →] ")

    _section("Step 2 of 4: _plan_mcp_tool_calls() — GPT-4o decides which MCP tools to call")
    try:
        _print_source(BuyerAgent._plan_mcp_tool_calls, notes=[
            "This is the PLANNER step — GPT-4o returns {\"tool_calls\": [...]}",
            "temp=0 and tiny prompt — decision is fast and cheap (not the main negotiation call)",
            "Safety gate: allowed_tools set — even if GPT-4o hallucinates a tool, we block it",
            "Returns max 2 calls — keeps MCP calls bounded per round",
            "Compare M4 (ADK): this whole function is replaced by MCPToolset's auto tool-calling",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: show make_initial_offer — round 1 →] ")

    _section("Step 3 of 4: make_initial_offer() — round 1, no seller counter yet")
    try:
        _print_source(BuyerAgent.make_initial_offer, notes=[
            "Step 1: _gather_mcp_context() — runs the planner, executes MCP tools",
            "Step 2: builds user_message with market data from MCP as context",
            "Step 3: _call_llm() — GPT-4o sees system prompt + market data → returns JSON",
            "Step 4: create_offer() — wraps LLM decision into NegotiationMessage TypedDict",
            "Return value goes into LangGraph state → seller_node reads it next",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: show respond_to_counter — rounds 2+ →] ")

    _section("Step 4 of 4: respond_to_counter() — reads seller's counter from LangGraph state")
    try:
        _print_source(BuyerAgent.respond_to_counter, notes=[
            "seller_message is a NegotiationMessage dict — read fields by name, NO regex",
            "seller_price = seller_message.get('price') — clean, typed access",
            "Budget guardrail (hardcoded): if seller_price <= BUYER_BUDGET → accept immediately",
            "walk_away guardrail: if LLM sets walk_away=True → emit WITHDRAW message",
            "LLM history grows each round — GPT-4o remembers ALL previous offers and counters",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: Part 3 — SellerAgent differences →] ")


def _show_seller_agent_differences(step_mode: bool) -> None:
    """Part 3: Show SellerAgent actual source — dual MCP servers + floor enforcement."""
    _header("Part 3 — SellerAgent: Two MCP Servers + Hard Floor Enforcement")
    print("""
  BuyerAgent  → 1 MCP server  (pricing only: get_market_price, calculate_discount)
  SellerAgent → 2 MCP servers (pricing + inventory: also get_minimum_acceptable_price)

  Information asymmetry — the seller KNOWS its floor, the buyer must GUESS it:
  ┌──────────────────────────────────────────────────────────────┐
  │  Tool                           Buyer     Seller             │
  │  get_market_price               YES       YES                │
  │  calculate_discount             YES       YES                │
  │  get_inventory_level            NO        YES                │
  │  get_minimum_acceptable_price   NO        YES ← FLOOR PRICE  │
  └──────────────────────────────────────────────────────────────┘

  File: m3_langgraph_multiagents/seller_simple.py
""")
    _wait(step_mode, "  [ENTER: show SellerAgent.__init__ — dual MCP server paths →] ")

    _section("Step 1 of 2: SellerAgent.__init__ — same pattern as buyer, but dual MCP paths")
    try:
        from m3_langgraph_multiagents.seller_simple import SellerAgent
        _print_source(SellerAgent.__init__, notes=[
            "Same OpenAI client + llm_messages pattern as BuyerAgent.__init__",
            "_market_data, _inventory_data, _seller_constraints: 3 separate caches",
            "PRICING_SERVER_PATH and INVENTORY_SERVER_PATH — two different MCP servers",
            "Seller connects to inventory server; buyer never does — enforced by convention",
            "In M4 (ADK): enforced at MCPToolset level — buyer's agent literally has no inventory tools",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: show respond_to_offer — auto-accept + floor guardrail →] ")

    _section("Step 2 of 2: respond_to_offer() — auto-accept + LLM floor correction")
    try:
        _print_source(SellerAgent.respond_to_offer, notes=[
            "Line 1: auto-accept — if buyer_price >= MINIMUM_PRICE, skip LLM entirely",
            "This is a HARDCODED rule the LLM cannot override (compare M1 FSM invariants)",
            "_gather_mcp_context() → agent decides which MCP tools to call (same pattern as buyer)",
            "Floor guardrail near the end: if LLM counter < MINIMUM_PRICE → CORRECT IT",
            "return create_counter_offer(...) — typed message back to LangGraph state",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: Part 4 — LangGraph graph construction →] ")


def _show_langgraph_graph_setup(step_mode: bool) -> None:
    """Part 4: Show actual LangGraph graph code — NegotiationState, nodes, edges, routers."""
    _header("Part 4 — LangGraph Graph: StateGraph, Nodes, Edges, Reducers")
    print("""
  Everything in Parts 1–3 is the AGENT layer.
  This part shows the ORCHESTRATION layer — how LangGraph wires it together.

  The graph replaces the FSM's while not fsm.is_terminal() loop.
  Instead: graph.ainvoke(state) runs the full negotiation automatically.

  File: m3_langgraph_multiagents/langgraph_flow.py
""")
    _wait(step_mode, "  [ENTER: show NegotiationState TypedDict (the shared state) →] ")

    _section("Step 1 of 5: NegotiationState — ALL nodes read from and write to this dict")
    try:
        from m3_langgraph_multiagents.langgraph_flow import NegotiationState
        _print_source(NegotiationState, notes=[
            "ALL nodes receive this full dict as 'state' parameter",
            "Nodes return PARTIAL updates — LangGraph merges them (no full replacement)",
            "history: Annotated[list[dict], operator.add] — the REDUCER pattern",
            "  → When buyer_node returns {'history': [entry]}, LangGraph APPENDS, not replaces",
            "_buyer_agent_ref / _seller_agent_ref — agent objects stored in state, reused across rounds",
            "Compare M1 FSMContext: only 5 fields. LangGraph state carries full negotiation data.",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: show create_negotiation_graph — 4-step construction →] ")

    _section("Step 2 of 5: create_negotiation_graph() — the 4-step LangGraph pattern")
    try:
        from m3_langgraph_multiagents.langgraph_flow import create_negotiation_graph
        _print_source(create_negotiation_graph, notes=[
            "Step 1: StateGraph(NegotiationState) — schema-validated state",
            "Step 2: add_node — register async functions as named nodes",
            "Step 3: add_edge / add_conditional_edges — wire the topology",
            "Step 4: workflow.compile() — validates graph, catches dead ends",
            "After compile: graph is a callable — graph.ainvoke(state) runs the full loop",
            "Compare M1: NegotiationFSM.__init__ builds TRANSITIONS dict. Same concept.",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: show buyer_node — an async LangGraph node →] ")

    _section("Step 3 of 5: buyer_node() — async node that calls BuyerAgent + returns partial state")
    try:
        from m3_langgraph_multiagents.langgraph_flow import buyer_node
        _print_source(buyer_node, notes=[
            "state: dict — receives the full NegotiationState, reads what it needs",
            "buyer_agent = state['_buyer_agent_ref'] — reuses the agent created in init node",
            "Returns PARTIAL dict — only the fields that changed this round",
            "LangGraph merges this partial update into the full state automatically",
            "history: [history_entry] — the reducer APPENDS this to the existing list",
            "new_status drives what route_after_buyer() returns next",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: show route_after_buyer — the conditional edge router →] ")

    _section("Step 4 of 5: route_after_buyer() — reads state, returns next node name")
    try:
        from m3_langgraph_multiagents.langgraph_flow import route_after_buyer
        _print_source(route_after_buyer, notes=[
            "PURE FUNCTION: only reads state, returns a string, no side effects",
            "String return value maps to node names in add_conditional_edges()",
            "'to_seller' → go to seller node | 'end' → terminate graph",
            "Compare M1 TRANSITIONS dict: NEGOTIATING → {AGREED, FAILED, NEGOTIATING}",
            "Same concept: given current state, what's the valid next state?",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: show route_after_seller — the loop-or-stop router →] ")

    _section("Step 5 of 5: route_after_seller() — loop back to buyer or terminate")
    try:
        from m3_langgraph_multiagents.langgraph_flow import route_after_seller
        _print_source(route_after_seller, notes=[
            "'continue' → routes back to buyer_node — this IS the negotiation loop",
            "'end' → routes to END — graph stops, ainvoke() returns final state",
            "Round limit guard: if round_number >= max_rounds → deadlock (same as FSM max_turns)",
            "This function replaces: while not fsm.is_terminal() + fsm.process_turn()",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: run live negotiation →] ")


# ─── Environment helpers ──────────────────────────────────────────────────────

def _load_env_file_if_present(env_path: Path) -> None:
    """Load KEY=VALUE pairs from .env into process env without overriding existing vars."""
    if not env_path.exists():
        return

    try:
        with env_path.open("r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        # Non-fatal: explicit shell exports still work.
        pass

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    # Ensure absolute imports work even when launched from other directories.
    sys.path.insert(0, str(REPO_ROOT))

# Load .env early so check_environment() sees OPENAI_API_KEY without shell export.
_load_env_file_if_present(REPO_ROOT / ".env")

# Validate environment before importing anything
def check_environment() -> None:
    """Check that required environment variables are set."""
    missing = []

    if not os.environ.get("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")

    if missing:
        print("ERROR: Missing required environment variables:")
        for var in missing:
            # Keep output shell-friendly for quick copy/paste.
            print(f"   export {var}=<your_value>")
        print()
        print("Get your OpenAI API key at: https://platform.openai.com/api-keys")
        sys.exit(1)


async def main() -> None:
    """Main entry point for the LangGraph negotiation demo."""

    # ── Parse arguments ───────────────────────────────────────────────────────
    parser = argparse.ArgumentParser(
        description="Real Estate Negotiation — LangGraph Multi-Agent Version",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full teaching demo with walkthroughs + live negotiation:
  python m3_langgraph_multiagents/main_langgraph_multiagent.py --demo

  # Demo, no pauses:
  python m3_langgraph_multiagents/main_langgraph_multiagent.py --demo --fast

  # Skip code walkthroughs, go straight to negotiation:
  python m3_langgraph_multiagents/main_langgraph_multiagent.py --demo --skip-code

  # Just run negotiation (no walkthroughs):
  python m3_langgraph_multiagents/main_langgraph_multiagent.py
""",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Show agent code walkthrough before running negotiation",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Disable step-mode pauses (run without ENTER prompts)",
    )
    parser.add_argument(
        "--skip-code",
        action="store_true",
        help="Skip code walkthroughs — go straight to negotiation",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=5,
        help="Maximum negotiation rounds (default: 5)",
    )
    parser.add_argument(
        "--session",
        type=str,
        default=None,
        help="Session ID (default: auto-generated)",
    )
    parser.add_argument(
        "--buyer-budget",
        type=float,
        default=460_000,
        help="Buyer maximum budget (default: 460000)",
    )
    parser.add_argument(
        "--seller-minimum",
        type=float,
        default=445_000,
        help="Seller minimum price (default: 445000)",
    )
    args = parser.parse_args()

    step_mode = args.demo and not args.fast
    session_id = args.session or f"neg_{uuid.uuid4().hex[:8]}"

    # ── Environment check ─────────────────────────────────────────────────────
    check_environment()

    # ── Intro banner ──────────────────────────────────────────────────────────
    _header("Module 3 — LangGraph Multi-Agent Negotiation")
    print(f"""
  Stack:   OpenAI GPT-4o + MCP + LangGraph
  Module:  m3_langgraph_multiagents/

  What you will see (--demo):
    Part 0. FSM → LangGraph bridge    — what changed and what stayed the same
    Part 1. NegotiationMessage        — TypedDict replacing raw strings (source code)
    Part 2. BuyerAgent code           — GPT-4o + ReAct MCP planning (source code)
    Part 3. SellerAgent code          — dual MCP servers + floor enforcement (source code)
    Part 4. LangGraph graph           — StateGraph, nodes, edges, routers (source code)
    Live:   Negotiation turns         — both agents running, MCP calls + routing visible

  Property:      742 Evergreen Terrace, Austin, TX 78701
  Listed at:     $485,000
  Buyer budget:  ${args.buyer_budget:,.0f}
  Seller floor:  ${args.seller_minimum:,.0f}  (mortgage payoff — seller-confidential)
  Max rounds:    {args.rounds}
  Session:       {session_id}
""")

    if args.demo:
        _wait(step_mode, "  [ENTER: start walkthroughs →] ")

        # ── Code walkthroughs ─────────────────────────────────────────────────
        if not args.skip_code:
            _show_fsm_to_langgraph_bridge(step_mode)   # Part 0: FSM → LangGraph bridge
            _show_negotiation_types_code(step_mode)    # Part 1: NegotiationMessage TypedDict
            _show_buyer_agent_code(step_mode)          # Part 2: BuyerAgent source
            _show_seller_agent_differences(step_mode)  # Part 3: SellerAgent source
            _show_langgraph_graph_setup(step_mode)     # Part 4: LangGraph graph source
        else:
            print("  [Skipping code walkthroughs — --skip-code flag set]")
            print("  Parts 0-4 cover: FSM→LangGraph bridge, TypedDict, BuyerAgent, SellerAgent, graph")
            print()
            _wait(step_mode, "  [ENTER: run negotiation →] ")
    else:
        print("  Tip: Run with --demo for full code walkthroughs before negotiation.")
        print()

    # ── Run the LangGraph negotiation ─────────────────────────────────────────
    _header("Live Negotiation — LangGraph Orchestrated")
    print("""
  Watch two layers simultaneously:
    AGENT LAYER  — buyer/seller messages, MCP tool calls, GPT-4o decisions
    GRAPH LAYER  — which node runs, what the router returns, state updates

  [Graph] prefix = LangGraph framework messages
  [Buyer] prefix = BuyerAgent activity
  [Seller] prefix = SellerAgent activity
""")
    if step_mode:
        input("  [ENTER: start negotiation →] ")

    from m3_langgraph_multiagents.langgraph_flow import run_negotiation

    try:
        final_state = await run_negotiation(
            session_id=session_id,
            property_address="742 Evergreen Terrace, Austin, TX 78701",
            listing_price=485_000.0,
            buyer_budget=args.buyer_budget,
            seller_minimum=args.seller_minimum,
            max_rounds=args.rounds,
            step_mode=step_mode,
        )

        # ── Post-negotiation ──────────────────────────────────────────────────
        print("\n  What just happened:")
        print("    • LangGraph called init → buyer → seller → buyer ... automatically")
        print("    • Each node returned PARTIAL state; LangGraph merged updates")
        print("    • history[] grew via Annotated[list, operator.add] reducer")
        print("    • route_after_buyer/seller read status → decided next node")
        print()
        print("  Next steps:")
        print("    M4 (ADK):  python m4_adk_multiagents/a2a_protocol_seller_server.py --port 9102")
        print("    Exercises: open exercises/exercises.md")
        print()

        return final_state

    except KeyboardInterrupt:
        print("\n\n  Negotiation interrupted.")
        sys.exit(0)

    except Exception as e:
        print(f"\n  ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
