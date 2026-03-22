"""
Real Estate Inventory MCP Server
==================================
An MCP server exposing real estate inventory and seller constraint data.

MCP CONCEPT:
  This server simulates an MLS (Multiple Listing Service) inventory system.
  It exposes two tools — one public (inventory data both agents can use)
  and one restricted (seller's minimum price, only the seller should access).

  In a real system, MCP auth would enforce this restriction.
  In our workshop, it's a teaching convention: the buyer agent simply
  doesn't connect to get_minimum_acceptable_price.

TOOLS EXPOSED:
  • get_inventory_level(zip_code)
      Returns: active listings, days on market avg, market condition,
               absorption rate — publicly available market data

  • get_minimum_acceptable_price(property_id)
      Returns: the seller's absolute floor price and reasoning
      ⚠️  In real estate, ONLY the seller's agent knows this.
      Our seller agent uses this; buyer agent does NOT connect to it.

TRANSPORT:
  stdio (default): python inventory_server.py
  SSE:             python inventory_server.py --sse --port 8002
"""

import argparse
import inspect
import random
import sys
import textwrap
import time
from typing import Optional

from mcp.server.fastmcp import FastMCP


# ─── Demo Helpers ─────────────────────────────────────────────────────────────

def _wait(step_mode: bool, prompt: str = "  [ENTER to continue →] ") -> None:
    if step_mode:
        input(prompt)
    else:
        time.sleep(0.3)


def _header(title: str, width: int = 65) -> None:
    print("\n" + "╔" + "═" * (width - 2) + "╗")
    pad = (width - 2 - len(title)) // 2
    print("║" + " " * pad + title + " " * (width - 2 - pad - len(title)) + "║")
    print("╚" + "═" * (width - 2) + "╝")


def _section(title: str, width: int = 65) -> None:
    print("\n" + "─" * width)
    print("  " + title)
    print("─" * width)


def _print_source(method, notes: list = None) -> None:
    raw = inspect.getsource(method)
    src = textwrap.dedent(raw)
    lines = src.rstrip().split("\n")
    print()
    print("  " + "┄" * 63)
    for i, line in enumerate(lines, 1):
        display = line if len(line) <= 90 else line[:87] + "…"
        print(f"  {i:3d} │ {display}")
    print("  " + "┄" * 63)
    if notes:
        print()
        for note in notes:
            print(f"  ▶  {note}")


# ─── Initialize Server ────────────────────────────────────────────────────────

mcp = FastMCP(
    "real-estate-inventory"
)


# ─── Simulated Inventory Database ─────────────────────────────────────────────

INVENTORY_DATA: dict[str, dict] = {
    "78701": {
        "zip_code": "78701",
        "city": "Austin",
        "neighborhood": "South Austin",
        "active_listings": 47,
        "new_listings_30_days": 18,
        "closed_sales_30_days": 15,
        "avg_days_on_market": 22,
        "median_days_on_market": 18,
        "absorption_rate_months": 3.1,
        "price_reductions_pct": 12,  # % of listings with price drops
        "list_to_sale_ratio": 0.971,
        "market_condition": "balanced",
        "buyer_competition_level": "moderate",
        "notes": "Balanced market with moderate buyer activity. Standard negotiation expected.",
    },
    "78702": {
        "zip_code": "78702",
        "city": "Austin",
        "neighborhood": "East Austin",
        "active_listings": 23,
        "new_listings_30_days": 22,
        "closed_sales_30_days": 21,
        "avg_days_on_market": 9,
        "median_days_on_market": 7,
        "absorption_rate_months": 1.1,
        "price_reductions_pct": 3,
        "list_to_sale_ratio": 1.018,
        "market_condition": "hot",
        "buyer_competition_level": "very_high",
        "notes": "Very hot market. Multiple offers common. Buyers should act fast and offer strong.",
    },
    "78703": {
        "zip_code": "78703",
        "city": "Austin",
        "neighborhood": "Clarksville",
        "active_listings": 89,
        "new_listings_30_days": 14,
        "closed_sales_30_days": 13,
        "avg_days_on_market": 48,
        "median_days_on_market": 42,
        "absorption_rate_months": 6.8,
        "price_reductions_pct": 31,
        "list_to_sale_ratio": 0.943,
        "market_condition": "cold",
        "buyer_competition_level": "low",
        "notes": "Buyer's market. Negotiate aggressively. Sellers are motivated.",
    },
}

