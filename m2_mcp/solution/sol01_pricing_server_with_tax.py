"""
MODULE 2 — EXERCISE 1 SOLUTION: Add get_property_tax_estimate Tool
==================================================================
This is the COMPLETE, RUNNABLE SOLUTION for Exercise 1.
It is a full MCP server — a copy of pricing_server.py with the new
get_property_tax_estimate tool added. The original pricing_server.py
is NOT modified.

WHAT WAS ADDED vs the original pricing_server.py:
  - get_property_tax_estimate(price, tax_rate) tool  ← the only addition

HOW TO RUN (demo mode — shows the new tool working step by step):
  python m2_mcp/solution/sol01_pricing_server_with_tax.py

HOW TO RUN (no pauses):
  python m2_mcp/solution/sol01_pricing_server_with_tax.py --fast

HOW TO RUN (as MCP server — for agent use):
  python m2_mcp/solution/sol01_pricing_server_with_tax.py --server

HOW TO RUN (SSE mode — multiple clients):
  python m2_mcp/solution/sol01_pricing_server_with_tax.py --sse --port 8003

WIRING INTO BUYER AGENT (Exercise 2):
  After adding this tool, update buyer_simple.py:
  1. Add to BUYER_MCP_PLANNER_PROMPT available tools list
  2. Add a note to BUYER_SYSTEM_PROMPT about using tax for strategy
  The call_pricing_mcp() function does NOT need to change — it's generic.
"""

import argparse
import inspect
import random
import sys
import textwrap
import time
from typing import Literal

from mcp.server.fastmcp import FastMCP


# ─── Demo Helpers ─────────────────────────────────────────────────────────────

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


# ─── Initialize MCP Server ────────────────────────────────────────────────────

mcp = FastMCP("real-estate-pricing-with-tax")


# ─── Simulated Data Store ─────────────────────────────────────────────────────
# Identical to pricing_server.py — real data, not stubs.

PROPERTY_DATABASE: dict[str, dict] = {
    "742 evergreen terrace, austin, tx 78701": {
        "display_address": "742 Evergreen Terrace, Austin, TX 78701",
        "type": "single_family",
        "bedrooms": 4,
        "bathrooms": 3,
        "sqft": 2400,
        "lot_sqft": 8500,
        "year_built": 2005,
        "list_price": 485_000,
        "estimated_value": 462_000,
        "price_per_sqft": 202,
        "days_on_market": 18,
        "neighborhood": "South Austin",
        "zip_code": "78701",
        "school_rating": 8,
        "hoa_monthly": 0,
        "tax_annual": 9_800,
        "recent_upgrades": [
            "Kitchen renovation (2023) - $45,000",
            "New roof (2022) - $18,000",
            "HVAC replacement (2021) - $12,000",
        ],
        "comparable_sales": [
            {"address": "738 Evergreen Terrace, Austin, TX", "price": 458_000, "sqft": 2_350, "price_per_sqft": 195, "days_ago": 12, "bed_bath": "4/2"},
            {"address": "751 Evergreen Terrace, Austin, TX", "price": 471_500, "sqft": 2_520, "price_per_sqft": 187, "days_ago": 28, "bed_bath": "4/3"},
            {"address": "820 Maple Creek Dr, Austin, TX",   "price": 456_000, "sqft": 2_280, "price_per_sqft": 200, "days_ago": 41, "bed_bath": "3/3"},
            {"address": "715 Bluebell Ave, Austin, TX",     "price": 468_000, "sqft": 2_400, "price_per_sqft": 195, "days_ago": 55, "bed_bath": "4/3"},
        ]
    }
}

MARKET_DATA: dict[str, dict] = {
    "78701": {"condition": "balanced", "inventory_months": 3.2, "yoy_appreciation_pct": 4.1, "median_days_on_market": 22, "list_to_sale_ratio": 0.97},
    "78702": {"condition": "hot",      "inventory_months": 1.5, "yoy_appreciation_pct": 8.3, "median_days_on_market": 9,  "list_to_sale_ratio": 1.02},
    "78703": {"condition": "cold",     "inventory_months": 6.8, "yoy_appreciation_pct": 1.2, "median_days_on_market": 45, "list_to_sale_ratio": 0.94},
    "default": {"condition": "balanced", "inventory_months": 3.5, "yoy_appreciation_pct": 3.5, "median_days_on_market": 25, "list_to_sale_ratio": 0.96},
}


