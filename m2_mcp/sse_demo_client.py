"""
SSE MCP Demo Client
===================
Connects to our real estate MCP servers running in SSE (HTTP) mode
and demonstrates tool discovery and calling — the same pattern used
by agents, but over HTTP instead of stdio.

WHY SSE?
  stdio:  Server runs as a child process (1:1 coupling).
  SSE:    Server runs as an HTTP endpoint — multiple clients can connect
          at once, and the server can live on another machine or container.

PREREQUISITES:
  Start the MCP servers in SSE mode first (in separate terminals):
    python m2_mcp/pricing_server.py --sse --port 8001
    python m2_mcp/inventory_server.py --sse --port 8002

HOW TO RUN:
  python m2_mcp/sse_demo_client.py

  # Connect to pricing server only:
  python m2_mcp/sse_demo_client.py --pricing-url http://localhost:8001/sse

  # Connect to both servers:
  python m2_mcp/sse_demo_client.py --pricing-url http://localhost:8001/sse --inventory-url http://localhost:8002/sse

WHAT THIS DEMONSTRATES:
  1. Connecting to MCP servers via SSE transport (HTTP)
  2. Listing available tools (auto-discovery)
  3. Calling tools with structured arguments
  4. Parsing structured results
  5. Connecting to multiple MCP servers from a single client
"""

import argparse
import asyncio
import json
import sys
import time
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _wait(step_mode: bool, prompt: str = "  [ENTER to continue →] ") -> None:
    if step_mode:
        input(prompt)
    else:
        time.sleep(0.4)


def _header(title: str, width: int = 65) -> None:
    print("\n" + "╔" + "═" * (width - 2) + "╗")
    pad = (width - 2 - len(title)) // 2
    print("║" + " " * pad + title + " " * (width - 2 - pad - len(title)) + "║")
    print("╚" + "═" * (width - 2) + "╝")


def _section(title: str, width: int = 65) -> None:
    print("\n" + "─" * width)
    print("  " + title)
    print("─" * width)


def _parse_tool_result(result: Any) -> dict:
    """Parse MCP tool result content blocks into Python dict."""
    if result.content and len(result.content) > 0:
        text = result.content[0].text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}
    return {}


def _print_dict(data: dict, indent: int = 4) -> None:
    """Pretty-print a dict with consistent indentation, clipping deep nesting."""
    prefix = " " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            print(f"{prefix}{key}:")
            _print_dict(value, indent + 4)
        elif isinstance(value, list):
            print(f"{prefix}{key}: [{len(value)} items]")
            for item in value[:2]:
                if isinstance(item, dict):
                    _print_dict(item, indent + 4)
                else:
                    print(f"{prefix}    {item}")
        elif isinstance(value, str) and len(value) > 70:
            print(f"{prefix}{key}: {value[:67]}...")
        else:
            print(f"{prefix}{key}: {value}")


# ─── Demo: Pricing Server ────────────────────────────────────────────────────

