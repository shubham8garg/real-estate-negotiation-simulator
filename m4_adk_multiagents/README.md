# Module 4 — True A2A Protocol (`m4_adk_multiagents`)

**Requires:** `GOOGLE_API_KEY` (free — get it at https://aistudio.google.com)

This module shows what production multi-agent systems look like: two agents running as **independent HTTP services**, communicating over the A2A protocol standard.

---

## What this module teaches

In Module 3, the buyer and seller were both Python objects in the same process. The buyer called the seller like a function.

Module 4 changes that fundamental assumption:

| | Module 3 | Module 4 |
|---|---|---|
| Where agents run | Same Python process | Separate HTTP servers |
| How they communicate | Shared LangGraph state dict | A2A JSON-RPC over HTTP |
| Agent discovery | Hardcoded imports | Agent Card at `/.well-known/agent-card.json` |
| LLM | GPT-4o (OpenAI) | Gemini 2.0 Flash (Google, free) |
| Tool framework | Manual MCP calls | ADK `MCPToolset` (auto tool-use) |

This is what you'd build if the buyer and seller were owned by **different teams** — or even different companies.

---

## File breakdown

### `a2a_protocol_seller_server.py` — The A2A seller server *(start here)*

This file turns the seller agent into a real HTTP server. Any A2A-compatible client can connect to it — it doesn't need to be Python or even know that ADK is running underneath.

**What it does:**
- Exposes an Agent Card at `GET /.well-known/agent-card.json`
  - The card describes what the agent does, what inputs it accepts, what it returns
  - Any client fetches this first to discover the agent's capabilities
- Accepts `POST /` with A2A `message/send` JSON-RPC requests
- Runs the ADK seller agent (`seller_adk.py`) to generate a response
- Returns the counter-offer as an A2A task result

**The task lifecycle:**

```
client sends message
    -> task status: "submitted"
    -> SellerADKA2AExecutor.execute() runs
    -> task status: "working"
    -> SellerAgentADK responds (Gemini + MCP)
    -> task status: "completed"
    -> client receives counter-offer
```

### `a2a_protocol_buyer_client_demo.py` — The A2A buyer client *(pair with seller server)*

This file is the buyer's side: it makes an offer and sends it to the seller server over the A2A protocol.

**Three-step flow:**

```python
# Step 1: Buyer ADK agent makes an offer (Gemini + MCP, same as always)
async with BuyerAgentADK(...) as buyer:
    offer = await buyer.make_initial_offer()

# Step 2: Discover the seller — no hardcoded knowledge
resolver = A2ACardResolver(base_url=seller_url)
card = await resolver.get_agent_card()   # GET /.well-known/agent-card.json
client = A2AClient(agent_card=card)

# Step 3: Send the offer as an A2A message
response = await client.send_message(request)   # POST / (message/send)
```

The buyer doesn't import the seller's code. It doesn't know how the seller is built. It only knows the seller's URL and what the Agent Card says.

---

### `buyer_adk.py` — Buyer agent (Google ADK + Gemini)

The buyer agent, rebuilt with Google ADK instead of OpenAI.

**The key difference from Module 3:**
- In Module 3, the buyer manually called MCP tools then passed results to GPT-4o
- Here, `MCPToolset` gives Gemini direct access to MCP tools — Gemini decides when to call them autonomously

```python
pricing_toolset = MCPToolset(connection_params=StdioConnectionParams(...))
tools = await pricing_toolset.get_tools()

self._agent = LlmAgent(
    model="gemini-2.0-flash",
    tools=tools,    # Gemini calls these when it decides it needs market data
)
```

### `seller_adk.py` — Seller agent (Google ADK + Gemini)

Same pattern as the buyer, but connects to **two** MCP toolsets: pricing + inventory.

```python
all_tools = list(pricing_tools) + list(inventory_tools)
```

The seller has access to `get_minimum_acceptable_price` — the buyer does not. Same information asymmetry as Module 2, now running in a real networked setup.

### `messaging_adk.py` — Response parsing + session state

Gemini returns text. This file converts that text into structured `ADKNegotiationMessage` objects.

It uses four fallback strategies (in order):
1. Parse the response directly as JSON
2. Find a JSON block inside markdown code fences
3. Find the first `{...}` in the response
4. Extract key:value pairs with regex

If all four fail, it falls back to defaults. This is defense-in-depth for LLM output parsing.

### `adk_a2a_types.py` — Module 4 message schema

Pydantic models (`ADKNegotiationMessage`, `ADKNegotiationPayload`) used by Module 4.

Kept separate from Module 3's `negotiation_types.py` so the two modules are independent — you can read one without the other.

---

## How to run

**You need two terminals.**

```bash
# Terminal 1 — start the seller A2A server
python m4_adk_multiagents/a2a_protocol_seller_server.py --port 9102
# You should see: "A2A seller server listening at http://127.0.0.1:9102"

# Terminal 2 — run the buyer client (after the server is up)
python m4_adk_multiagents/a2a_protocol_buyer_client_demo.py --seller-url http://127.0.0.1:9102
```

**What to expect:**
- Terminal 1: Server starts, waits. When the buyer connects, you'll see the Gemini + MCP activity
- Terminal 2: Buyer makes an offer via ADK, sends it over HTTP, receives counter-offer
- Final output shows the offer sent and the seller's structured JSON response

---

## Bonus demos (`bonus/` folder)

These are not core teaching — they're extras for learners who want to explore more.

```bash
# Same ADK agents, coordinated in-process (no network, no A2A transport)
# Architecturally equivalent to Module 3, but with Gemini + ADK instead of GPT-4o + LangGraph
python m4_adk_multiagents/bonus/main_adk_multiagent.py

# ADK's LoopAgent — native loop orchestration without a manual for loop
python m4_adk_multiagents/bonus/adk_orchestrator_agents_demo.py --check    # no API key needed
python m4_adk_multiagents/bonus/adk_orchestrator_agents_demo.py --run --max-iterations 3
```

---

## Quick mental model

- If you want to understand A2A (core teaching), start with `a2a_protocol_seller_server.py` and `a2a_protocol_buyer_client_demo.py`.
- If you want to understand how ADK agents work internally, read `buyer_adk.py` and `seller_adk.py`.
- If you're curious how Gemini output gets turned into structured messages, look at `messaging_adk.py`.
- `bonus/` is purely optional — skip it if you're short on time.

---

## A2A in one diagram

```
Terminal 2 (buyer)                          Terminal 1 (seller)
──────────────────                          ──────────────────────────
BuyerAgentADK                               a2a_protocol_seller_server.py
  Gemini + MCP                                FastAPI app
  make_initial_offer()                          GET /.well-known/agent-card.json
                                               POST / (message/send)
                                                  |
A2ACardResolver                                   v
  GET /.well-known/ ──────────────────────> returns Agent Card
  agent-card.json

A2AClient                                   SellerADKA2AExecutor
  send_message() ─────────────────────────> execute()
  (HTTP POST /)                                SellerAgentADK
                                               Gemini + MCP (pricing + inventory)
                                               responds with counter-offer

  receives response <───────────────────── updater.complete(counter_offer)
```
