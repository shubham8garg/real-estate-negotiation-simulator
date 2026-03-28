"""
MODULE 4 — EXERCISE 2 SOLUTION: Seller Server with /history Endpoint
=====================================================================
This is a RUNNABLE COPY of a2a_protocol_seller_server.py with the
/history/{session_id} and /sessions REST endpoints added.
The original a2a_protocol_seller_server.py is NOT modified.

WHAT EXERCISE 2 ASKS:
  Add a REST endpoint /history/{session_id} to the seller server
  that returns the agent's internal LLM conversation history as JSON.
  This endpoint coexists with the A2A JSON-RPC endpoint on the same FastAPI app.

THE KEY INSIGHT:
  A2AFastAPIApplication.build() returns a STANDARD FastAPI app.
  You can add any routes to a FastAPI app before the server starts.
  No special A2A knowledge required — it's just FastAPI routing.

SEARCH FOR "EXERCISE 2 SOLUTION" to find the two added route definitions.

HOW TO RUN:
  python m4_adk_multiagents/solution/sol02_seller_server_with_history.py --port 9103

HOW TO TEST:
  Terminal 1 (start this server):
    python m4_adk_multiagents/solution/sol02_seller_server_with_history.py --port 9103

  Terminal 2 (run one round of negotiation):
    python m4_adk_multiagents/a2a_protocol_http_orchestrator.py \\
           --seller-url http://127.0.0.1:9103 --rounds 1

  Terminal 3 (inspect the endpoints):
    curl http://127.0.0.1:9103/sessions
    curl http://127.0.0.1:9103/history/<session_id_from_sessions>
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import HTTPException

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AFastAPIApplication
from a2a.server.events.event_queue import EventQueue
from a2a.server.events.in_memory_queue_manager import InMemoryQueueManager
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentProvider, AgentSkill, TextPart
from pydantic import BaseModel, Field, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

load_dotenv(REPO_ROOT / ".env")

from m4_adk_multiagents.seller_adk import SellerAgentADK


class BuyerEnvelope(BaseModel):
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
    def __init__(self):
        self._agents: dict[str, SellerAgentADK] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, session_id: str) -> SellerAgentADK:
        async with self._lock:
            existing = self._agents.get(session_id)
            if existing is not None:
                return existing

            agent = SellerAgentADK(session_id=f"seller_a2a_{session_id}")
            await agent.__aenter__()
            self._agents[session_id] = agent
            return agent

    async def close_all(self) -> None:
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
    return AgentCard(
        name="adk_seller_a2a_server_with_history",
        description="ADK-backed seller agent with /history observability endpoint",
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
        updater = TaskUpdater(event_queue, task_id=context.task_id, context_id=context.context_id)
        await updater.start_work()

        incoming_text = context.get_user_input().strip()

        try:
            parsed_buyer = BuyerEnvelope.model_validate(json.loads(incoming_text))
            seller = await SESSION_REGISTRY.get_or_create(parsed_buyer.session_id)
            response_payload: dict[str, Any] = await seller.respond_to_offer_envelope(
                parsed_buyer.model_dump(mode="json")
            )

            agent_message = updater.new_agent_message(
                parts=[TextPart(text=json.dumps(response_payload))],
                metadata={"protocol": "a2a", "runtime": "adk-openai"},
            )
            await updater.complete(agent_message)

        except (json.JSONDecodeError, ValidationError) as error:
            agent_message = updater.new_agent_message(
                parts=[TextPart(text=f"ERROR: Invalid buyer envelope. {error}")],
                metadata={"protocol": "a2a", "runtime": "adk-openai", "status": "error"},
            )
            await updater.failed(message=agent_message)
        except Exception as error:
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
    title = "A2A Seller Server — With /history Endpoint (Exercise 2 Solution)"
    pad = (width - 2 - len(title)) // 2
    print("║" + " " * pad + title + " " * (width - 2 - pad - len(title)) + "║")
    print("╚" + "═" * (width - 2) + "╝")
    print(f"""
  Module:    m4_adk_multiagents/solution/sol02_seller_server_with_history.py
  Stack:     ADK SellerAgent + OpenAI GPT-4o + 2 MCP servers
  Protocol:  A2A (Agent-to-Agent) over HTTP JSON-RPC

  ── WHAT THIS SERVER EXPOSES ──────────────────────────────

  Agent Card (discovery):
    GET  {base_url}/.well-known/agent-card.json

  Message endpoint (JSON-RPC):
    POST {base_url}/
         Method: message/send

  ── EXERCISE 2 SOLUTION ENDPOINTS ────────────────────────

    GET  {base_url}/sessions
         Returns: list of active session IDs

    GET  {base_url}/history/{{session_id}}
         Returns: seller's LLM conversation history as JSON

  ── TESTING WORKFLOW ──────────────────────────────────────

  1. Start this server:
       python m4_adk_multiagents/solution/sol02_seller_server_with_history.py --port 9103

  2. Run 1 round of negotiation:
       python m4_adk_multiagents/a2a_protocol_http_orchestrator.py \\
              --seller-url http://127.0.0.1:9103 --rounds 1

  3. List active sessions:
       curl http://127.0.0.1:9103/sessions

  4. Fetch history (use session_id from /sessions):
       curl http://127.0.0.1:9103/history/<session_id>

  ── KEY INSIGHT ───────────────────────────────────────────

  app = app_builder.build(...) returns a STANDARD FastAPI app.
  You can add any routes with @app.get(), @app.post(), etc.
  A2A JSON-RPC (POST /) and REST endpoints coexist on the same app.

  ── SERVER READY ─────────────────────────────────────────
""")


async def main() -> None:
    parser = argparse.ArgumentParser(description="A2A seller server with /history endpoint (Exercise 2 solution)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9103)
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

    # ── EXERCISE 2 SOLUTION: /sessions and /history endpoints ─────────────────
    # KEY INSIGHT: app is a standard FastAPI app. Add any routes here.
    # These routes coexist with the A2A JSON-RPC (POST /) on the same app.
    # No special A2A knowledge required — it's plain FastAPI routing.

    @app.get("/sessions")
    async def list_sessions():
        """List all active negotiation sessions on this server."""
        return {
            "active_sessions": list(SESSION_REGISTRY._agents.keys()),
            "count": len(SESSION_REGISTRY._agents),
        }

    @app.get("/history/{session_id}")
    async def get_session_history(session_id: str):
        """
        Return the seller agent's LLM conversation history for a session.

        SECURITY NOTE (reflection answer for Exercise 2):
        This endpoint exposes the seller's negotiation strategy including
        its price floor reasoning. In production, this must have:
          - Authentication (JWT, API key, OAuth)
          - Authorization (only seller's admin can call /history)
          - Rate limiting (prevent scraping)
          - Content filtering (scrub price floors before returning)

        For this workshop: open for debugging convenience.
        Recognizing this distinction is a production engineering skill.
        """
        agents = SESSION_REGISTRY._agents
        agent = agents.get(session_id)

        if agent is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": f"No session found for '{session_id}'",
                    "active_sessions": list(agents.keys()),
                    "hint": "Call /sessions first to see exact session ID keys",
                },
            )

        history = []
        for msg in getattr(agent, "llm_messages", []):
            if isinstance(msg, dict) and msg.get("role") in ("assistant", "user"):
                history.append({
                    "role": msg["role"],
                    "content": (msg.get("content") or "")[:400],
                })

        return {
            "session_id": session_id,
            "message_count": len(history),
            "history": history,
        }
    # ── End Exercise 2 Solution ───────────────────────────────────────────────

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