# Seller constraint data — ONLY the seller should access this
# In real life: this comes from the seller's listing agreement
SELLER_CONSTRAINTS: dict[str, dict] = {
    "742-evergreen-austin-78701": {
        "property_id": "742-evergreen-austin-78701",
        "display_address": "742 Evergreen Terrace, Austin, TX 78701",
        "list_price": 485_000,
        "minimum_acceptable_price": 445_000,
        "ideal_price": 465_000,
        "seller_motivation_level": "moderate",  # low | moderate | high
        "must_close_by": "2025-03-31",
        "seller_situation": "Seller has purchased another home and needs proceeds",
        "price_floor_reasoning": (
            "Seller owes $380,000 on mortgage. After agent commission (3%) "
            "and closing costs (~$8,000), seller needs minimum $445,000 to "
            "cover all obligations and have funds for the new home down payment."
        ),
        "concessions_willing_to_make": [
            "Cover buyer's title insurance ($1,200)",
            "Include all appliances",
            "Flexible closing date within 30–60 days",
        ],
        "dealbreakers": [
            "Cannot go below $445,000 — mortgage payoff requirement",
            "Cannot delay closing past March 31, 2025",
        ],
    }
}


# ─── MCP Tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def get_inventory_level(zip_code: str) -> dict:
    """
    Get real estate inventory and market activity data for a ZIP code.

    This is PUBLIC market data — both buyer and seller agents can use this
    to understand market conditions and calibrate their negotiation strategy.

    MCP NOTE: In production, this would call the MLS API or Realtor.com.
    MCP abstracts this — agents call the same tool regardless of the
    underlying data source.

    Args:
        zip_code: 5-digit ZIP code (e.g., "78701" for South Austin)

    Returns:
        Inventory statistics, market condition, and negotiation context.
    """
    # Step 1) Lookup known ZIP data for deterministic workshop outputs.
    data = INVENTORY_DATA.get(zip_code)

    if not data:
        # Step 2) Fallback for unknown ZIPs so tool stays useful for ad-hoc demos.
        # In production this would query MLS/provider APIs.
        absorption = round(random.uniform(2.0, 5.0), 1)
        dom = random.randint(15, 45)
        active = random.randint(30, 100)
        closed = random.randint(10, 30)

        condition = (
            "hot" if absorption < 2 else
            "cold" if absorption > 5 else
            "balanced"
        )

        data = {
            "zip_code": zip_code,
            "city": "Austin",
            "neighborhood": "Austin Metro",
            "active_listings": active,
            "new_listings_30_days": random.randint(10, 30),
            "closed_sales_30_days": closed,
            "avg_days_on_market": dom,
            "median_days_on_market": int(dom * 0.85),
            "absorption_rate_months": absorption,
            "price_reductions_pct": random.randint(8, 25),
            "list_to_sale_ratio": round(random.uniform(0.95, 1.02), 3),
            "market_condition": condition,
            "buyer_competition_level": "moderate",
            "notes": f"Data generated for {zip_code}. Absorption rate: {absorption} months.",
        }

    # Step 3) Add negotiation interpretation layer on top of raw market metrics.
    # This keeps clients simple: they receive both data and decision context.
    condition = data["market_condition"]
    buyer_leverage = {
        "hot": "Minimal — seller has leverage",
        "balanced": "Moderate — balanced negotiation",
        "cold": "Strong — buyer has leverage",
    }.get(condition, "Unknown")

    price_drop_expectation = {
        "hot": "0–2% — little room to negotiate",
        "balanced": "2–5% — typical negotiation range",
        "cold": "5–10% — significant negotiation room",
    }.get(condition, "Unknown")

    # Final MCP payload returned to caller.
    return {
        "zip_code": data["zip_code"],
        "location": {
            "city": data["city"],
            "neighborhood": data["neighborhood"],
        },
        "activity_30_days": {
            "active_listings": data["active_listings"],
            "new_listings": data["new_listings_30_days"],
            "closed_sales": data["closed_sales_30_days"],
            "absorption_rate_months": data["absorption_rate_months"],
        },
        "time_on_market": {
            "avg_days": data["avg_days_on_market"],
            "median_days": data["median_days_on_market"],
        },
        "pricing_metrics": {
            "pct_with_price_reductions": data["price_reductions_pct"],
            "list_to_sale_ratio": data["list_to_sale_ratio"],
            "typical_close_vs_list_pct": round((data["list_to_sale_ratio"] - 1) * 100, 1),
        },
        "market_assessment": {
            "condition": data["market_condition"],
            "buyer_competition": data["buyer_competition_level"],
            "market_notes": data["notes"],
        },
        "negotiation_analysis": {
            "buyer_leverage": buyer_leverage,
            "expected_price_drop_pct": price_drop_expectation,
            "urgency_for_buyer": (
                "High — act quickly" if condition == "hot" else
                "Low — take time to negotiate" if condition == "cold" else
                "Moderate — reasonable pace"
            ),
            "seller_motivation": (
                "Low" if condition == "hot" else
                "High" if condition == "cold" else
                "Moderate"
            ),
        },
        "data_source": "MCP Inventory Server (simulated MLS data)",
    }


