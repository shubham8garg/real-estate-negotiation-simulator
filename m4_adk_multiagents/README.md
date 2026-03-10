# Module 4 — Google ADK Version (`m4_adk_multiagents`)

This folder is the **Google ADK + Gemini version** of the negotiation system.
North star for this module: **true protocol A2A** (networked agent-to-agent) with ADK agents behind each endpoint.

- Module 3: pure LangGraph state orchestration
- Module 4: pure A2A protocol transport

---

## What each file is for

- `buyer_adk.py`
  - Buyer agent built with ADK `LlmAgent`
  - Uses MCPToolset (pricing server)
  - Produces structured buyer-side A2A messages

- `seller_adk.py`
  - Seller agent built with ADK `LlmAgent`
  - Uses MCPToolset (pricing + inventory servers)
  - Produces structured seller-side A2A messages

- `messaging_adk.py`
  - ADK messaging adapter layer
  - Parses Gemini text into `ADKNegotiationMessage`
  - Formats incoming message context for the other agent
  - Tracks session-level negotiation state (`NegotiationSession`)

- `adk_a2a_types.py`
  - ADK-native message schema + helpers used only by Module 4
  - Keeps Module 4 independent from Module 3 message types

- `a2a_protocol_seller_server.py`
  - True networked A2A protocol server (A2A SDK) exposing an ADK seller agent
  - Publishes agent card + handles `message/send` over protocol transport

- `a2a_protocol_buyer_client_demo.py`
  - True networked A2A protocol client demo (A2A SDK)
  - Uses ADK buyer output and sends it to the protocol seller endpoint

- `adk_orchestrator_agents_demo.py`
  - Compact ADK orchestrator demo using only `buyer_agent` + `seller_agent`
  - Uses `LoopAgent` as the orchestration pattern for iterative negotiation rounds

---

## Quick mental model

- If you want true protocol A2A, start with `a2a_protocol_seller_server.py` and `a2a_protocol_buyer_client_demo.py`.
- If you want ADK agent setup details, read `buyer_adk.py` and `seller_adk.py`.

---

## Typical run path for Module 4 (true A2A)

Terminal 1:

`m4_adk_multiagents/a2a_protocol_seller_server.py`
→ `m4_adk_multiagents/seller_adk.py`

Terminal 2:

`m4_adk_multiagents/a2a_protocol_buyer_client_demo.py`
→ `m4_adk_multiagents/buyer_adk.py`

---

## Run commands

```bash
# True protocol A2A (terminal 1)
python m4_adk_multiagents/a2a_protocol_seller_server.py --port 9102

# True protocol A2A (terminal 2)
python m4_adk_multiagents/a2a_protocol_buyer_client_demo.py --seller-url http://127.0.0.1:9102

# Optional ADK runner (not protocol transport)
python m4_adk_multiagents/main_adk_multiagent.py

# Optional ADK orchestrator-agent types demo
python m4_adk_multiagents/adk_orchestrator_agents_demo.py --check
python m4_adk_multiagents/adk_orchestrator_agents_demo.py --run --max-iterations 3
```
