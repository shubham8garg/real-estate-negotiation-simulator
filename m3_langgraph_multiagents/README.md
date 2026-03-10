# Module 3 — Pure LangGraph Multi-Agent Workflow (`m3_langgraph_multiagents`)

This folder is the **simple/OpenAI + LangGraph version** of the negotiation system.
It is intentionally state-driven: buyer and seller nodes communicate through shared
LangGraph `TypedDict` state (not protocol A2A transport).

---

## What each file is for

- `negotiation_types.py`
  - Defines the internal message/status types used by Module 3
  - Keeps node-to-node communication simple and LangGraph-native

- `buyer_simple.py`
  - Buyer agent implementation (GPT-4o)
  - Uses GPT-4o as an MCP planner to choose which pricing MCP tools to invoke each round
  - Produces negotiation message dicts for LangGraph state

- `seller_simple.py`
  - Seller agent implementation (GPT-4o)
  - Uses GPT-4o as an MCP planner to choose which pricing/inventory MCP tools to invoke each round
  - Produces negotiation message dicts for LangGraph state

- `langgraph_flow.py`
  - Runs the full negotiation loop as a LangGraph state machine
  - Controls turns, termination, and status transitions
  - Uses both buyer/seller agents + shared TypedDict state

---

## Quick mental model

- If you are confused about state/message fields, start with `negotiation_types.py`.
- If you want to see buyer/seller decision logic, open `buyer_simple.py` and `seller_simple.py`.
- If you want to see how everything connects into a full run, open `langgraph_flow.py`.

---

## Typical run path for Module 3

Entry point: `m3_langgraph_multiagents/main_langgraph_multiagent.py`

`m3_langgraph_multiagents/main_langgraph_multiagent.py`
→ `m3_langgraph_multiagents/langgraph_flow.py`
→ `m3_langgraph_multiagents/buyer_simple.py` + `m3_langgraph_multiagents/seller_simple.py`
→ `m3_langgraph_multiagents/negotiation_types.py`

Strict planner mode: Module 3 executes only MCP tool calls explicitly selected by the LLM planner for that turn (no automatic fallback tool calls).
