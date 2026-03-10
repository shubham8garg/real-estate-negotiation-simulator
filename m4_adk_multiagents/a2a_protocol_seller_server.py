"""
True A2A Protocol Seller Server (Google ADK)
===========================================
Runs a seller agent as an A2A protocol server using `a2a-sdk`.

This is a true networked Agent-to-Agent endpoint:
- Exposes an Agent Card at `/.well-known/agent-card.json`
- Accepts `message/send` requests over A2A JSON-RPC
- Uses Google ADK seller logic to produce responses

Run:
  python m4_adk_multiagents/a2a_protocol_seller_server.py --port 9102
"""

import argparse
import asyncio
import json
import os
import re
import sys
import uuid
from pathlib import Path

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2ARESTFastAPIApplication
from a2a.server.events.event_queue import EventQueue
from a2a.server.events.in_memory_queue_manager import InMemoryQueueManager
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentProvider, AgentSkill, Role, TextPart

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from m4_adk_multiagents.adk_a2a_types import create_offer
from m4_adk_multiagents.seller_adk import SellerAgentADK


def _extract_price(text: str) -> float | None:
    if not text:
        return None
    match = re.search(r"\$?\s*([0-9]{2,3}(?:,[0-9]{3})+|[0-9]{5,7})", text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _build_agent_card(base_url: str) -> AgentCard:
    return AgentCard(
        name="adk_seller_a2a_server",
        description="Google ADK-backed seller agent exposed via A2A protocol",
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
        buyer_price = _extract_price(incoming_text) or 425_000.0

        buyer_message = create_offer(
            session_id=f"a2a_seller_{uuid.uuid4().hex[:8]}",
            round_num=1,
            price=buyer_price,
            message=incoming_text or f"Buyer offer at ${buyer_price:,.0f}",
        )

        try:
            async with SellerAgentADK(session_id=f"seller_a2a_{uuid.uuid4().hex[:8]}") as seller:
                seller_reply = await seller.respond_to_offer(buyer_message)

            response_payload = {
                "message_type": seller_reply.message_type,
                "price": seller_reply.payload.price,
                "message": seller_reply.payload.message,
                "conditions": seller_reply.payload.conditions,
                "closing_timeline_days": seller_reply.payload.closing_timeline_days,
                "session_id": seller_reply.session_id,
                "in_reply_to": seller_reply.in_reply_to,
            }

            agent_message = updater.new_agent_message(
                parts=[TextPart(text=json.dumps(response_payload))],
                metadata={"protocol": "a2a", "runtime": "google-adk"},
            )
            await updater.complete(agent_message)

        except Exception as error:
            agent_message = updater.new_agent_message(
                parts=[TextPart(text=f"ERROR: {error}")],
                metadata={"protocol": "a2a", "runtime": "google-adk", "status": "error"},
            )
            await updater.failed(message=agent_message)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        updater = TaskUpdater(event_queue, task_id=context.task_id, context_id=context.context_id)
        cancel_message = updater.new_agent_message(
            parts=[TextPart(text="Request cancelled by client")],
            metadata={"protocol": "a2a", "runtime": "google-adk", "status": "cancelled"},
        )
        await updater.cancel(message=cancel_message)


async def main() -> None:
    parser = argparse.ArgumentParser(description="True A2A seller server (Google ADK)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9102)
    args = parser.parse_args()

    if not os.environ.get("GOOGLE_API_KEY"):
        print("GOOGLE_API_KEY is not set. Set it before starting A2A seller server.")
        raise SystemExit(1)

    base_url = f"http://{args.host}:{args.port}"
    card = _build_agent_card(base_url)

    handler = DefaultRequestHandler(
        agent_executor=SellerADKA2AExecutor(),
        task_store=InMemoryTaskStore(),
        queue_manager=InMemoryQueueManager(),
    )

    app_builder = A2ARESTFastAPIApplication(agent_card=card, http_handler=handler)
    app = app_builder.build(agent_card_url="/.well-known/agent-card.json", rpc_url="/")

    import uvicorn

    print(f"A2A seller server listening at {base_url}")
    print(f"Agent card: {base_url}/.well-known/agent-card.json")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    asyncio.run(main())
