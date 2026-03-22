"""
HTTP A2A Negotiation Orchestrator (Google ADK-native state)
===========================================================
Runs a multi-round negotiation loop over HTTP A2A.

- Buyer turn is produced by BuyerAgentADK (Google ADK + OpenAI GPT-4o).
- Seller turn is requested from a remote A2A seller server over JSON-RPC.
- Orchestration state is persisted in ADK InMemorySessionService.

WHAT THIS DEMONSTRATES:
  1. BuyerAgentADK — LlmAgent + MCPToolset (automatic tool-calling vs M3 manual)
  2. A2A Protocol   — Agent Card discovery + JSON-RPC message/send
  3. M3 vs M4       — same negotiation, different tool-calling mechanism

HOW TO RUN:
  # Terminal 1 — start the seller server:
  python m4_adk_multiagents/a2a_protocol_seller_server.py --port 9102

  # Terminal 2 — run the orchestrator with full demo walkthrough:
  python m4_adk_multiagents/a2a_protocol_http_orchestrator.py --demo \\
         --seller-url http://127.0.0.1:9102

  # No pauses:
  python m4_adk_multiagents/a2a_protocol_http_orchestrator.py --demo --fast \\
         --seller-url http://127.0.0.1:9102

  # Skip walkthroughs, just run negotiation:
  python m4_adk_multiagents/a2a_protocol_http_orchestrator.py \\
         --seller-url http://127.0.0.1:9102
"""

import argparse
import asyncio
import inspect
import json
import os
import sys
import textwrap
import time
import uuid
from pathlib import Path
from typing import Any, Literal, Optional

import httpx
from a2a.client import A2AClient, A2ACardResolver
from a2a.types import Message, MessageSendParams, Role, SendMessageRequest, TextPart
from dotenv import load_dotenv
from google.adk.events import Event
from google.adk.events.event_actions import EventActions
from google.adk.sessions import InMemorySessionService
from pydantic import BaseModel, Field, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load environment from repo root so this file works even when launched from subfolders.
load_dotenv(REPO_ROOT / ".env")

from m4_adk_multiagents.buyer_adk import BuyerAgentADK


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


