"""
True A2A Protocol Seller Server (ADK + OpenAI)
==============================================
Runs a seller agent as an A2A protocol server using `a2a-sdk`.

This is a true networked Agent-to-Agent endpoint:
- Exposes an Agent Card at `/.well-known/agent-card.json`
- Accepts `message/send` requests over A2A JSON-RPC
- Uses ADK seller logic to produce responses

Run:
  python m4_adk_multiagents/a2a_protocol_seller_server.py --port 9102
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AFastAPIApplication
from a2a.server.events.event_queue import EventQueue
from a2a.server.events.in_memory_queue_manager import InMemoryQueueManager
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentProvider, AgentSkill, TextPart
from pydantic import BaseModel, Field, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Load OPENAI_API_KEY and other local vars from repo-root .env.
load_dotenv(REPO_ROOT / ".env")

from m4_adk_multiagents.seller_adk import SellerAgentADK


class BuyerEnvelope(BaseModel):
    # Contract the server expects from buyer side over HTTP A2A.
    session_id: str
    round: int
    from_agent: str
    to_agent: str
    message_type: str
    price: float | None = None
    message: str
    conditions: list[str] = Field(default_factory=list)
    closing_timeline_days: int | None = None
    in_reply_to: str | None = None


class SellerSessionRegistry:
    # Reuses one SellerAgentADK instance per session_id for multi-turn continuity.
    def __init__(self):
        self._agents: dict[str, SellerAgentADK] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, session_id: str) -> SellerAgentADK:
        async with self._lock:
            existing = self._agents.get(session_id)
            if existing is not None:
                return existing

            # Lazily create seller ADK agent the first time this session appears.
            agent = SellerAgentADK(session_id=f"seller_a2a_{session_id}")
            await agent.__aenter__()
            self._agents[session_id] = agent
            return agent

    async def close_all(self) -> None:
        # Graceful server shutdown: close all managed ADK agent contexts.
        async with self._lock:
            agents = list(self._agents.values())
            self._agents.clear()
        for agent in agents:
            try:
                await agent.__aexit__(None, None, None)
            except Exception:
                pass


SESSION_REGISTRY = SellerSessionRegistry()


def _build_agent_card(base_url: str) -> AgentCard:
    # Agent Card is the discovery contract returned at /.well-known/agent-card.json.
    return AgentCard(
        name="adk_seller_a2a_server",
        description="ADK-backed seller agent exposed via A2A protocol",
        url=base_url,
        version="1.0.0",
        protocolVersion="0.3.0",
        preferredTransport="JSONRPC",
        defaultInputModes=["text/plain"],
        defaultOutputModes=["text/plain"],
        capabilities=AgentCapabilities(streaming=False, pushNotifications=False),
        skills=[
            AgentSkill(
                id="real_estate_seller_negotiation",
                name="Real Estate Seller Negotiation",
                description="Responds to buyer offers with ADK-generated counter-offers or acceptance",
                tags=["real_estate", "negotiation", "seller", "adk", "a2a"],
                examples=["Buyer offers $438,000 with 45-day close"],
                inputModes=["text/plain"],
                outputModes=["text/plain"],
            )
        ],
        provider=AgentProvider(
            organization="Negotiation Workshop",
            url="https://example.local/negotiation-workshop",
        ),
    )


class SellerADKA2AExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # TaskUpdater emits submitted/working/completed task events for A2A clients.
        updater = TaskUpdater(event_queue, task_id=context.task_id, context_id=context.context_id)

        await updater.start_work()

        incoming_text = context.get_user_input().strip()

        try:
            # Validate incoming JSON text as a buyer envelope contract.
            parsed_buyer = BuyerEnvelope.model_validate(json.loads(incoming_text))

            # One-turn processing over HTTP; continuity is preserved per session_id.
            seller = await SESSION_REGISTRY.get_or_create(parsed_buyer.session_id)
            response_payload: dict[str, Any] = await seller.respond_to_offer_envelope(
                parsed_buyer.model_dump(mode="json")
            )

            agent_message = updater.new_agent_message(
                parts=[TextPart(text=json.dumps(response_payload))],
                metadata={"protocol": "a2a", "runtime": "adk-openai"},
            )
            # Complete task with one final structured response payload.
            await updater.complete(agent_message)

        except (json.JSONDecodeError, ValidationError) as error:
            # Contract violations are returned as task failures with explicit message.
            agent_message = updater.new_agent_message(
                parts=[TextPart(text=f"ERROR: Invalid buyer envelope. {error}")],
                metadata={"protocol": "a2a", "runtime": "adk-openai", "status": "error"},
            )
            await updater.failed(message=agent_message)
        except Exception as error:
            # Surface failures to client as task-failed responses (not silent drops).
            agent_message = updater.new_agent_message(
                parts=[TextPart(text=f"ERROR: {error}")],
                metadata={"protocol": "a2a", "runtime": "adk-openai", "status": "error"},
            )
            await updater.failed(message=agent_message)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, task_id=context.task_id, context_id=context.context_id)
        cancel_message = updater.new_agent_message(
            parts=[TextPart(text="Request cancelled by client")],
            metadata={"protocol": "a2a", "runtime": "adk-openai", "status": "cancelled"},
        )
        await updater.cancel(message=cancel_message)


def _print_startup_banner(base_url: str) -> None:
    width = 65
    print("\n" + "╔" + "═" * (width - 2) + "╗")
    title = "A2A Seller Server — ADK + OpenAI"
    pad = (width - 2 - len(title)) // 2
    print("║" + " " * pad + title + " " * (width - 2 - pad - len(title)) + "║")
    print("╚" + "═" * (width - 2) + "╝")
    print(f"""
  Module:    m4_adk_multiagents/a2a_protocol_seller_server.py
  Stack:     ADK SellerAgent + OpenAI GPT-4o + 2 MCP servers
  Protocol:  A2A (Agent-to-Agent) over HTTP JSON-RPC

  ── WHAT THIS SERVER EXPOSES ──────────────────────────────

  Agent Card (discovery):
    GET  {base_url}/.well-known/agent-card.json
         → Returns: name, skills, capabilities, protocol version
         → Buyers fetch this FIRST before sending any message

  Message endpoint (JSON-RPC):
    POST {base_url}/
         Method: message/send
         Input:  BuyerEnvelope JSON (session_id, round, price, message)
         Output: SellerEnvelope JSON (counter_price, message, accept/reject)

  ── A2A PROTOCOL FLOW ─────────────────────────────────────

  1. Buyer fetches Agent Card  →  GET /.well-known/agent-card.json
  2. Buyer sends offer         →  POST / (JSON-RPC message/send)
  3. Server validates envelope →  BuyerEnvelope.model_validate(json)
  4. SellerAgentADK executes   →  GPT-4o + 3 MCP tool calls
  5. Server returns counter    →  SellerEnvelope JSON in TextPart

  ── INFORMATION ASYMMETRY ─────────────────────────────────

  This seller has BOTH MCP servers:
    Pricing server:   get_market_price, calculate_discount
    Inventory server: get_inventory_level, get_minimum_acceptable_price

  The buyer orchestrator only has pricing server tools.
  This enforces seller's floor price stays confidential.

  ── HOW TO CONNECT ────────────────────────────────────────

  In another terminal, run the orchestrator:
    python m4_adk_multiagents/a2a_protocol_http_orchestrator.py \\
           --seller-url {base_url} --demo

  ── SERVER READY ─────────────────────────────────────────
""")


async def main() -> None:
    parser = argparse.ArgumentParser(description="True A2A seller server (ADK + OpenAI)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9102)
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set. Set it before starting A2A seller server.")
        raise SystemExit(1)

    base_url = f"http://{args.host}:{args.port}"
    _print_startup_banner(base_url)

    card = _build_agent_card(base_url)

    handler = DefaultRequestHandler(
        agent_executor=SellerADKA2AExecutor(),
        task_store=InMemoryTaskStore(),
        queue_manager=InMemoryQueueManager(),
    )

    app_builder = A2AFastAPIApplication(agent_card=card, http_handler=handler)
    app = app_builder.build(agent_card_url="/.well-known/agent-card.json", rpc_url="/")

    import uvicorn

    config = uvicorn.Config(app=app, host=args.host, port=args.port, log_level="warning")
    server = uvicorn.Server(config)
    print(f"  Listening at {base_url}  (Ctrl+C to stop)")
    print()
    try:
        await server.serve()
    finally:
        await SESSION_REGISTRY.close_all()


if __name__ == "__main__":
    asyncio.run(main())
