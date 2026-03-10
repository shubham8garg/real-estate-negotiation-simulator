# Module 3 — Agents + A2A + LangGraph (`m3_langgraph_multiagents`)

This folder is the **simple/OpenAI version** of the negotiation system.
Think of it in 3 layers:

1. **Message protocol layer** → `a2a_simple.py`
2. **Agent logic layer** → `buyer_simple.py`, `seller_simple.py`
3. **Workflow/orchestration layer** → `langgraph_flow.py`

---

## What each file is for

- `a2a_simple.py`
  - Defines the `A2AMessage` schema (what an offer/counter/accept message looks like)
  - Defines `A2AMessageBus` (in-memory routing between buyer/seller)
  - Includes helper constructors like `create_offer()` and `create_counter_offer()`

- `buyer_simple.py`
  - Buyer agent implementation (GPT-4o)
  - Calls pricing MCP tools
  - Produces A2A messages for the seller

- `seller_simple.py`
  - Seller agent implementation (GPT-4o)
  - Calls pricing + inventory MCP tools
  - Produces A2A messages for the buyer

- `langgraph_flow.py`
  - Runs the full negotiation loop as a LangGraph state machine
  - Controls turns, termination, and status transitions
  - Uses both buyer/seller agents + A2A messages

---

## Quick mental model

- If you are confused about message fields/types, start with `a2a_simple.py`.
- If you want to see buyer/seller decision logic, open `buyer_simple.py` and `seller_simple.py`.
- If you want to see how everything connects into a full run, open `langgraph_flow.py`.

---

## Typical run path for Module 3

Entry point: `main_simple.py`

`main_simple.py`
→ `m3_langgraph_multiagents/langgraph_flow.py`
→ `m3_langgraph_multiagents/buyer_simple.py` + `m3_langgraph_multiagents/seller_simple.py`
→ `m3_langgraph_multiagents/a2a_simple.py` (message schema/bus)

---

## Verify only A2A logic (no API keys)

```bash
pytest tests/test_a2a.py -v
```
