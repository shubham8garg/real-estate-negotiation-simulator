# Module 4 — Google ADK Version (`m4_adk_multiagents`)

This folder is the **Google ADK + Gemini version** of the negotiation system.
Compared to Module 3, the key difference is that ADK `Runner` + sessions handle each agent turn, while an orchestrator mediates exchanges.

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
  - Parses Gemini text into `A2AMessage`
  - Formats incoming message context for the other agent
  - Tracks session-level negotiation state (`NegotiationSession`)

- `a2a_adk_demo.py`
  - Focused ADK A2A transcript demo (round-by-round)
  - Best file to run if you only want to understand ADK-side A2A mediation

---

## Quick mental model

- If you want ADK agent setup details, start with `buyer_adk.py` and `seller_adk.py`.
- If you want to understand “how messages move” in ADK, read `messaging_adk.py`.
- If you want a clean demo run, use `a2a_adk_demo.py`.

---

## Typical run paths for Module 4

Full negotiation app:

`main_adk.py`
→ `m4_adk_multiagents/buyer_adk.py` + `m4_adk_multiagents/seller_adk.py`
→ `m4_adk_multiagents/messaging_adk.py`

Focused ADK A2A demo:

`m4_adk_multiagents/a2a_adk_demo.py`
→ `m4_adk_multiagents/buyer_adk.py` + `m4_adk_multiagents/seller_adk.py`
→ `m4_adk_multiagents/messaging_adk.py`

---

## Run commands

```bash
python main_adk.py
python m4_adk_multiagents/a2a_adk_demo.py --rounds 3
```