@mcp.tool()
def get_minimum_acceptable_price(property_id: str) -> dict:
    """
    Get the seller's minimum acceptable price and constraint analysis.

    ⚠️  ACCESS CONTROL NOTE:
    In a real estate transaction, ONLY the seller's agent knows the seller's
    floor price. This tool simulates that confidential data.

    In our workshop:
    - SELLER AGENT connects to this tool (it's their agent's information)
    - BUYER AGENT does NOT connect to this tool (information asymmetry)

    In production MCP systems, access control would be enforced via:
    - API keys per agent
    - OAuth scopes
    - MCP server-level auth checks

    Args:
        property_id: Unique property identifier
                     (e.g., "742-evergreen-austin-78701")

    Returns:
        Seller's floor price, motivation level, and negotiation constraints.
    """
    # Step 1) Resolve seller-specific constraints for the property.
    constraints = SELLER_CONSTRAINTS.get(property_id)

    if not constraints:
        # Step 2) Generate fallback constraints for unknown IDs.
        # This preserves demo continuity while clearly marking simulated behavior.
        list_price = random.randint(400_000, 600_000)
        min_price = int(list_price * random.uniform(0.90, 0.95))
        ideal_price = int(list_price * random.uniform(0.96, 0.99))

        constraints = {
            "property_id": property_id,
            "display_address": f"Property {property_id}",
            "list_price": list_price,
            "minimum_acceptable_price": min_price,
            "ideal_price": ideal_price,
            "seller_motivation_level": random.choice(["low", "moderate", "high"]),
            "must_close_by": None,
            "seller_situation": "Standard sale",
            "price_floor_reasoning": (
                f"Seller's mortgage and costs require minimum ${min_price:,}."
            ),
            "concessions_willing_to_make": ["Standard concessions"],
            "dealbreakers": [f"Cannot go below ${min_price:,}"],
        }

    # Step 3) Compute negotiation room so seller agent can set strategy bounds.
    list_price = constraints["list_price"]
    min_price = constraints["minimum_acceptable_price"]
    ideal_price = constraints["ideal_price"]
    negotiation_room = list_price - min_price

    # Final payload intentionally includes both numbers and strategy hints.
    return {
        "property_id": constraints["property_id"],
        "address": constraints["display_address"],
        "pricing_constraints": {
            "list_price": list_price,
            "minimum_acceptable_price": min_price,
            "ideal_closing_price": ideal_price,
            "absolute_negotiation_room": negotiation_room,
            "negotiation_room_pct": round(negotiation_room / list_price * 100, 1),
        },
        "seller_profile": {
            "motivation_level": constraints["seller_motivation_level"],
            "must_close_by": constraints.get("must_close_by"),
            "situation": constraints["seller_situation"],
        },
        "floor_price_reasoning": constraints["price_floor_reasoning"],
        "concessions_available": constraints["concessions_willing_to_make"],
        "dealbreakers": constraints["dealbreakers"],
        "strategy_for_seller_agent": {
            "your_floor": min_price,
            "your_target": ideal_price,
            "max_concession_amount": negotiation_room,
            "recommended_opening_counter": int(list_price * 0.985),
            "increment_strategy": "Drop by $5,000–$8,000 per round until floor",
            "walk_away_trigger": f"Any offer below ${min_price:,}",
        },
        "data_source": "MCP Inventory Server — SELLER CONFIDENTIAL",
        "access_warning": (
            "This data represents the seller's confidential floor price. "
            "In production, this would be protected by MCP authentication. "
            "Only the seller's agent should access this tool."
        ),
    }