def _turn_box(agent: str, round_num: int, msg_type: str, price: Optional[float],
              message: str, transport: str = "", step_mode: bool = False) -> None:
    icon = "🏠 BUYER" if agent == "buyer" else "🏡 SELLER"
    width = 65
    label = f"  Round {round_num} — {icon}  "
    bar = "═" * ((width - len(label)) // 2)
    print(f"\n╔{bar}{label}{bar}╗")

    price_str = f"${price:,.0f}" if price else "—"
    print(f"  ┌─ {agent.capitalize()} {'→' if agent == 'buyer' else '←'} A2A " + "─" * (width - 20))
    print(f"  │  Type:      {msg_type}")
    print(f"  │  Price:     {price_str}")
    if transport:
        print(f"  │  Transport: {transport}")
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
    for i, line in enumerate(lines[:3]):
        prefix = "  │  Message:  " if i == 0 else "  │            "
        print(f"{prefix}{line}")
    print(f"  └" + "─" * width)
    if step_mode:
        input("  [ENTER: next turn →] ")
    else:
        time.sleep(0.2)


# ─── Code Walkthroughs ────────────────────────────────────────────────────────

def _show_m3_to_m4_bridge(step_mode: bool) -> None:
    """Part 0: What changed from M3 LangGraph to M4 ADK + A2A?"""
    _header("Part 0 — From LangGraph (M3) to ADK + A2A (M4): What Changed?")
    print("""
  M3 (LangGraph):
    - BuyerAgent manually calls MCP → manually builds LLM prompt → calls GPT-4o
    - SellerAgent same pattern
    - LangGraph StateGraph wires them: graph.ainvoke(state) runs the loop
    - Buyer and seller live in the SAME process, communicate through shared state

  M4 (ADK + A2A):
    - BuyerAgentADK: MCPToolset discovers tools, Runner auto-calls them — no manual wiring
    - SellerAgentADK: same ADK pattern, runs as a SEPARATE HTTP server process
    - Orchestrator: simple for-loop, sends HTTP JSON-RPC to seller each round
    - Buyer and seller live in DIFFERENT processes, communicate through HTTP

  Same negotiation logic. Same MCP servers. Same GPT-4o.
  What changes: tool-calling mechanism (manual → ADK auto) + transport (in-process → HTTP).
""")
    _wait(step_mode, "  [ENTER: see the comparison table →] ")

    _section("What changed vs what stayed the same — M3 → M4")
    print("""
  ╔══════════════════════════╦══════════════════════════╦══════════════════════════╗
  ║ Concern                  ║ M3 (LangGraph)           ║ M4 (ADK + A2A)           ║
  ╠══════════════════════════╬══════════════════════════╬══════════════════════════╣
  ║ Orchestration            ║ LangGraph StateGraph     ║ Manual for loop          ║
  ║ Buyer↔Seller comms       ║ Shared Python state dict ║ HTTP JSON-RPC (A2A)      ║
  ║ MCP tool-calling         ║ Manual (ReAct planner)   ║ Auto (MCPToolset)        ║
  ║ Tool discovery           ║ Hardcoded function calls ║ ADK get_tools()          ║
  ║ Session memory           ║ LangGraph history[]      ║ ADK InMemorySessionService║
  ║ Seller location          ║ Same process             ║ Any HTTP endpoint        ║
  ║ Floor price guard        ║ Hardcoded if in Python   ║ Same guardrail in ADK    ║
  ║ MCP servers used         ║ pricing + inventory      ║ pricing + inventory      ║
  ║ LLM model                ║ OpenAI GPT-4o            ║ OpenAI GPT-4o            ║
  ╚══════════════════════════╩══════════════════════════╩══════════════════════════╝

  KEY INSIGHT:
    The agent LOGIC (what to offer, when to accept, floor guardrail) is identical.
    What changed is the INFRASTRUCTURE:
      ADK removes manual MCP wiring (MCPToolset replaces _plan_mcp_tool_calls)
      A2A removes process coupling (HTTP replaces Python dict state)
""")
    _wait(step_mode, "  [ENTER: Part 1 — BuyerAgentADK code →] ")


def _show_adk_buyer_code(step_mode: bool) -> None:
    """Parts 1: BuyerAgentADK — __init__, __aenter__, _run_agent, make_initial_offer."""
    _header("Part 1 — BuyerAgentADK: LlmAgent + MCPToolset + Runner")
    print("""
  M3 BuyerAgent.__init__: stores OpenAI client + llm_messages list
  M4 BuyerAgentADK.__init__: stores config only — NO connections yet

  M3 BuyerAgent: manually calls MCP → manually builds GPT-4o prompt
  M4 BuyerAgentADK: MCPToolset auto-discovers tools, Runner auto-calls them

  ADK lifecycle (context manager pattern):
    __init__    → store config (no connections)
    __aenter__  → connect to MCP, create LlmAgent, create Runner, create Session
    _run_agent  → execute one turn, collect ADK events, return final text
    __aexit__   → close MCP subprocess

  File: m4_adk_multiagents/buyer_adk.py
""")
    _wait(step_mode, "  [ENTER: show BuyerAgentADK.__init__ →] ")

    _section("Step 1 of 4: BuyerAgentADK.__init__ — config only, no connections yet")
    try:
        from m4_adk_multiagents.buyer_adk import BuyerAgentADK
        _print_source(BuyerAgentADK.__init__, notes=[
            "No OpenAI client here — LlmAgent creates it inside __aenter__",
            "No llm_messages list — ADK InMemorySessionService manages history automatically",
            "_pricing_toolset = None — placeholder, MCPToolset created in __aenter__",
            "Compare M3 BuyerAgent.__init__: creates self.client and self.llm_messages immediately",
            "ADK separates config (__init__) from connection (__aenter__) — cleaner lifecycle",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: show __aenter__ — MCPToolset + LlmAgent + Runner →] ")

    _section("Step 2 of 4: __aenter__ — MCPToolset connects, LlmAgent gets tools, Runner created")
    try:
        _print_source(BuyerAgentADK.__aenter__, notes=[
            "MCPToolset(StdioConnectionParams(StdioServerParameters(...))) → spawns MCP server subprocess",
            "get_tools() → ADK calls list_tools() over MCP protocol → returns tool objects",
            "LlmAgent(model=OPENAI_MODEL, tools=tools) → tools wired automatically — no manual wiring",
            "Runner(agent, session_service) → will handle the full tool-calling loop per turn",
            "Compare M3: no MCPToolset, no Runner — agent manually calls call_pricing_mcp()",
            "Context manager ensures __aexit__ closes MCP subprocess even on error",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: show _run_agent — the ADK event loop →] ")

    _section("Step 3 of 4: _run_agent() — async generator, tool calls happen automatically")
    try:
        _print_source(BuyerAgentADK._run_agent, notes=[
            "runner.run_async() returns an async generator of ADK Event objects",
            "Events include: tool_call_start, tool_result, text_delta, final_response",
            "ADK handles the full tool-calling loop: model → call tool → feed result back → model",
            "We only collect the final text — all intermediate tool calls are invisible",
            "Compare M3: explicit for-loop over planned_calls, explicit MCP call, explicit prompt building",
            "M3 shows the mechanism; M4 shows the outcome — same negotiation, different visibility",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: show make_initial_offer_envelope — round 1 →] ")

    _section("Step 4 of 4: make_initial_offer_envelope() — prompt → ADK → BuyerEnvelope")
    try:
        _print_source(BuyerAgentADK.make_initial_offer_envelope, notes=[
            "Prompt explicitly instructs: call get_market_price FIRST, then calculate_discount",
            "_run_agent(prompt) → ADK handles tool calls → returns final JSON text",
            "_parse_strict_json_output() → Pydantic validates the LLM response",
            "BuyerEnvelope.model_dump() → returns plain dict for JSON-RPC transport",
            "Compare M3 make_initial_offer(): same logic but manual MCP → manual prompt → create_offer()",
            "M4 output is BuyerEnvelope (Pydantic), M3 output is NegotiationMessage (TypedDict)",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: Part 2 — SellerAgentADK (dual MCPToolset) →] ")


def _show_adk_seller_code(step_mode: bool) -> None:
    """Part 2: SellerAgentADK — dual MCPToolset setup + floor guardrail."""
    _header("Part 2 — SellerAgentADK: Two MCPToolsets + Floor Enforcement")
    print("""
  BuyerAgentADK  → 1 MCPToolset (pricing server only)
  SellerAgentADK → 2 MCPToolsets (pricing + inventory)

  ADK merges tools from both servers into ONE unified tool list.
  The LlmAgent sees all 4 tools and picks which to call based on context.

  Information asymmetry enforced at MCPToolset level:
    Buyer's LlmAgent → has only [get_market_price, calculate_discount]
    Seller's LlmAgent → has all 4: above + get_inventory_level + get_minimum_acceptable_price

  File: m4_adk_multiagents/seller_adk.py
""")
    _wait(step_mode, "  [ENTER: show SellerAgentADK.__aenter__ — two MCPToolsets →] ")

    _section("Step 1 of 2: SellerAgentADK.__aenter__ — dual MCPToolset setup")
    try:
        from m4_adk_multiagents.seller_adk import SellerAgentADK
        _print_source(SellerAgentADK.__aenter__, notes=[
            "Two separate MCPToolset() calls — one per MCP server",
            "pricing_tools = await self._pricing_toolset.get_tools()",
            "inventory_tools = await self._inventory_toolset.get_tools()",
            "all_tools = list(pricing_tools) + list(inventory_tools) — MERGED list",
            "LlmAgent(tools=all_tools) → model sees all 4 tools as a unified list",
            "Compare M3 SellerAgent: two separate server_paths, two separate call_mcp_server() functions",
            "M4: ADK merges tool discovery — M3: agent manually routes to the right server",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: show respond_to_offer_envelope — floor guardrail →] ")

    _section("Step 2 of 2: respond_to_offer_envelope() — auto floor correction")
    try:
        _print_source(SellerAgentADK.respond_to_offer_envelope, notes=[
            "Prompt explicitly tells model: call get_minimum_acceptable_price FIRST",
            "_run_agent(prompt) → ADK calls all 3 MCP tools automatically",
            "counter_price = max(float(counter_price), float(MINIMUM_PRICE)) — floor guardrail",
            "This is the SAME hardcoded rule as M3 — the LLM cannot override it",
            "Result wrapped in SellerEnvelope (Pydantic) → serialized to JSON for HTTP response",
            "Compare M3 respond_to_offer(): explicit _gather_mcp_context() + explicit LLM call",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: Part 3 — A2A Protocol (server + client source) →] ")


def _show_a2a_protocol_walkthrough(step_mode: bool, seller_url: str = "http://127.0.0.1:9102") -> None:
    """Part 3: A2A Protocol — actual source from seller server + orchestrator."""
    _header("Part 3 — A2A Protocol: Agent Card + Server Executor + HTTP Client")
    print(f"""
  A2A (Agent-to-Agent): a protocol so agents talk over HTTP without knowing
  each other's implementation. Buyer sends JSON-RPC → seller responds.

  Three pieces of code make this work:
    1. _build_agent_card()           — seller announces itself (discovery)
    2. SellerADKA2AExecutor.execute() — seller handles each incoming message
    3. _extract_first_seller_envelope() — orchestrator parses the response

  Seller server runs at: {seller_url}
  Agent Card endpoint:   {seller_url}/.well-known/agent-card.json
""")
    _wait(step_mode, "  [ENTER: show _build_agent_card — seller self-description →] ")

    _section("Step 1 of 4: _build_agent_card() — what the seller announces to buyers")
    try:
        from m4_adk_multiagents.a2a_protocol_seller_server import _build_agent_card
        _print_source(_build_agent_card, notes=[
            "AgentCard is the discovery contract — buyer fetches this BEFORE sending any message",
            "skills[] describes what the seller can do — structured like an API spec",
            "capabilities: streaming=False — simple request/response, no streaming",
            "protocolVersion: '0.3.0' — buyer and seller must speak the same A2A version",
            "Any A2A-compatible client can discover and talk to this server — buyer doesn't need ADK",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: show SellerADKA2AExecutor.execute — server request handler →] ")

    _section("Step 2 of 4: SellerADKA2AExecutor.execute() — how the server handles each message")
    try:
        from m4_adk_multiagents.a2a_protocol_seller_server import SellerADKA2AExecutor
        _print_source(SellerADKA2AExecutor.execute, notes=[
            "TaskUpdater tracks A2A task lifecycle: start_work() → complete() or failed()",
            "context.get_user_input() → extracts the buyer's JSON text from the TextPart",
            "BuyerEnvelope.model_validate(json.loads(...)) → validates incoming contract",
            "SESSION_REGISTRY.get_or_create(session_id) → reuses one SellerAgentADK per session",
            "seller.respond_to_offer_envelope(envelope) → runs SellerAgentADK (2 MCPToolsets + GPT-4o)",
            "updater.complete(agent_message) → sends SellerEnvelope JSON back to buyer",
        ])
    except Exception as e:
        print(f"  [source unavailable: {e}]")

    _wait(step_mode, "  [ENTER: show _extract_first_seller_envelope — orchestrator parsing →] ")

    _section("Step 3 of 4: _extract_first_seller_envelope() — parse seller's A2A response")
    _print_source(_extract_first_seller_envelope, notes=[
        "A2A SDK response is deeply nested — we recursively find all text parts",
        "_extract_texts() walks the response tree looking for 'text' string values",
        "json.loads(text) → try to parse each text part as JSON",
        "SellerEnvelope.model_validate(candidate) → validates it matches the contract",
        "First valid envelope wins — tolerates extra text/metadata in the response",
        "This is the glue layer: raw HTTP response → typed Python dict",
    ])

    _wait(step_mode, "  [ENTER: show ADKOrchestrationState — session state store →] ")

    _section("Step 4 of 4: ADKOrchestrationState — ADK session as orchestration memory")
    _print_source(ADKOrchestrationState, notes=[
        "InMemorySessionService stores negotiation state across rounds",
        "update(state_delta) → append_event with EventActions(stateDelta=...) — same pattern as agents",
        "read_state() → returns full session state dict — useful for debugging and audit",
        "This replaces M3's LangGraph shared state — same goal, different mechanism",
        "In production: swap InMemorySessionService for DatabaseSessionService for persistence",
    ])

    _wait(step_mode, "  [ENTER: Part 4 — M3 vs M4 full comparison →] ")


def _show_m3_vs_m4_comparison(step_mode: bool) -> None:
    """Part 4: M3 vs M4 full comparison — same negotiation, different plumbing."""
    _header("Part 4 — M3 vs M4: Full Architecture Comparison")
    print("""
  ╔══════════════════════════╦══════════════════════════╦══════════════════════════╗
  ║ Concern                  ║ M3 (LangGraph)           ║ M4 (ADK + A2A)           ║
  ╠══════════════════════════╬══════════════════════════╬══════════════════════════╣
  ║ Orchestration            ║ LangGraph StateGraph     ║ Manual for loop          ║
  ║ Buyer↔Seller comms       ║ Shared TypedDict state   ║ HTTP A2A JSON-RPC        ║
  ║ MCP tool-calling         ║ Manual (ReAct planner)   ║ Auto (MCPToolset)        ║
  ║ Tool discovery           ║ Hardcoded function calls ║ ADK get_tools()          ║
  ║ Agent session memory     ║ LangGraph history[]      ║ ADK InMemorySessionService║
  ║ Seller location          ║ Same Python process      ║ Any HTTP endpoint        ║
  ║ Seller language          ║ Python only              ║ Any language (A2A spec)  ║
  ║ Floor guardrail          ║ Python if-statement      ║ Python if-statement      ║
  ║ MCP servers used         ║ pricing + inventory      ║ pricing + inventory      ║
  ║ LLM model                ║ OpenAI GPT-4o            ║ OpenAI GPT-4o            ║
  ╚══════════════════════════╩══════════════════════════╩══════════════════════════╝

  WHAT THIS WORKSHOP TAUGHT:
    M1 Naive   → raw strings, while True — no structure
    M1 FSM     → lifecycle control — provable termination
    M2 MCP     → tool protocol — agents access structured data
    M3 LangGraph → stateful orchestration — typed messages, graph routing
    M4 ADK+A2A → distributed agents — auto tool-calling, HTTP inter-agent comms

  PRODUCTION INSIGHT:
    M3 is best when agents share a process (same team, same codebase).
    M4 is best when agents are owned by different teams, languages, or services.
    A2A lets a Python buyer talk to a Java seller — both speak the same protocol.
""")
    _wait(step_mode, "  [ENTER: run live negotiation →] ")


# ─── Data types ───────────────────────────────────────────────────────────────

class SellerEnvelope(BaseModel):
    # Envelope schema expected from seller A2A responses.
    session_id: str
    round: int
    from_agent: Literal["seller"]
    to_agent: Literal["buyer"]
    message_type: Literal["COUNTER_OFFER", "ACCEPT", "REJECT"]
    price: float | None = None
    message: str
    conditions: list[str] = Field(default_factory=list)
    closing_timeline_days: int | None = None
    in_reply_to: str | None = None


def _extract_texts(obj: Any) -> list[str]:
    # A2A SDK responses are nested; we flatten all text parts so we can parse envelopes.
    texts: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "text" and isinstance(value, str):
                texts.append(value)
            else:
                texts.extend(_extract_texts(value))
    elif isinstance(obj, list):
        for item in obj:
            texts.extend(_extract_texts(item))
    return texts


def _extract_first_seller_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    # Iterate through all text parts and return the first valid seller envelope.
    for text in _extract_texts(payload):
        try:
            candidate = json.loads(text)
            if isinstance(candidate, dict):
                parsed = SellerEnvelope.model_validate(candidate)
                return parsed.model_dump(mode="json")
        except ValidationError:
            continue
        except json.JSONDecodeError:
            continue
    raise ValueError("No valid seller envelope found in A2A response text parts.")


class ADKOrchestrationState:
    # Thin wrapper around ADK SessionService used as orchestration state store.
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.app_name = "a2a_http_orchestrator"
        self.user_id = "orchestrator"
        self._service = InMemorySessionService()

    async def initialize(self, max_rounds: int) -> None:
        await self._service.create_session(
            app_name=self.app_name,
            user_id=self.user_id,
            session_id=self.session_id,
            state={"round": 0, "status": "negotiating", "max_rounds": max_rounds},
        )

    async def update(self, state_delta: dict[str, Any]) -> None:
        session = await self._service.get_session(
            app_name=self.app_name,
            user_id=self.user_id,
            session_id=self.session_id,
        )
        if session is None:
            raise RuntimeError("Orchestration ADK session not found.")
        await self._service.append_event(
            session=session,
            event=Event(author=self.user_id, actions=EventActions(stateDelta=state_delta)),
        )

    async def read_state(self) -> dict[str, Any]:
        session = await self._service.get_session(
            app_name=self.app_name,
            user_id=self.user_id,
            session_id=self.session_id,
        )
        if session is None:
            return {}
        return dict(session.state)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="HTTP A2A Orchestrator — ADK Buyer + A2A Seller",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start seller server first (separate terminal):
  python m4_adk_multiagents/a2a_protocol_seller_server.py --port 9102

  # Full teaching demo:
  python m4_adk_multiagents/a2a_protocol_http_orchestrator.py --demo \\
         --seller-url http://127.0.0.1:9102

  # Demo, no pauses:
  python m4_adk_multiagents/a2a_protocol_http_orchestrator.py --demo --fast \\
         --seller-url http://127.0.0.1:9102

  # Just run negotiation:
  python m4_adk_multiagents/a2a_protocol_http_orchestrator.py \\
         --seller-url http://127.0.0.1:9102
""",
    )
    parser.add_argument("--seller-url", default="http://127.0.0.1:9102")
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--session", default=None)
    parser.add_argument("--demo", action="store_true",
                        help="Show agent code walkthrough before negotiation")
    parser.add_argument("--fast", action="store_true",
                        help="Disable step-mode pauses")
    parser.add_argument("--skip-code", action="store_true",
                        help="Skip code walkthroughs")
    args = parser.parse_args()

    # Validate seller URL — catch common typos like :910 instead of :9102.
    import urllib.parse as _urlparse
    _parsed = _urlparse.urlparse(args.seller_url)
    if not _parsed.scheme or not _parsed.netloc:
        print(f"ERROR: --seller-url '{args.seller_url}' is not a valid URL.")
        print("  Expected format: http://127.0.0.1:9102")
        print("  Start the seller server first:")
        print("    python m4_adk_multiagents/a2a_protocol_seller_server.py --port 9102")
        raise SystemExit(1)
    if _parsed.port and _parsed.port != 9102:
        print(f"WARNING: --seller-url uses port {_parsed.port}, but the seller server")
        print(f"  defaults to port 9102. Did you mean: http://{_parsed.hostname}:9102 ?")
        print(f"  Continuing with {args.seller_url} — press Ctrl+C to abort.")
        print()

    step_mode = args.demo and not args.fast

    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set. Set it before running this demo.")
        raise SystemExit(1)

    session_id = args.session or f"a2a_http_{uuid.uuid4().hex[:8]}"

    # ── Intro banner ──────────────────────────────────────────────────────────
    _header("Module 4 — ADK Multi-Agent + A2A Protocol Negotiation")
    print(f"""
  Stack:   Google ADK + OpenAI GPT-4o + A2A Protocol
  Module:  m4_adk_multiagents/

  What you will see (--demo):
    Part 0. M3 → M4 bridge      — what changed and what stayed the same
    Part 1. BuyerAgentADK code  — __init__, __aenter__, _run_agent, make_initial_offer (source)
    Part 2. SellerAgentADK code — dual MCPToolset + floor guardrail (source)
    Part 3. A2A Protocol        — Agent Card, server executor, response parsing (source)
    Part 4. M3 vs M4 table      — full architecture comparison
    Live:   Negotiation turns   — buyer HTTP→seller, A2A JSON-RPC visible round by round

  Seller URL:   {args.seller_url}
  Session:      {session_id}
  Max rounds:   {args.rounds}
""")

    if args.demo:
        _wait(step_mode, "  [ENTER: start walkthroughs →] ")

        if not args.skip_code:
            _show_m3_to_m4_bridge(step_mode)                              # Part 0: M3→M4 bridge
            _show_adk_buyer_code(step_mode)                               # Part 1: BuyerAgentADK
            _show_adk_seller_code(step_mode)                              # Part 2: SellerAgentADK
            _show_a2a_protocol_walkthrough(step_mode, args.seller_url)    # Part 3: A2A protocol
            _show_m3_vs_m4_comparison(step_mode)                          # Part 4: comparison
        else:
            print("  [Skipping code walkthroughs — --skip-code flag set]")
            print("  Parts 0-4: M3→M4 bridge, BuyerAgentADK, SellerAgentADK, A2A protocol, comparison")
            print()
            _wait(step_mode, "  [ENTER: run negotiation →] ")
    else:
        print("  Tip: Run with --demo for full code walkthroughs before negotiation.")
        print()

    # ── Live negotiation ──────────────────────────────────────────────────────
    _header("Live A2A Negotiation — HTTP JSON-RPC")
    print(f"""
  Buyer (local ADK agent) ←—HTTP—→ Seller (remote A2A server at {args.seller_url})

  Watch:
    [Buyer ADK]  — BuyerAgentADK activity (MCPToolset tool calls, GPT-4o)
    [Seller ADK] — SellerAgentADK activity (printed by the seller server)
    [A2A]        — HTTP requests/responses between buyer and seller
""")
    if step_mode:
        input("  [ENTER: start negotiation →] ")

    state = ADKOrchestrationState(session_id=session_id)
    await state.initialize(max_rounds=args.rounds)

    async with BuyerAgentADK(session_id=f"{session_id}_buyer") as buyer:
        async with httpx.AsyncClient(timeout=45.0) as http_client:
            # Step 1: Discover seller via Agent Card
            print(f"\n  [A2A] Fetching Agent Card from {args.seller_url}/.well-known/agent-card.json")
            resolver = A2ACardResolver(httpx_client=http_client, base_url=args.seller_url)
            card = await resolver.get_agent_card()
            print(f"  [A2A] Agent Card received: name={card.name}")
            print(f"  [A2A] Skills: {[s.id for s in card.skills]}")
            print(f"  [A2A] Protocol: {card.protocol_version}")

            if step_mode:
                input("\n  [ENTER: start round 1 →] ")

            client = A2AClient(httpx_client=http_client, agent_card=card)

            last_seller: Optional[dict[str, Any]] = None
            status = "negotiating"
            agreed_price: Optional[float] = None
            history: list[dict] = []

            for round_num in range(1, args.rounds + 1):
                # ── Buyer turn ────────────────────────────────────────────────
                if round_num == 1:
                    buyer_message = await buyer.make_initial_offer_envelope()
                else:
                    if last_seller is None:
                        raise RuntimeError("Missing seller message for next buyer turn.")
                    buyer_message = await buyer.respond_to_counter_envelope(last_seller)

                _turn_box(
                    agent="buyer",
                    round_num=buyer_message["round"],
                    msg_type=buyer_message["message_type"],
                    price=buyer_message.get("price"),
                    message=buyer_message.get("message", ""),
                    transport="MCPToolset → GPT-4o → A2A envelope",
                    step_mode=step_mode,
                )

                await state.update({
                    "round": buyer_message["round"],
                    "status": "buyer_walked" if buyer_message["message_type"] == "WITHDRAW" else "negotiating",
                    "last_buyer_type": buyer_message["message_type"],
                    "last_buyer_price": buyer_message.get("price"),
                })
                history.append({
                    "round": buyer_message["round"],
                    "agent": "buyer",
                    "type": buyer_message["message_type"],
                    "price": buyer_message.get("price"),
                })

                if buyer_message["message_type"] == "WITHDRAW":
                    status = "buyer_walked"
                    break

                # ── A2A HTTP call to seller ───────────────────────────────────
                print(f"\n  [A2A] POST {args.seller_url}/  (message/send JSON-RPC)")
                print(f"  [A2A] Sending buyer offer round {buyer_message['round']} — ${buyer_message.get('price') or 0:,.0f}")

                request = SendMessageRequest(
                    id=f"req_{uuid.uuid4().hex[:8]}",
                    params=MessageSendParams(
                        message=Message(
                            messageId=f"msg_{uuid.uuid4().hex[:8]}",
                            role=Role.user,
                            parts=[TextPart(text=json.dumps(buyer_message))],
                        )
                    ),
                )

                response = await client.send_message(request)
                dumped = response.model_dump(mode="json")
                seller_message = _extract_first_seller_envelope(dumped)
                last_seller = seller_message

                print(f"  [A2A] Response received — task completed")

                _turn_box(
                    agent="seller",
                    round_num=seller_message["round"],
                    msg_type=seller_message["message_type"],
                    price=seller_message.get("price"),
                    message=seller_message.get("message", ""),
                    transport="A2A JSON-RPC → SellerAgentADK → MCPToolset",
                    step_mode=step_mode,
                )

                if seller_message["message_type"] == "ACCEPT":
                    status = "agreed"
                    agreed_price = seller_message.get("price")
                elif seller_message["message_type"] == "REJECT":
                    status = "seller_rejected"
                else:
                    status = "negotiating"

                await state.update({
                    "round": seller_message["round"],
                    "status": status,
                    "last_seller_type": seller_message["message_type"],
                    "last_seller_price": seller_message.get("price"),
                    "agreed_price": agreed_price,
                })
                history.append({
                    "round": seller_message["round"],
                    "agent": "seller",
                    "type": seller_message["message_type"],
                    "price": seller_message.get("price"),
                })

                if status != "negotiating":
                    break

            if status == "negotiating":
                status = "deadlocked"
                await state.update({"status": status})

            # ── Results ───────────────────────────────────────────────────────
            width = 65
            print("\n" + "╔" + "═" * (width - 2) + "╗")
            title = "A2A NEGOTIATION COMPLETE"
            pad = (width - 2 - len(title)) // 2
            print("║" + " " * pad + title + " " * (width - 2 - pad - len(title)) + "║")
            print("╚" + "═" * (width - 2) + "╝")

            outcome_map = {
                "agreed": "DEAL REACHED",
                "buyer_walked": "BUYER WALKED AWAY",
                "deadlocked": "DEADLOCK — MAX ROUNDS",
                "seller_rejected": "SELLER REJECTED",
            }
            print(f"\n  Outcome:   {outcome_map.get(status, status.upper())}")
            if agreed_price:
                savings = 485_000 - agreed_price
                print(f"  Listed:    $485,000")
                print(f"  Agreed:    ${agreed_price:,.0f}")
                print(f"  Saved:     ${savings:,.0f}")

            if history:
                print(f"\n  {'Rnd':>3}  {'Agent':>8}  {'Type':>16}  {'Price':>12}")
                print("  " + "─" * 46)
                for entry in history:
                    price_str = f"${entry['price']:,.0f}" if entry.get("price") else "—"
                    print(f"  {entry['round']:>3}  {entry['agent']:>8}  {entry['type']:>16}  {price_str:>12}")

            current = await state.read_state()
            print(f"\n  ADK session state (InMemorySessionService):")
            for k, v in current.items():
                if v is not None and k not in ("max_rounds",):
                    print(f"    {k}: {v}")

            print("\n" + "╔" + "═" * (width - 2) + "╗")
            print("║  What just happened:                                          ║")
            print("║    BuyerAgentADK ran GPT-4o with MCPToolset (auto tool calls) ║")
            print("║    Each turn sent over HTTP as A2A JSON-RPC message/send      ║")
            print("║    Seller is a separate process — could be any machine        ║")
            print("║    Agent Card enabled discovery — no hardcoded seller config  ║")
            print("╚" + "═" * (width - 2) + "╝")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (ValueError, ValidationError) as error:
        print(f"ERROR: {error}")
        raise SystemExit(1)