async def demo_pricing_server(url: str, step_mode: bool = True) -> None:
    """Connect to the pricing MCP server and demonstrate its tools over SSE."""
    _header(f"PRICING SERVER — SSE Transport")
    print(f"""
  URL: {url}
  Transport: SSE (Server-Sent Events over HTTP)

  SSE DIFFERENCE FROM STDIO:
    stdio: server runs as a child process of the client (1:1, same machine)
    SSE:   server runs as a standalone HTTP endpoint (1:N, any machine)

  Same MCP protocol. Same list_tools() + call_tool() calls.
  The client code doesn't change — only the connection parameters do.
""")
    _wait(step_mode, "  [ENTER: connect and discover tools →] ")

    async with sse_client(url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("  Connected via SSE. MCP handshake complete.")
            print()

            # ── Tool Discovery ─────────────────────────────────────────────
            _section("Tool Discovery: session.list_tools()")
            tools_response = await session.list_tools()
            tools = tools_response.tools

            print(f"\n  Pricing server exposes {len(tools)} tools:")
            for tool in tools:
                print(f"    • {tool.name}")
                print(f"      {tool.description[:80]}...")
            print()
            _wait(step_mode, "  [ENTER: call get_market_price() →] ")

            # ── Call: get_market_price ─────────────────────────────────────
            _section("Tool Call 1: get_market_price('742 Evergreen Terrace, Austin, TX 78701')")
            print()
            result = await session.call_tool(
                "get_market_price",
                {"address": "742 Evergreen Terrace, Austin, TX 78701"},
            )
            data = _parse_tool_result(result)
            _print_dict(data)
            print()
            _wait(step_mode, "  [ENTER: call calculate_discount() →] ")

            # ── Call: calculate_discount ───────────────────────────────────
            _section("Tool Call 2: calculate_discount(485000, 'balanced', 30, 'good')")
            print()
            result = await session.call_tool(
                "calculate_discount",
                {
                    "base_price": 485000,
                    "market_condition": "balanced",
                    "days_on_market": 30,
                    "property_condition": "good",
                },
            )
            data = _parse_tool_result(result)
            _print_dict(data)
            print()


# ─── Demo: Inventory Server ──────────────────────────────────────────────────

async def demo_inventory_server(url: str, step_mode: bool = True) -> None:
    """Connect to the inventory MCP server and demonstrate its tools over SSE."""
    _header("INVENTORY SERVER — Information Asymmetry over SSE")
    print(f"""
  URL: {url}
  Transport: SSE

  This server has TWO tools with DIFFERENT access levels:
    get_inventory_level       — PUBLIC (buyer + seller both call this)
    get_minimum_acceptable_price — SELLER ONLY (buyer should not connect here)

  In production: MCP auth would enforce this. In our demo: convention.
""")
    _wait(step_mode, "  [ENTER: connect and discover tools →] ")

    async with sse_client(url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("  Connected via SSE. MCP handshake complete.")
            print()

            # ── Tool Discovery ─────────────────────────────────────────────
            _section("Tool Discovery: session.list_tools()")
            tools_response = await session.list_tools()
            tools = tools_response.tools

            print(f"\n  Inventory server exposes {len(tools)} tools:")
            for tool in tools:
                print(f"    • {tool.name}")
                print(f"      {tool.description[:80]}...")
            print()
            _wait(step_mode, "  [ENTER: call get_inventory_level() — public tool →] ")

            # ── Call: get_inventory_level ──────────────────────────────────
            _section("Tool Call 1: get_inventory_level('78701')  [PUBLIC tool]")
            print()
            result = await session.call_tool(
                "get_inventory_level",
                {"zip_code": "78701"},
            )
            data = _parse_tool_result(result)
            _print_dict(data)
            print()
            _wait(step_mode, "  [ENTER: call get_minimum_acceptable_price() — seller-only tool →] ")

            # ── Call: get_minimum_acceptable_price ─────────────────────────
            _section("Tool Call 2: get_minimum_acceptable_price()  ⚠️  SELLER ONLY")
            print("""
  In production: the buyer's MCP client would not have a token that grants
  access to this tool. The server would reject the call.
  In our demo:   the buyer_adk.py simply never connects to inventory_server.
""")
            _wait(step_mode, "  [ENTER: run call →] ")
            result = await session.call_tool(
                "get_minimum_acceptable_price",
                {"property_id": "742-evergreen-austin-78701"},
            )
            data = _parse_tool_result(result)
            _print_dict(data)
            print()
            print("  ▶  minimum_acceptable_price is the seller's floor — buyer must guess via negotiation.")


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main(pricing_url: str | None, inventory_url: str | None, step_mode: bool = True) -> None:
    _header("MCP SSE Client Demo — Same Protocol, Different Transport")
    print("""
  This client connects to MCP servers over HTTP (SSE transport).
  Same list_tools() + call_tool() calls as the stdio demos.
  The ONLY difference is the connection type.

  stdio:  sse_client(url)  →  HTTP GET /sse  →  server pushes events
  versus
  stdio:  stdio_client(params)  →  subprocess stdin/stdout pipes

  To run this demo you need the servers running in SSE mode:
    Terminal 1: python m2_mcp/pricing_server.py --sse --port 8001
    Terminal 2: python m2_mcp/inventory_server.py --sse --port 8002
    Terminal 3: python m2_mcp/sse_demo_client.py --both
""")

    if not pricing_url and not inventory_url:
        print("  No server URLs provided. Start servers first:")
        print("    python m2_mcp/pricing_server.py --sse --port 8001")
        print("    python m2_mcp/inventory_server.py --sse --port 8002")
        print()
        print("  Then run:")
        print("    python m2_mcp/sse_demo_client.py                  # pricing only")
        print("    python m2_mcp/sse_demo_client.py --both           # both servers")
        sys.exit(1)

    _wait(step_mode, "  [ENTER: connect to pricing server →] ")

    if pricing_url:
        await demo_pricing_server(pricing_url, step_mode)

    if inventory_url:
        _wait(step_mode, "  [ENTER: connect to inventory server →] ")
        await demo_inventory_server(inventory_url, step_mode)

    _header("SSE Demo Complete")
    print("""
  Key takeaway:
    stdio and SSE use the SAME MCP protocol.
    The only difference is the transport layer.
    Agents call list_tools() and call_tool() identically either way.

    Use stdio when:  server and client are on the same machine (agent spawning)
    Use SSE when:    server is shared, remote, or serves multiple clients at once
""")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="MCP SSE Demo Client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start servers first (in separate terminals):
  python m2_mcp/pricing_server.py --sse --port 8001
  python m2_mcp/inventory_server.py --sse --port 8002

  # Then:
  python sse_demo_client.py                # pricing server only, step-by-step
  python sse_demo_client.py --both         # both servers, step-by-step
  python sse_demo_client.py --both --fast  # both servers, no pauses
""",
    )
    parser.add_argument(
        "--pricing-url",
        default="http://localhost:8001/sse",
        help="SSE URL for the pricing server (default: http://localhost:8001/sse)",
    )
    parser.add_argument(
        "--inventory-url",
        default=None,
        help="SSE URL for the inventory server",
    )
    parser.add_argument(
        "--both",
        action="store_true",
        help="Connect to both pricing (8001) and inventory (8002) servers",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Disable step mode — run without pausing",
    )

    args = parser.parse_args()

    pricing = args.pricing_url
    inventory = args.inventory_url

    if args.both:
        pricing = pricing or "http://localhost:8001/sse"
        inventory = inventory or "http://localhost:8002/sse"

    asyncio.run(main(pricing, inventory, step_mode=not args.fast))