# ─── Demo Mode ────────────────────────────────────────────────────────────────

def _run_demo(step_mode: bool) -> None:
    """
    Walk through the inventory server's tools in teaching mode.
    Key concept: information asymmetry — one tool is public, one is seller-only.
    """
    _header("Real Estate Inventory MCP Server — Information Asymmetry")
    print("""
  This server exposes 2 MCP tools:
    1. get_inventory_level(zip_code)           ← PUBLIC: buyer AND seller can use
    2. get_minimum_acceptable_price(property_id) ← SELLER ONLY: buyer does NOT connect

  This is INFORMATION ASYMMETRY enforced by MCP access control.
  In real estate: only the seller's agent knows the seller's floor price.
  In our system:  the buyer agent simply never connects to this server's
                  get_minimum_acceptable_price tool.

  In production: MCP auth (API keys, OAuth scopes) would enforce this at the
                 protocol level — the server rejects unauthorized calls.
""")
    _wait(step_mode, "  [ENTER: see the public tool — get_inventory_level() →] ")

    # ── Tool 1: get_inventory_level (public) ──────────────────────────────────
    _section("Tool 1 of 2: get_inventory_level() — PUBLIC (buyer + seller both call this)")
    print("""
  Public market data. Both buyer and seller agents call this to understand
  market pressure before making or responding to an offer.
  More listings → buyer has leverage. Fewer listings → seller has leverage.
""")
    _print_source(get_inventory_level, notes=[
        "INVENTORY_DATA dict: deterministic data for 78701/78702/78703 ZIP codes",
        "Fallback: synthesizes plausible values for unknown ZIPs",
        "absorption_rate_months: < 2 = hot, > 5 = cold, 2–5 = balanced",
        "Returns buyer_leverage + expected_price_drop_pct — agent cites these in offers",
        "Both buyer and seller can call this — no access restriction",
    ])
    _wait(step_mode, "  [ENTER: call get_inventory_level('78701') live →] ")

    _section("Live call: get_inventory_level('78701')  [balanced market]")
    print()
    result = get_inventory_level("78701")
    loc = result["location"]
    act = result["activity_30_days"]
    tom = result["time_on_market"]
    pm = result["pricing_metrics"]
    ma = result["market_assessment"]
    na = result["negotiation_analysis"]
    print(f"  location:           {loc['neighborhood']}, {loc['city']}")
    print(f"  active_listings:    {act['active_listings']}")
    print(f"  closed_30_days:     {act['closed_sales']}")
    print(f"  absorption_rate:    {act['absorption_rate_months']} months  ← balanced (2–5 = balanced)")
    print(f"  avg_days_on_market: {tom['avg_days']}")
    print(f"  list_to_sale_ratio: {pm['list_to_sale_ratio']}  (homes close at {int(pm['list_to_sale_ratio']*100)}% of list)")
    print(f"  pct_price_drops:    {pm['pct_with_price_reductions']}% of listings reduced")
    print()
    print(f"  market_condition:   {ma['condition']}")
    print(f"  buyer_leverage:     {na['buyer_leverage']}")
    print(f"  expected_price_drop:{na['expected_price_drop_pct']}")
    print(f"  urgency_for_buyer:  {na['urgency_for_buyer']}")
    print()

    _wait(step_mode, "  [ENTER: compare with a HOT market (78702) →] ")
    _section("Live call: get_inventory_level('78702')  [hot market — contrast]")
    print()
    result2 = get_inventory_level("78702")
    act2 = result2["activity_30_days"]
    tom2 = result2["time_on_market"]
    ma2 = result2["market_assessment"]
    na2 = result2["negotiation_analysis"]
    print(f"  location:           {result2['location']['neighborhood']}, {result2['location']['city']}")
    print(f"  active_listings:    {act2['active_listings']}  (vs 47 in 78701 — far fewer)")
    print(f"  absorption_rate:    {act2['absorption_rate_months']} months  ← HOT (< 2 months)")
    print(f"  avg_days_on_market: {tom2['avg_days']}  (vs 22 in 78701)")
    print(f"  market_condition:   {ma2['condition']}")
    print(f"  buyer_leverage:     {na2['buyer_leverage']}")
    print(f"  expected_price_drop:{na2['expected_price_drop_pct']}")
    print()
    print("  COMPARE: In a hot market, agents offer differently.")
    print("  Same tool call, different ZIP code → totally different negotiation strategy.")
    _wait(step_mode, "  [ENTER: see the seller-only tool — get_minimum_acceptable_price() →] ")

    # ── Tool 2: get_minimum_acceptable_price (seller-only) ────────────────────
    _section("Tool 2 of 2: get_minimum_acceptable_price() — SELLER ONLY ⚠️")
    print("""
  This is the seller's CONFIDENTIAL floor price.
  In real estate: the seller's agent knows this. The buyer's agent does NOT.

  In our system:
    seller_adk.py connects to BOTH pricing_server + inventory_server
    buyer_adk.py  connects ONLY to pricing_server

  That's the information asymmetry: the seller knows their floor.
  The buyer must guess. This mirrors real negotiations.

  In production MCP systems, this would be protected by:
    • API keys — buyer's token doesn't grant access to this tool
    • OAuth scopes — buyer's scope excludes "seller:confidential"
    • Server-level auth check — call rejected before the function runs
""")
    _print_source(get_minimum_acceptable_price, notes=[
        "SELLER_CONSTRAINTS dict: contains the seller's mortgage payoff requirement",
        "minimum_acceptable_price: $445,000 — the hard floor (mortgage payoff + costs)",
        "seller_motivation_level: 'moderate' — seller bought another home, needs proceeds",
        "concessions_willing_to_make: things seller can offer to close the deal",
        "strategy_for_seller_agent: pre-computed strategy the seller agent follows",
        "access_warning field: documents that this is confidential — not just a naming convention",
    ])
    _wait(step_mode, "  [ENTER: call get_minimum_acceptable_price() live →] ")

    _section("Live call: get_minimum_acceptable_price('742-evergreen-austin-78701')")
    print()
    result3 = get_minimum_acceptable_price("742-evergreen-austin-78701")
    pc = result3["pricing_constraints"]
    sp = result3["seller_profile"]
    st = result3["strategy_for_seller_agent"]
    print(f"  property_id:            {result3['property_id']}")
    print(f"  address:                {result3['address']}")
    print()
    print(f"  list_price:             ${pc['list_price']:,}")
    print(f"  minimum_acceptable:     ${pc['minimum_acceptable_price']:,}  ← the floor")
    print(f"  ideal_closing_price:    ${pc['ideal_closing_price']:,}  ← what seller hopes for")
    print(f"  negotiation_room:       ${pc['absolute_negotiation_room']:,} ({pc['negotiation_room_pct']}% off list)")
    print()
    print(f"  motivation_level:       {sp['motivation_level']}")
    print(f"  must_close_by:          {sp['must_close_by']}")
    print(f"  situation:              {sp['situation']}")
    print()
    print(f"  floor_price_reasoning:")
    print(f"    {result3['floor_price_reasoning']}")
    print()
    print(f"  strategy_for_seller_agent:")
    print(f"    floor:              ${st['your_floor']:,}")
    print(f"    target:             ${st['your_target']:,}")
    print(f"    recommended_opening:${st['recommended_opening_counter']:,}")
    print(f"    increment_strategy: {st['increment_strategy']}")
    print(f"    walk_away_trigger:  {st['walk_away_trigger']}")
    print()
    print(f"  ⚠️  {result3['access_warning'][:80]}...")
    _wait(step_mode, "  [ENTER: see the information asymmetry summary →] ")

    # ── Information asymmetry summary ─────────────────────────────────────────
    _section("Information Asymmetry — The Teaching Point")
    print("""
  ╔══════════════════════════╦═══════════════════╦═══════════════════╗
  ║ Tool                     ║  Buyer agent      ║  Seller agent     ║
  ╠══════════════════════════╬═══════════════════╬═══════════════════╣
  ║ get_market_price         ║  ✓ can call       ║  ✓ can call       ║
  ║ calculate_discount       ║  ✓ can call       ║  ✓ can call       ║
  ║ get_inventory_level      ║  ✓ can call       ║  ✓ can call       ║
  ║ get_minimum_acceptable_  ║  ✗ no access      ║  ✓ can call       ║
  ║   price                  ║                   ║                   ║
  ╚══════════════════════════╩═══════════════════╩═══════════════════╝

  The buyer must INFER the seller's floor through negotiation.
  The seller KNOWS their floor and can accept instantly when buyer reaches it.

  This asymmetry is enforced by which MCPToolsets each agent creates:
    buyer_adk.py:   MCPToolset(pricing_server) only
    seller_adk.py:  MCPToolset(pricing_server) + MCPToolset(inventory_server)

  The seller sees 4 tools. The buyer sees 2. Same protocol. Different access.
""")


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Real Estate Inventory MCP Server — stdio, SSE, and demo modes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python inventory_server.py              # demo mode (default when run in a terminal)
  python inventory_server.py --fast       # demo without pauses
  python inventory_server.py --check      # verify server loads correctly
  python inventory_server.py --sse --port 8002  # HTTP/SSE server mode
  python inventory_server.py --server     # force stdio server mode (agents use this automatically)
