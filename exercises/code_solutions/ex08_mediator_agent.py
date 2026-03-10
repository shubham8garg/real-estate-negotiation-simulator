import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from openai import AsyncOpenAI
from m3_langgraph_multiagents.a2a_simple import A2AMessage

MEDIATOR_SYSTEM_PROMPT = """You are a neutral real estate mediator.
Your job is to find a fair compromise when buyer and seller cannot agree.

Response format (JSON):
{
    \"proposed_price\": <integer>,
    \"reasoning\": \"<why this is fair to both parties>\",
    \"message_to_both\": \"<neutral message explaining the proposal>\"
}"""


class MediatorAgent:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    async def propose_settlement(
        self,
        buyer_final_offer: float,
        seller_final_counter: float,
        history: list[dict],
        round_num: int,
    ) -> A2AMessage:
        midpoint = (buyer_final_offer + seller_final_counter) / 2
        user_message = f"""
Negotiation has stalled. Propose a fair settlement.

Buyer's position: ${buyer_final_offer:,.0f}
Seller's position: ${seller_final_counter:,.0f}
Gap: ${seller_final_counter - buyer_final_offer:,.0f}
Mathematical midpoint: ${midpoint:,.0f}

Full history:
{json.dumps(history, indent=2)}
"""
        response = await self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": MEDIATOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
        )
        decision = json.loads(response.choices[0].message.content)
        proposed = float(decision.get("proposed_price", midpoint))
        return A2AMessage(
            session_id=self.session_id,
            from_agent="buyer",
            to_agent="seller",
            round=round_num,
            message_type="OFFER",
            payload={
                "price": proposed,
                "message": f"[MEDIATOR PROPOSAL] {decision.get('message_to_both', '')}",
                "conditions": ["Mediator-proposed settlement — accept or decline"],
            },
        )


async def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set. Add it to .env or environment before running ex08.")
        raise SystemExit(1)

    history = [
        {"round": 1, "agent": "buyer", "price": 425000},
        {"round": 1, "agent": "seller", "price": 477000},
        {"round": 2, "agent": "buyer", "price": 438000},
        {"round": 2, "agent": "seller", "price": 465000},
    ]
    mediator = MediatorAgent(session_id="med_demo_001")
    proposal = await mediator.propose_settlement(438000, 465000, history, 3)
    print(proposal)


if __name__ == "__main__":
    asyncio.run(main())
