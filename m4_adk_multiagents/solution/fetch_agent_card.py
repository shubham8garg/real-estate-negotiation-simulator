"""
MODULE 4 — EXERCISE 1 SOLUTION: Fetch and Inspect the Agent Card
================================================================
This script demonstrates A2A agent discovery by fetching the seller
server's Agent Card from the well-known discovery URL.

BEFORE RUNNING: Start the seller server in another terminal:
    python m4_adk_multiagents/a2a_protocol_seller_server.py --port 9102

THEN RUN:
    python m4_adk_multiagents/solution/fetch_agent_card.py
    python m4_adk_multiagents/solution/fetch_agent_card.py --fast    (no pauses)
    python m4_adk_multiagents/solution/fetch_agent_card.py --url http://localhost:9102

A2A DISCOVERY CONCEPT:
    Before any session starts, a buyer agent can fetch the seller's
    Agent Card to learn: name, version, skills, capabilities, and
    the URL to send tasks to. This is "zero-config discovery" —
    no shared config file, no manual registration.

    Compare to MCP tool discovery:
    - MCP:  list_tools() over an active session (after connection)
    - A2A:  HTTP GET to /.well-known/agent-card.json (before connection)

    A2A discovery is earlier in the lifecycle: you can inspect an
    agent's capabilities BEFORE deciding whether to connect to it.
"""

import argparse
import asyncio
import json
import sys
import time


def _wait(step_mode: bool, prompt: str = "  [ENTER to continue →] ") -> None:
    if step_mode:
        input(prompt)
    else:
        time.sleep(0.5)


def _header(title: str, width: int = 65) -> None:
    print("\n" + "╔" + "═" * (width - 2) + "╗")
    pad = (width - 2 - len(title)) // 2
    print("║" + " " * pad + title + " " * (width - 2 - pad - len(title)) + "║")
    print("╚" + "═" * (width - 2) + "╝")


def _section(title: str, width: int = 65) -> None:
    print("\n" + "─" * width)
    print("  " + title)
    print("─" * width)


async def fetch_and_display(seller_url: str, step_mode: bool) -> None:
    try:
        import httpx
    except ImportError:
        print("ERROR: httpx is required. Install with: pip install httpx")
        sys.exit(1)

    _header("M4 Exercise 1 Solution — A2A Agent Card Discovery")
    print(f"""
  We will fetch the seller's Agent Card from:
    {seller_url}/.well-known/agent-card.json

  This URL is standardized by the A2A protocol spec.
  Any A2A-compliant agent server exposes its card here.

  Think of it as the agent's "business card" — readable before
  any session or connection is established.
""")
    _wait(step_mode, "  [ENTER: fetch the Agent Card →] ")

    # ── Step 1: Fetch the card ────────────────────────────────────────────────
    _section("Step 1: HTTP GET /.well-known/agent-card.json")
    card_url = f"{seller_url}/.well-known/agent-card.json"
    print(f"\n  Fetching: {card_url}")
    print()

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(card_url)
            response.raise_for_status()
        except httpx.ConnectError:
            print(f"  ERROR: Could not connect to {seller_url}")
            print(f"  Make sure the seller server is running:")
            print(f"    python m4_adk_multiagents/a2a_protocol_seller_server.py --port 9102")
            return
        except Exception as e:
            print(f"  ERROR: {e}")
            return

    card = response.json()
    print(f"  HTTP {response.status_code} OK — card received ({len(response.content)} bytes)")
    _wait(step_mode, "  [ENTER: inspect the card fields →] ")

    # ── Step 2: Display core identity fields ──────────────────────────────────
    _section("Step 2: Core identity fields")
    print(f"""
  name:         {card.get('name', 'N/A')}
  version:      {card.get('version', 'N/A')}
  description:  {card.get('description', 'N/A')[:80]}
  url:          {card.get('url', 'N/A')}
""")
    _wait(step_mode, "  [ENTER: see skills →] ")

    # ── Step 3: Skills ────────────────────────────────────────────────────────
    _section("Step 3: Skills — what this agent can DO")
    skills = card.get("skills", [])
    if skills:
        for s in skills:
            print(f"  • {s.get('name', 'unnamed')}: {s.get('description', '')[:60]}")
            if s.get("examples"):
                print(f"      example: \"{s['examples'][0]}\"")
    else:
        print("  (no skills listed)")
    print()
    _wait(step_mode, "  [ENTER: see capabilities →] ")

    # ── Step 4: Capabilities ──────────────────────────────────────────────────
    _section("Step 4: Capabilities — protocol features supported")
    caps = card.get("capabilities", {})
    print(f"""
  streaming:            {caps.get('streaming', False)}
  pushNotifications:    {caps.get('pushNotifications', False)}
  stateTransitionHistory: {caps.get('stateTransitionHistory', False)}

  These capabilities tell the buyer client WHAT the server supports
  before sending any task. No wasted round-trips to discover features.
""")
    _wait(step_mode, "  [ENTER: see full raw JSON →] ")

    # ── Step 5: Full JSON ─────────────────────────────────────────────────────
    _section("Step 5: Full raw Agent Card JSON")
    print()
    print(json.dumps(card, indent=2))
    _wait(step_mode, "  [ENTER: compare to MCP tool discovery →] ")

    # ── Step 6: A2A vs MCP comparison ────────────────────────────────────────
    _section("Step 6: A2A Agent Card vs MCP Tool Discovery")
    print("""
  ┌─────────────────────┬───────────────────────────┬──────────────────────────────┐
  │                     │  MCP list_tools()          │  A2A Agent Card              │
  ├─────────────────────┼───────────────────────────┼──────────────────────────────┤
  │ Scope               │  Individual functions      │  Entire agent + skills       │
  │ Protocol            │  JSON-RPC over active      │  HTTP GET — no session       │
  │                     │  session (stdio/SSE)       │  needed                      │
  │ Timing              │  AFTER connection           │  BEFORE connection           │
  │ Schema              │  JSON Schema per param     │  Skill name + description    │
  │ Use case            │  Agent calling a tool      │  Discovering a peer agent    │
  └─────────────────────┴───────────────────────────┴──────────────────────────────┘

  KEY INSIGHT:
    MCP = tools for an agent to use (capabilities it CALLS)
    A2A = other agents it can talk to (peers it COMMUNICATES WITH)

    An A2A agent may internally use MCP tools to do its work.
    The buyer uses MCP to call pricing_server.py for market data,
    then uses A2A to negotiate with the seller server.
    Two protocols, two different layers of the architecture.
""")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch and inspect the A2A seller server's Agent Card",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:9102",
        help="Seller server base URL (default: http://127.0.0.1:9102)",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Skip interactive pauses",
    )
    args = parser.parse_args()

    asyncio.run(fetch_and_display(args.url, step_mode=not args.fast))


if __name__ == "__main__":
    main()
