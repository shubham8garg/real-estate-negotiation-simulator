"""
True A2A Protocol Buyer Client Demo (Google ADK + A2A SDK)
==========================================================
Uses a Google ADK buyer agent to create an offer, then sends that offer to
an A2A protocol seller server over `a2a-sdk`.

Run (terminal 1):
  python m4_adk_multiagents/a2a_protocol_seller_server.py --port 9102

Run (terminal 2):
  python m4_adk_multiagents/a2a_protocol_buyer_client_demo.py --seller-url http://127.0.0.1:9102
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import httpx
from a2a.client import A2AClient, A2ACardResolver
from a2a.types import Message, MessageSendParams, Role, SendMessageRequest, TextPart

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from m4_adk_multiagents.buyer_adk import BuyerAgentADK


def _extract_texts(obj):
    texts = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "text" and isinstance(v, str):
                texts.append(v)
            else:
                texts.extend(_extract_texts(v))
    elif isinstance(obj, list):
        for item in obj:
            texts.extend(_extract_texts(item))
    return texts


async def main() -> None:
    parser = argparse.ArgumentParser(description="True A2A buyer client demo")
    parser.add_argument("--seller-url", default="http://127.0.0.1:9102")
    args = parser.parse_args()

    if not os.environ.get("GOOGLE_API_KEY"):
        print("GOOGLE_API_KEY is not set. Set it before running this demo.")
        raise SystemExit(1)

    async with BuyerAgentADK(session_id=f"buyer_a2a_{uuid.uuid4().hex[:8]}") as buyer:
        offer = await buyer.make_initial_offer()

    offer_text = (
        f"Buyer offer: ${offer.payload.price:,.0f}. "
        f"Type={offer.message_type}. "
        f"Message={offer.payload.message}"
    )

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        resolver = A2ACardResolver(httpx_client=http_client, base_url=args.seller_url)
        card = await resolver.get_agent_card()
        client = A2AClient(httpx_client=http_client, agent_card=card)

        request = SendMessageRequest(
            id=f"req_{uuid.uuid4().hex[:8]}",
            params=MessageSendParams(
                message=Message(
                    messageId=f"msg_{uuid.uuid4().hex[:8]}",
                    role=Role.user,
                    parts=[TextPart(text=offer_text)],
                )
            ),
        )

        response = await client.send_message(request)

    dumped = response.model_dump(mode="json")
    texts = _extract_texts(dumped)

    print("\n=== TRUE A2A DEMO RESULT ===")
    print(f"Seller URL: {args.seller_url}")
    print(f"Buyer offer sent: {offer_text}")
    print("Response payload:")
    print(json.dumps(dumped, indent=2))
    if texts:
        print("\nExtracted text parts:")
        for text in texts:
            print(f"- {text}")


if __name__ == "__main__":
    asyncio.run(main())
