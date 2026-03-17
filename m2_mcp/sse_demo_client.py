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
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_tool_result(result: Any) -> dict:
    """Parse MCP tool result content blocks into Python dict."""
    if result.content and len(result.content) > 0:
        text = result.content[0].text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}
    return {}


def _print_dict(data: dict, indent: int = 6) -> None:
    """Pretty-print a dict with consistent indentation."""
    prefix = " " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            print(f"{prefix}{key}:")
            _print_dict(value, indent + 4)
        elif isinstance(value, list):
            print(f"{prefix}{key}: [{len(value)} items]")
            for item in value[:3]:
                if isinstance(item, dict):
                    _print_dict(item, indent + 4)
                else:
                    print(f"{prefix}    {item}")
        else:
            print(f"{prefix}{key}: {value}")


# ─── Demo: Pricing Server ────────────────────────────────────────────────────

async def demo_pricing_server(url: str) -> None:
    """Connect to the pricing MCP server and call its tools."""
    print("=" * 60)
    print(f"PRICING SERVER  ({url})")
    print("=" * 60)
    print()

    async with sse_client(url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("Connected to Pricing MCP Server via SSE transport")
            print()

            # ── Tool Discovery ───────────────────────────────────────────
            tools_response = await session.list_tools()
            tools = tools_response.tools

            print(f"Available tools ({len(tools)}):")
            for tool in tools:
                print(f"  - {tool.name}: {tool.description[:70]}...")
            print()

            # ── Call: get_market_price ───────────────────────────────────
            print("Calling: get_market_price('742 Evergreen Terrace, Austin, TX 78701')")
            print()

            result = await session.call_tool(
                "get_market_price",
                {"address": "742 Evergreen Terrace, Austin, TX 78701"},
            )
            data = _parse_tool_result(result)
            _print_dict(data)
            print()

            # ── Call: calculate_discount ─────────────────────────────────
            print("Calling: calculate_discount(base_price=485000, market_condition='balanced')")
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

async def demo_inventory_server(url: str) -> None:
    """Connect to the inventory MCP server and call its tools."""
    print("=" * 60)
    print(f"INVENTORY SERVER  ({url})")
    print("=" * 60)
    print()

    async with sse_client(url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            print("Connected to Inventory MCP Server via SSE transport")
            print()

            # ── Tool Discovery ───────────────────────────────────────────
            tools_response = await session.list_tools()
            tools = tools_response.tools

            print(f"Available tools ({len(tools)}):")
            for tool in tools:
                print(f"  - {tool.name}: {tool.description[:70]}...")
            print()

            # ── Call: get_inventory_level ────────────────────────────────
            print("Calling: get_inventory_level('78701')")
            print()

            result = await session.call_tool(
                "get_inventory_level",
                {"zip_code": "78701"},
            )
            data = _parse_tool_result(result)
            _print_dict(data)
            print()

            # ── Call: get_minimum_acceptable_price ───────────────────────
            print("Calling: get_minimum_acceptable_price('742-evergreen')")
            print("   (This is seller-only confidential data)")
            print()

            result = await session.call_tool(
                "get_minimum_acceptable_price",
                {"property_id": "742-evergreen"},
            )
            data = _parse_tool_result(result)
            _print_dict(data)
            print()


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main(pricing_url: str | None, inventory_url: str | None) -> None:
    print()
    print("MCP SSE Client Demo")
    print("=" * 60)
    print("This client connects to MCP servers over HTTP (SSE transport).")
    print("Same protocol, same tools — just a different transport layer.")
    print()

    if pricing_url:
        await demo_pricing_server(pricing_url)

    if inventory_url:
        await demo_inventory_server(inventory_url)

    if not pricing_url and not inventory_url:
        print("No server URLs provided. Use --pricing-url and/or --inventory-url.")
        print()
        print("Example:")
        print("  # Start servers first (in separate terminals):")
        print("  python m2_mcp/pricing_server.py --sse --port 8001")
        print("  python m2_mcp/inventory_server.py --sse --port 8002")
        print()
        print("  # Then run this client:")
        print("  python m2_mcp/sse_demo_client.py --pricing-url http://localhost:8001/sse --inventory-url http://localhost:8002/sse")
        sys.exit(1)

    print("=" * 60)
    print("DONE — SSE demo complete.")
    print()
    print("Key takeaway:")
    print("  stdio and SSE use the SAME MCP protocol.")
    print("  The only difference is the transport layer.")
    print("  Agents don't care which transport is used — they call")
    print("  list_tools() and call_tool() the same way either way.")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCP SSE Demo Client")
    parser.add_argument(
        "--pricing-url",
        default="http://localhost:8001/sse",
        help="SSE URL for the pricing server (default: http://localhost:8001/sse)",
    )
    parser.add_argument(
        "--inventory-url",
        default=None,
        help="SSE URL for the inventory server (default: http://localhost:8002/sse)",
    )
    parser.add_argument(
        "--both",
        action="store_true",
        help="Connect to both pricing and inventory servers (default ports)",
    )

    args = parser.parse_args()

    pricing = args.pricing_url
    inventory = args.inventory_url

    if args.both:
        pricing = pricing or "http://localhost:8001/sse"
        inventory = inventory or "http://localhost:8002/sse"

    asyncio.run(main(pricing, inventory))