""",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Import check: verify server loads correctly then exit 0. No network I/O.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run interactive teaching demo (default when run in a terminal — kept for compatibility)",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Disable step pauses in demo mode",
    )
    parser.add_argument(
        "--server",
        action="store_true",
        help="Force stdio server mode (normally auto-detected when spawned as a subprocess)",
    )
    parser.add_argument(
        "--sse",
        action="store_true",
        help="Use SSE transport (HTTP server mode)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8002,
        help="Port for SSE transport (default: 8002)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host for SSE transport (default: 0.0.0.0)"
    )
    args = parser.parse_args()

    if args.check:
        # Lightweight health check for CI/scripts.
        tools = list(mcp._tool_manager._tools.keys())
        print(f"inventory_server OK  tools={tools}")
        sys.exit(0)
    elif args.sse:
        # SSE mode: long-running HTTP endpoint, suitable for multiple clients.
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        print(f"Real Estate Inventory MCP Server (SSE mode)")
        print(f"   Listening on: http://{args.host}:{args.port}/sse")
        print(f"   Tools: get_inventory_level, get_minimum_acceptable_price")
        print(f"   ⚠️  get_minimum_acceptable_price is seller-confidential — buyer should not connect here.")
        print(f"   Ctrl+C to stop.")
        mcp.run(transport="sse")
    elif args.server or not sys.stdin.isatty():
        # stdio server mode: either explicitly requested (--server) or auto-detected because
        # stdin is a pipe — meaning an agent spawned this process as a subprocess.
        mcp.run()
    else:
        # Interactive terminal (default): run the teaching demo.
        # Students can run: python inventory_server.py
        # --demo flag is accepted as an alias for backwards compatibility.
        _run_demo(step_mode=not args.fast)
