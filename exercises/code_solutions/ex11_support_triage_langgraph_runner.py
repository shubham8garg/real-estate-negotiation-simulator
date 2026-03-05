"""
Exercise 11 solution: Customer Support Triage (LangGraph).

Run:
    python exercises/code_solutions/ex11_support_triage_langgraph_runner.py
"""

import asyncio
import json
import operator
from typing import Annotated

from langgraph.graph import END, StateGraph
from openai import AsyncOpenAI
from typing_extensions import TypedDict

client = AsyncOpenAI()


class SupportState(TypedDict):
    ticket: str
    classification: str
    urgency: str
    assigned_to: str
    specialist_response: str
    final_response: str
    history: Annotated[list[dict], operator.add]


async def triage_node(state: SupportState) -> dict:
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a customer support triage agent. "
                    "Return JSON with classification (billing|technical|general), "
                    "urgency (low|medium|high), and reasoning."
                ),
            },
            {"role": "user", "content": f"Classify this ticket:\n\n{state['ticket']}"},
        ],
        response_format={"type": "json_object"},
    )
    payload = json.loads(response.choices[0].message.content)
    classification = payload.get("classification", "general").strip().lower()
    urgency = payload.get("urgency", "low").strip().lower()
    if classification not in ("billing", "technical", "general"):
        classification = "general"
    if urgency not in ("low", "medium", "high"):
        urgency = "low"
    return {
        "classification": classification,
        "urgency": urgency,
        "history": [{"step": "triage", "classification": classification, "urgency": urgency}],
    }


async def billing_node(state: SupportState) -> dict:
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "You are a billing specialist. Write a 2-3 paragraph empathetic response.",
            },
            {"role": "user", "content": f"Customer support ticket:\n\n{state['ticket']}"},
        ],
    )
    text = response.choices[0].message.content
    return {
        "assigned_to": "billing",
        "specialist_response": text,
        "history": [{"step": "billing", "chars": len(text)}],
    }


async def technical_node(state: SupportState) -> dict:
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "You are a technical specialist. Provide numbered troubleshooting steps.",
            },
            {"role": "user", "content": f"Customer support ticket:\n\n{state['ticket']}"},
        ],
    )
    text = response.choices[0].message.content
    return {
        "assigned_to": "technical",
        "specialist_response": text,
        "history": [{"step": "technical", "chars": len(text)}],
    }


async def general_node(state: SupportState) -> dict:
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": "You are a friendly general support agent. Be concise and helpful.",
            },
            {"role": "user", "content": f"Customer support ticket:\n\n{state['ticket']}"},
        ],
    )
    text = response.choices[0].message.content
    return {
        "assigned_to": "general",
        "specialist_response": text,
        "history": [{"step": "general", "chars": len(text)}],
    }


async def format_response_node(state: SupportState) -> dict:
    urgency_tag = {"high": "[!]", "medium": "[~]", "low": "[ ]"}.get(state.get("urgency", "low"), "[ ]")
    final = (
        "SUPPORT TICKET RESPONSE\n"
        + "=" * 40
        + "\n"
        + f"Classified: {state.get('classification', 'general').upper()}\n"
        + f"Urgency:    {urgency_tag} {state.get('urgency', 'low').upper()}\n"
        + f"Handled by: {state.get('assigned_to', 'support').title()} Team\n"
        + "-" * 40
        + "\n\n"
        + state.get("specialist_response", "")
    )
    return {"final_response": final, "history": [{"step": "format_response", "done": True}]}


def route_after_triage(state: SupportState) -> str:
    value = state.get("classification", "general")
    return value if value in ("billing", "technical", "general") else "general"


def build_support_graph():
    workflow = StateGraph(SupportState)
    workflow.add_node("triage", triage_node)
    workflow.add_node("billing", billing_node)
    workflow.add_node("technical", technical_node)
    workflow.add_node("general", general_node)
    workflow.add_node("format_response", format_response_node)
    workflow.set_entry_point("triage")
    workflow.add_conditional_edges(
        "triage",
        route_after_triage,
        {"billing": "billing", "technical": "technical", "general": "general"},
    )
    workflow.add_edge("billing", "format_response")
    workflow.add_edge("technical", "format_response")
    workflow.add_edge("general", "format_response")
    workflow.add_edge("format_response", END)
    return workflow.compile()


async def handle_ticket(ticket: str) -> str:
    app = build_support_graph()
    result = await app.ainvoke({"ticket": ticket, "history": []})
    return result["final_response"]


if __name__ == "__main__":
    tickets = [
        "I was charged twice for my subscription this month. Please refund the extra charge.",
        "The app crashes every time I upload a file larger than 10MB.",
        "How do I update the email address on my account?",
    ]

    async def run() -> None:
        for index, ticket in enumerate(tickets, start=1):
            print(f"\nTicket {index}: {ticket}")
            print(await handle_ticket(ticket))

    asyncio.run(run())