# ─── Existing Tools (copied from pricing_server.py — unchanged) ───────────────

@mcp.tool()
def get_market_price(
    address: str,
    property_type: str = "single_family"
) -> dict:
    """
    Get comprehensive market pricing data for a property.

    Returns comparable recent sales, estimated market value, price per sqft,
    and market analysis to help agents understand fair market value.

    Args:
        address: Full property address (e.g., "742 Evergreen Terrace, Austin, TX 78701")
        property_type: Type of property — single_family, condo, townhouse, multi_family

    Returns:
        Comprehensive pricing data including comparables, market analysis,
        and negotiation context.
    """
    normalized = address.lower().strip()
    property_data = PROPERTY_DATABASE.get(normalized)

    if not property_data:
        base_price = random.randint(380_000, 550_000)
        sqft = random.randint(1_800, 3_200)
        estimated_value = int(base_price * random.uniform(0.93, 0.99))
        comp_base = estimated_value
        property_data = {
            "display_address": address,
            "type": property_type,
            "bedrooms": random.randint(3, 5),
            "bathrooms": random.randint(2, 4),
            "sqft": sqft,
            "lot_sqft": random.randint(6_000, 12_000),
            "year_built": random.randint(1990, 2020),
            "list_price": base_price,
            "estimated_value": estimated_value,
            "price_per_sqft": int(base_price / sqft),
            "days_on_market": random.randint(5, 60),
            "neighborhood": "Austin Metro",
            "zip_code": "78701",
            "school_rating": random.randint(6, 9),
            "hoa_monthly": 0,
            "tax_annual": int(base_price * 0.020),
            "recent_upgrades": [],
            "comparable_sales": [
                {
                    "address": f"Similar Property {chr(65 + i)}, Austin, TX",
                    "price": int(comp_base * random.uniform(0.95, 1.05)),
                    "sqft": sqft + random.randint(-200, 200),
                    "price_per_sqft": int(comp_base / sqft),
                    "days_ago": random.randint(10, 60),
                    "bed_bath": "4/3"
                }
                for i in range(4)
            ]
        }

    comp_prices = [c["price"] for c in property_data["comparable_sales"]]
    avg_comp_price = int(sum(comp_prices) / len(comp_prices))
    median_comp_price = sorted(comp_prices)[len(comp_prices) // 2]
    price_variance_pct = round(
        (property_data["list_price"] - avg_comp_price) / avg_comp_price * 100, 1
    )

    zip_code = property_data.get("zip_code", "default")
    market = MARKET_DATA.get(zip_code, MARKET_DATA["default"])

    return {
        "address": property_data["display_address"],
        "property_details": {
            "type": property_data["type"],
            "bedrooms": property_data["bedrooms"],
            "bathrooms": property_data["bathrooms"],
            "sqft": property_data["sqft"],
            "lot_sqft": property_data.get("lot_sqft"),
            "year_built": property_data["year_built"],
            "school_district_rating": property_data.get("school_rating"),
            "hoa_monthly": property_data.get("hoa_monthly", 0),
            "annual_property_tax": property_data.get("tax_annual"),
            "recent_upgrades": property_data.get("recent_upgrades", []),
        },
        "pricing": {
            "list_price": property_data["list_price"],
            "estimated_market_value": property_data["estimated_value"],
            "price_per_sqft": property_data["price_per_sqft"],
            "days_on_market": property_data["days_on_market"],
        },
        "comparable_sales": property_data["comparable_sales"],
        "market_statistics": {
            "avg_comparable_price": avg_comp_price,
            "median_comparable_price": median_comp_price,
            "price_vs_comps_pct": price_variance_pct,
            "is_overpriced": price_variance_pct > 3,
            "valuation_summary": (
                f"Property is listed {'above' if price_variance_pct > 0 else 'below'} "
                f"comparable sales by {abs(price_variance_pct):.1f}%"
            ),
        },
        "market_conditions": {
            "zip_code": zip_code,
            "market_type": market["condition"],
            "inventory_months_supply": market["inventory_months"],
            "yoy_appreciation_pct": market["yoy_appreciation_pct"],
            "median_days_on_market": market["median_days_on_market"],
            "typical_list_to_sale_ratio": market["list_to_sale_ratio"],
        },
        "negotiation_context": {
            "fair_market_value_range": {
                "low": int(avg_comp_price * 0.97),
                "high": int(avg_comp_price * 1.03),
            },
            "buyer_recommendation": (
                f"Fair offer range: ${int(avg_comp_price * 0.97):,} – ${int(avg_comp_price * 1.03):,}. "
                f"Property is {'overpriced' if price_variance_pct > 3 else 'fairly priced'} "
                f"relative to recent sales."
            ),
        },
        "data_source": "MCP Pricing Server with Tax (solution file)",
    }


@mcp.tool()
def calculate_discount(
    base_price: float,
    market_condition: Literal["hot", "balanced", "cold"] = "balanced",
    days_on_market: int = 0,
    property_condition: Literal["excellent", "good", "fair", "poor"] = "good"
) -> dict:
    """
    Calculate appropriate discount range based on market conditions.

    Args:
        base_price: The listing price to calculate discount from
        market_condition: Market heat — "hot", "balanced", or "cold"
        days_on_market: Days the property has been listed
        property_condition: Physical condition of the property

    Returns:
        Discount analysis with suggested offer ranges and negotiation tips.
    """
    base_rates: dict[str, dict[str, float]] = {
        "hot":      {"min": 0.000, "max": 0.020},
        "balanced": {"min": 0.020, "max": 0.050},
        "cold":     {"min": 0.050, "max": 0.100},
    }

    dom_adjustment: float = 0.0
    if days_on_market >= 90:
        dom_adjustment = 0.040
    elif days_on_market >= 60:
        dom_adjustment = 0.025
    elif days_on_market >= 30:
        dom_adjustment = 0.012

    condition_adjustment: dict[str, float] = {
        "excellent": -0.010,
        "good":       0.000,
        "fair":       0.020,
        "poor":       0.050,
    }
    cond_adj = condition_adjustment.get(property_condition, 0.0)

    rates = base_rates.get(market_condition, base_rates["balanced"])
    min_discount = max(0, rates["min"] + dom_adjustment + cond_adj)
    max_discount = min(0.20, rates["max"] + dom_adjustment + cond_adj)

    offer_conservative = int(base_price * (1 - min_discount))
    offer_moderate = int(base_price * (1 - (min_discount + max_discount) / 2))
    offer_aggressive = int(base_price * (1 - max_discount))
    offer_ultra_aggressive = int(base_price * (1 - max_discount - 0.02))

    tips: list[str] = []
    if market_condition == "hot":
        tips.extend(["Market favors sellers — avoid lowball offers", "Be prepared for multiple offer situations"])
    elif market_condition == "cold":
        tips.extend(["Market favors buyers — room for aggressive negotiation", "Ask seller to cover closing costs"])
    else:
        tips.extend(["Balanced market — reasonable negotiation expected", "Use comparable sales data to justify your offer"])

    if days_on_market > 30:
        tips.append(f"Property has been on market {days_on_market} days — seller may be more motivated")

    return {
        "inputs": {"base_price": base_price, "market_condition": market_condition, "days_on_market": days_on_market, "property_condition": property_condition},
        "discount_analysis": {
            "min_discount_pct": round(min_discount * 100, 1),
            "max_discount_pct": round(max_discount * 100, 1),
            "dom_adjustment_pct": round(dom_adjustment * 100, 1),
            "condition_adjustment_pct": round(cond_adj * 100, 1),
        },
        "suggested_offer_prices": {
            "conservative": offer_conservative,
            "moderate": offer_moderate,
            "aggressive": offer_aggressive,
            "ultra_aggressive": offer_ultra_aggressive,
        },
        "expected_closing_price": int(base_price * (1 - min_discount - 0.01)),
        "reasoning": (
            f"In a {market_condition} market with {days_on_market} DOM and {property_condition} "
            f"condition: expect {min_discount*100:.0f}–{max_discount*100:.0f}% below asking."
        ),
        "negotiation_tips": tips,
        "data_source": "MCP Pricing Server with Tax (solution file)",
    }


# ─── EXERCISE 1 SOLUTION: The new tool ───────────────────────────────────────

@mcp.tool()
def get_property_tax_estimate(
    price: float,
    tax_rate: float = 0.02,
) -> dict:
    """
    Estimate annual property tax based on purchase price and local tax rate.

    SOLUTION EXPLANATION:
    This tool follows the exact same pattern as get_market_price and
    calculate_discount. The @mcp.tool() decorator does three things:
      1. Registers the function name as the discoverable tool name
      2. Inspects type hints to auto-generate JSON Schema parameters
      3. Serializes the return dict as a JSON text content block

    WHY THIS MATTERS FOR THE BUYER:
      $485,000 × 2% = $9,700/year = $808/month added to housing costs.
      A buyer who ignores property tax may over-offer relative to their
      actual monthly budget. Citing tax costs also strengthens their
      negotiation position: "High taxes justify a lower purchase price."

    Args:
        price: The listing or purchase price to estimate tax from
        tax_rate: Annual property tax rate as decimal (default 2% = Austin, TX)

    Returns:
        Annual and monthly tax estimates with negotiation context.
    """
    annual_tax = int(price * tax_rate)
    monthly_tax = round(annual_tax / 12, 2)

    if annual_tax > 10_000:
        assessment = "High property taxes — a meaningful factor in affordability."
    elif annual_tax > 7_000:
        assessment = "Moderate property taxes — typical for Austin metro."
    else:
        assessment = "Relatively low property taxes — buyer-friendly."

    return {
        "price": price,
        "tax_rate": tax_rate,
        "estimated_annual_tax": annual_tax,
        "estimated_monthly_tax": monthly_tax,
        "assessment": assessment,
        "negotiation_note": (
            f"Annual property tax of ${annual_tax:,} adds ${monthly_tax:,.0f}/month "
            f"to total housing costs. Buyers cite high taxes to justify lower offers."
        ),
        "data_source": "MCP Pricing Server with Tax (solution file)",
    }


# ─── Demo Mode ────────────────────────────────────────────────────────────────

def _run_demo(step_mode: bool) -> None:
    _header("Exercise 1 Solution — get_property_tax_estimate Tool")
    print("""
  This file is the COMPLETE, RUNNABLE SOLUTION for M2 Exercise 1.
  The original pricing_server.py is NOT modified.

  This server has all 3 tools:
    1. get_market_price       — existing tool (unchanged)
    2. calculate_discount     — existing tool (unchanged)
    3. get_property_tax_estimate  — NEW (Exercise 1 solution)

  Exercise 1 asked you to add get_property_tax_estimate using the
  @mcp.tool() decorator — the same pattern as the existing tools.
""")
    _wait(step_mode, "  [ENTER: see the @mcp.tool() pattern →] ")

    # ── Step 1: The pattern ───────────────────────────────────────────────────
    _section("Step 1 — The @mcp.tool() pattern (same as existing tools)")
    print("""
  The new tool uses the exact same 3-element pattern:

    @mcp.tool()                          ← registers tool, generates schema
    def get_property_tax_estimate(
        price: float,                    ← type hint → JSON Schema "number"
        tax_rate: float = 0.02,          ← default value preserved in schema
    ) -> dict:
        annual_tax = int(price * tax_rate)
        return {                         ← dict is auto-serialized to JSON
            "estimated_annual_tax": annual_tax,
            ...
        }

  That's all it takes. No config file. No manual registration.
  No OpenAPI spec. The decorator handles everything.

  When agents call list_tools(), they see 3 tools — including the new one.
""")
    _wait(step_mode, "  [ENTER: see the source code →] ")

    # ── Step 2: Source code ───────────────────────────────────────────────────
    _section("Step 2 — Full source of get_property_tax_estimate()")
    _print_source(get_property_tax_estimate, notes=[
        "annual_tax = int(price * tax_rate) — core calculation, one line",
        "monthly_tax = round(annual_tax / 12, 2) — agents cite this in negotiation",
        "assessment: 3 tiers — buyer uses this qualitative label to frame position",
        "negotiation_note: pre-formatted phrase agents can quote directly",
        "Pattern is identical to calculate_discount — no new concepts needed",
    ])
    _wait(step_mode, "  [ENTER: call the tool live →] ")

    # ── Step 3: Live call ─────────────────────────────────────────────────────
    _section("Step 3 — Live call: get_property_tax_estimate(485_000, 0.02)")
    result = get_property_tax_estimate(485_000, 0.02)
    print()
    print(f"  price:                  ${result['price']:,.0f}")
    print(f"  tax_rate:               {result['tax_rate'] * 100:.1f}%")
    print(f"  estimated_annual_tax:   ${result['estimated_annual_tax']:,}")
    print(f"  estimated_monthly_tax:  ${result['estimated_monthly_tax']:,.0f}/month")
    print(f"  assessment:             {result['assessment']}")
    print(f"  negotiation_note:")
    print(f"    {result['negotiation_note']}")
    _wait(step_mode, "  [ENTER: see all 3 tools together →] ")

    # ── Step 4: All tools together ────────────────────────────────────────────
    _section("Step 4 — All 3 tools registered on this server")
    tools = list(mcp._tool_manager._tools.keys())
    print()
    for i, tool_name in enumerate(tools, 1):
        print(f"  {i}. {tool_name}")
    print()
    print(f"  Total: {len(tools)} tools — agents discover these via list_tools()")
    print()
    print("  KEY INSIGHT:")
    print("  Adding a tool to an MCP server is O(1) work.")
    print("  Agents automatically discover it on next connection.")
    print("  No agent code changes needed to discover the new tool.")
    _wait(step_mode, "  [ENTER: see how the buyer agent uses it (Exercise 2 preview) →] ")

    # ── Step 5: Exercise 2 preview ────────────────────────────────────────────
    _section("Step 5 — Wiring into the buyer agent (Exercise 2)")
    print("""
  After adding the tool to the server, Exercise 2 wires it into the buyer:

  CHANGE 1 — BUYER_MCP_PLANNER_PROMPT (in buyer_simple.py):
    Add this line to the available tools list:
      - get_property_tax_estimate: {"price": number, "tax_rate": number}
    This teaches GPT-4o that the tool EXISTS and how to call it.

  CHANGE 2 — BUYER_SYSTEM_PROMPT (in buyer_simple.py):
    Add this to the strategy section:
      - Reference property tax estimates to strengthen your negotiation position
    This teaches the buyer WHY to use it in negotiation.

  CHANGE 3 — Nothing else!
    call_pricing_mcp() is generic — it takes any tool name and arguments
    and calls the server. No changes needed to the transport layer.
    This is the power of MCP: server and client evolve independently.

  WHY REACT PLANNING (not hardcoded calls)?
    Round 1: get_market_price + calculate_discount  (market context first)
    Round 2: calculate_discount                     (market already known)
    Round 3: get_property_tax_estimate              (fine-tuning near-final offer)
    = 4 total API calls vs 15 if hardcoded all tools every round (73% fewer)
""")


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="M2 Exercise 1 Solution — pricing server with tax tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python m2_mcp/solution/sol01_pricing_server_with_tax.py            # demo mode
  python m2_mcp/solution/sol01_pricing_server_with_tax.py --fast     # no pauses
  python m2_mcp/solution/sol01_pricing_server_with_tax.py --check    # verify tools load
  python m2_mcp/solution/sol01_pricing_server_with_tax.py --server   # stdio server mode
  python m2_mcp/solution/sol01_pricing_server_with_tax.py --sse --port 8003  # SSE mode
""",
    )
    parser.add_argument("--fast",   action="store_true", help="Skip interactive pauses")
    parser.add_argument("--server", action="store_true", help="Run as MCP stdio server")
    parser.add_argument("--check",  action="store_true", help="Verify tools load and exit")
    parser.add_argument("--sse",    action="store_true", help="Run as SSE HTTP server")
    parser.add_argument("--port",   type=int, default=8003, help="Port for SSE mode (default: 8003)")
    parser.add_argument("--host",   type=str, default="0.0.0.0", help="Host for SSE mode")
    args = parser.parse_args()

    if args.check:
        tools = list(mcp._tool_manager._tools.keys())
        print(f"pricing_server_with_tax OK  tools={tools}")
        sys.exit(0)
    elif args.sse:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        print(f"Real Estate Pricing MCP Server with Tax (SSE mode)")
        print(f"   Listening on: http://{args.host}:{args.port}/sse")
        print(f"   Tools: get_market_price, calculate_discount, get_property_tax_estimate")
        print(f"   Ctrl+C to stop.")
        mcp.run(transport="sse")
    elif args.server or not sys.stdin.isatty():
        mcp.run()
    else:
        _run_demo(step_mode=not args.fast)
