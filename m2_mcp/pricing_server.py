"""
Real Estate Pricing MCP Server
================================
An MCP server that exposes real estate pricing tools to AI agents.

MCP CONCEPT:
  This server wraps simulated real estate pricing data (in production:
  Zillow API, Redfin, MLS database) and exposes it as MCP tools.
  Any MCP-compatible agent can discover and call these tools without
  knowing where the data comes from.

TRANSPORT OPTIONS:
  stdio (default) — client spawns this as a subprocess
    python pricing_server.py

  SSE (HTTP)      — runs as standalone HTTP server, multiple clients
    python pricing_server.py --sse --port 8001

TOOLS EXPOSED:
  • get_market_price(address, property_type)
      Returns comparable sales, estimated value, price analysis

  • calculate_discount(base_price, market_condition, days_on_market)
      Returns suggested offer range, discount percentages, negotiation tips

HOW AGENTS USE THIS:
  Buyer agent: Calls get_market_price to justify offers
               Calls calculate_discount to determine offer range
  Seller agent: Calls get_market_price to understand buyer's perspective
                Calls calculate_discount to anticipate buyer's strategy
"""

import argparse
import inspect
import json
import random
import sys
import textwrap
import time
from typing import Literal

# FastMCP is the Pythonic way to build MCP servers
# Install: pip install mcp
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


# ─── Initialize FastMCP Server ────────────────────────────────────────────────

mcp = FastMCP(
    "real-estate-pricing"
)


# ─── Simulated Data Store ─────────────────────────────────────────────────────
# In production, these would be calls to Zillow API, Redfin, MLS database, etc.
# MCP abstracts this — agents don't care WHERE the data comes from.

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
            {
                "address": "738 Evergreen Terrace, Austin, TX",
                "price": 458_000,
                "sqft": 2_350,
                "price_per_sqft": 195,
                "days_ago": 12,
                "bed_bath": "4/2"
            },
            {
                "address": "751 Evergreen Terrace, Austin, TX",
                "price": 471_500,
                "sqft": 2_520,
                "price_per_sqft": 187,
                "days_ago": 28,
                "bed_bath": "4/3"
            },
            {
                "address": "820 Maple Creek Dr, Austin, TX",
                "price": 456_000,
                "sqft": 2_280,
                "price_per_sqft": 200,
                "days_ago": 41,
                "bed_bath": "3/3"
            },
            {
                "address": "715 Bluebell Ave, Austin, TX",
                "price": 468_000,
                "sqft": 2_400,
                "price_per_sqft": 195,
                "days_ago": 55,
                "bed_bath": "4/3"
            },
        ]
    }
}

# Market condition data by ZIP code
MARKET_DATA: dict[str, dict] = {
    "78701": {
        "condition": "balanced",
        "inventory_months": 3.2,
        "yoy_appreciation_pct": 4.1,
        "median_days_on_market": 22,
        "list_to_sale_ratio": 0.97,  # homes sell for 97% of list
    },
    "78702": {
        "condition": "hot",
        "inventory_months": 1.5,
        "yoy_appreciation_pct": 8.3,
        "median_days_on_market": 9,
        "list_to_sale_ratio": 1.02,  # over asking in hot market
    },
    "78703": {
        "condition": "cold",
        "inventory_months": 6.8,
        "yoy_appreciation_pct": 1.2,
        "median_days_on_market": 45,
        "list_to_sale_ratio": 0.94,
    },
    "default": {
        "condition": "balanced",
        "inventory_months": 3.5,
        "yoy_appreciation_pct": 3.5,
        "median_days_on_market": 25,
        "list_to_sale_ratio": 0.96,
    }
}


# ─── MCP Tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def get_market_price(
    address: str,
    property_type: str = "single_family"
) -> dict:
    """
    Get comprehensive market pricing data for a property.

    Returns comparable recent sales, estimated market value, price per sqft,
    and market analysis to help agents understand fair market value.

    MCP NOTE: This tool abstracts the complexity of querying real estate
    databases. Agents call this tool without knowing whether data comes
    from Zillow, Redfin, MLS, or a local database.

    Args:
        address: Full property address (e.g., "742 Evergreen Terrace, Austin, TX 78701")
        property_type: Type of property — single_family, condo, townhouse, multi_family

    Returns:
        Comprehensive pricing data including comparables, market analysis,
        and negotiation context.
    """
    # Step 1) Normalize input so equivalent address strings map consistently.
    # Example: extra spaces/casing differences should still hit the same record.
    normalized = address.lower().strip()

    # Step 2) Try deterministic lookup first (repeatable workshop behavior).
    property_data = PROPERTY_DATABASE.get(normalized)

    if not property_data:
        # Step 3) Fallback path for unknown properties.
        # We synthesize plausible values so demos continue even for new addresses.
        # In production this branch would call an external data provider.
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

    # Step 4) Derive summary metrics that agents can cite in negotiation.
    # Keeping this logic in the server avoids duplicate calculations in clients.
    comp_prices = [c["price"] for c in property_data["comparable_sales"]]
    avg_comp_price = int(sum(comp_prices) / len(comp_prices))
    median_comp_price = sorted(comp_prices)[len(comp_prices) // 2]
    price_variance_pct = round(
        (property_data["list_price"] - avg_comp_price) / avg_comp_price * 100, 1
    )

    # Step 5) Attach ZIP-level market context to ground offer strategy.
    zip_code = property_data.get("zip_code", "default")
    market = MARKET_DATA.get(zip_code, MARKET_DATA["default"])

    # Final MCP payload: structured JSON-friendly dict returned to caller.
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
        "data_source": "MCP Pricing Server (simulated MLS/Zillow data)",
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

    Provides data-driven discount recommendations that agents can use
    to formulate and justify their negotiation positions.

    MCP NOTE: This tool encapsulates pricing business logic that would
    otherwise be duplicated across agents. By exposing it as an MCP tool,
    both the buyer (to determine offer) and seller (to anticipate buyer
    strategy) can use the same logic from the same source.

    Args:
        base_price: The listing price to calculate discount from
        market_condition: Market heat — "hot" (seller's market), "balanced", or "cold" (buyer's market)
        days_on_market: Days the property has been listed (longer = more negotiable)
        property_condition: Physical condition of the property

    Returns:
        Discount analysis with suggested offer ranges and negotiation tips.
    """
    # Step 1) Start with baseline discount bands from market temperature.
    base_rates: dict[str, dict[str, float]] = {
        "hot":      {"min": 0.000, "max": 0.020},   # 0–2%   (seller's market)
        "balanced": {"min": 0.020, "max": 0.050},   # 2–5%
        "cold":     {"min": 0.050, "max": 0.100},   # 5–10%  (buyer's market)
    }

    # Step 2) Add time-on-market pressure (stale listings usually become flexible).
    dom_adjustment: float = 0.0
    if days_on_market >= 90:
        dom_adjustment = 0.040
    elif days_on_market >= 60:
        dom_adjustment = 0.025
    elif days_on_market >= 30:
        dom_adjustment = 0.012

    # Step 3) Add condition-based pricing pressure.
    # Worse condition => larger expected discount.
    condition_adjustment: dict[str, float] = {
        "excellent": -0.010,  # less room to negotiate
        "good":       0.000,
        "fair":       0.020,  # more room to negotiate
        "poor":       0.050,  # significant discount expected
    }
    cond_adj = condition_adjustment.get(property_condition, 0.0)

    # Step 4) Combine effects and clamp to sane bounds.
    rates = base_rates.get(market_condition, base_rates["balanced"])
    min_discount = max(0, rates["min"] + dom_adjustment + cond_adj)
    max_discount = min(0.20, rates["max"] + dom_adjustment + cond_adj)  # cap at 20%

    # Step 5) Convert discount percentages into concrete offer anchors.
    offer_conservative = int(base_price * (1 - min_discount))
    offer_moderate = int(base_price * (1 - (min_discount + max_discount) / 2))
    offer_aggressive = int(base_price * (1 - max_discount))
    offer_ultra_aggressive = int(base_price * (1 - max_discount - 0.02))

    # Step 6) Produce qualitative guidance so the output is not only numeric.
    tips: list[str] = []

    if market_condition == "hot":
        tips.extend([
            "Market favors sellers — avoid lowball offers",
            "Consider waiving minor contingencies to strengthen offer",
            "Be prepared for multiple offer situations",
            "Move quickly; good properties don't last",
        ])
    elif market_condition == "cold":
        tips.extend([
            "Market favors buyers — room for aggressive negotiation",
            "Request all inspection contingencies",
            "Ask seller to cover closing costs",
            "Request repairs or price reductions after inspection",
        ])
    else:
        tips.extend([
            "Balanced market — reasonable negotiation expected",
            "Keep standard contingencies (inspection, financing)",
            "Use comparable sales data to justify your offer",
        ])

    if days_on_market > 30:
        tips.append(
            f"Property has been on market {days_on_market} days — "
            "seller may be more motivated to negotiate"
        )

    if property_condition in ("fair", "poor"):
        tips.append("Request inspection and estimate repair costs before finalizing offer")

    # Final MCP payload returned to client/agent.
    return {
        "inputs": {
            "base_price": base_price,
            "market_condition": market_condition,
            "days_on_market": days_on_market,
            "property_condition": property_condition,
        },
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
            f"property condition: expect {min_discount*100:.0f}–{max_discount*100:.0f}% "
            f"below asking price. Typical closing: ${int(base_price * (1 - min_discount - 0.01)):,}."
        ),
        "negotiation_tips": tips,
        "data_source": "MCP Pricing Server (simulated market analysis)",
    }


# ─── Demo Mode ────────────────────────────────────────────────────────────────

def _run_demo(step_mode: bool) -> None:
    """
    Walk through the pricing server's structure and tools in teaching mode.
    Calls the tool functions directly (no MCP protocol needed for local demo).
    """
    _header("Real Estate Pricing MCP Server — How MCP Servers Work")
    print("""
  This server exposes 2 MCP tools to agents:
    1. get_market_price(address, property_type)
    2. calculate_discount(base_price, market_condition, days_on_market)

  Both buyer AND seller agents call these tools.
  The server abstracts where the data comes from — Zillow, Redfin, or MLS.

  This is the core MCP value: N agents × M servers, not N×M custom integrations.
""")
    _wait(step_mode, "  [ENTER: see how a tool is defined with @mcp.tool() →] ")

    # ── Step 1: @mcp.tool() concept ───────────────────────────────────────────
    _section("Step 1: The @mcp.tool() decorator — how tools are registered")
    print("""
  Without MCP: every agent writes its own HTTP client for every data source.
  With MCP:    wrap any Python function with @mcp.tool() — auto-discoverable.

  mcp = FastMCP("real-estate-pricing")   ← one line to create the server

  @mcp.tool()                            ← one decorator registers the function
  def get_market_price(address: str, property_type: str = "single_family") -> dict:
      ...

  FastMCP reads the function signature → builds a JSON schema → registers it.
  When an agent calls session.list_tools(), it receives the complete schema.
  No OpenAPI spec. No handwritten docs. No manual function registration.

  The LLM then uses that schema to know EXACTLY how to call the tool.
""")
    _wait(step_mode, "  [ENTER: see the get_market_price tool source →] ")

    # ── Step 2: get_market_price source ───────────────────────────────────────
    _section("Tool 1 of 2: get_market_price() — full source")
    print("""
  What the buyer and seller BOTH call to understand fair market value.
  In production: Zillow API, Redfin, MLS database.
  In our demo:   reads from PROPERTY_DATABASE dict — same interface either way.
  The caller (agent) doesn't know or care which data source is behind it.
""")
    _print_source(get_market_price, notes=[
        "normalized = address.lower().strip()  — case-insensitive lookup",
        "PROPERTY_DATABASE.get(normalized)  — deterministic for workshop demos",
        "Fallback path: synthesizes plausible values for unknown addresses",
        "Returns rich dict: comparables, market stats, negotiation_context",
        "Buyer agent cites avg_comparable_price to justify every offer",
        "Seller agent uses same data to understand buyer's perspective",
    ])
    _wait(step_mode, "  [ENTER: call get_market_price() live →] ")

    # ── Step 3: Call get_market_price live ────────────────────────────────────
    _section("Live call: get_market_price('742 Evergreen Terrace, Austin, TX 78701')")
    print()
    result = get_market_price("742 Evergreen Terrace, Austin, TX 78701", "single_family")

    p = result["property_details"]
    pricing = result["pricing"]
    ms = result["market_statistics"]
    mc = result["market_conditions"]
    nc = result["negotiation_context"]
    comps = result["comparable_sales"]

    print(f"  address:           {result['address']}")
    print(f"  property:          {p['bedrooms']}bd/{p['bathrooms']}ba, {p['sqft']:,} sqft, built {p['year_built']}")
    print(f"  recent_upgrades:   {len(p['recent_upgrades'])} items (kitchen, roof, HVAC)")
    print()
    print(f"  list_price:        ${pricing['list_price']:,}")
    print(f"  estimated_value:   ${pricing['estimated_market_value']:,}  ← what the market thinks it's worth")
    print(f"  days_on_market:    {pricing['days_on_market']}")
    print()
    print(f"  avg_comp_price:    ${ms['avg_comparable_price']:,}  ({len(comps)} comparable sales)")
    print(f"  valuation_summary: {ms['valuation_summary']}")
    print()
    print(f"  market_type:       {mc['market_type']}  ({mc['inventory_months_supply']} months supply)")
    print(f"  list-to-sale ratio:{mc['typical_list_to_sale_ratio']}  (homes close at ~{int(mc['typical_list_to_sale_ratio']*100)}% of list)")
    print()
    low = nc["fair_market_value_range"]["low"]
    high = nc["fair_market_value_range"]["high"]
    print(f"  fair_value_range:  ${low:,} – ${high:,}")
    print(f"  buyer_rec:         {nc['buyer_recommendation'][:80]}...")
    print()
    print(f"  This dict has {len(result)} top-level keys — agents cite specific fields in every message.")
    _wait(step_mode, "  [ENTER: see the calculate_discount tool →] ")

    # ── Step 4: calculate_discount source ─────────────────────────────────────
    _section("Tool 2 of 2: calculate_discount() — full source")
    print("""
  What the buyer calls to determine their offer range.
  The seller also calls this to ANTICIPATE the buyer's strategy.
  Both sides use the same pricing logic from the same server — grounded negotiation.

  This is information symmetry: both parties reason from the same market data.
  Contrast with get_minimum_acceptable_price() in inventory_server.py
    which is SELLER-ONLY — that's information ASYMMETRY enforced by MCP access control.
""")
    _print_source(calculate_discount, notes=[
        "base_rates: hot=0–2%, balanced=2–5%, cold=5–10% discount off asking",
        "dom_adjustment: stale listings (30/60/90+ days) → 1.2/2.5/4% more room",
        "condition_adjustment: poor property condition → up to 5% extra discount",
        "Returns 4 offer anchors: conservative, moderate, aggressive, ultra_aggressive",
        "Also returns negotiation_tips — LLM uses these in its message to the seller",
        "data_source field: 'MCP Pricing Server (simulated)' — caller always knows origin",
    ])
    _wait(step_mode, "  [ENTER: call calculate_discount() live →] ")

    # ── Step 5: Call calculate_discount live ──────────────────────────────────
    _section("Live call: calculate_discount(485_000, 'balanced', 18, 'good')")
    print()
    result2 = calculate_discount(485_000, "balanced", 18, "good")
    da = result2["discount_analysis"]
    so = result2["suggested_offer_prices"]
    print(f"  base_price:         $485,000")
    print(f"  market_condition:   balanced")
    print(f"  days_on_market:     18  (relatively fresh listing)")
    print()
    print(f"  discount_range:     {da['min_discount_pct']}% – {da['max_discount_pct']}%")
    print(f"  dom_adjustment:     +{da['dom_adjustment_pct']}%")
    print()
    print(f"  Suggested offer prices:")
    print(f"    conservative:     ${so['conservative']:,}   (safest — lowest discount)")
    print(f"    moderate:         ${so['moderate']:,}   (middle ground)")
    print(f"    aggressive:       ${so['aggressive']:,}   (pushes the range)")
    print(f"    ultra_aggressive: ${so['ultra_aggressive']:,}   (risks rejection)")
    print()
    print(f"  reasoning:  {result2['reasoning']}")
    print()
    print(f"  negotiation_tips ({len(result2['negotiation_tips'])}):")
    for tip in result2["negotiation_tips"]:
        print(f"    • {tip}")
    _wait(step_mode, "  [ENTER: see the N×M problem this server solves →] ")

    # ── Step 6: N×M problem ───────────────────────────────────────────────────
    _section("Why MCP? The N×M Integration Problem")
    print("""
  WITHOUT MCP — every agent integrates every data source directly:
  ┌────────────────┬──────────────┬──────────────┬──────────────┐
  │                │  Zillow API  │  Redfin API  │  MLS Direct  │
  ├────────────────┼──────────────┼──────────────┼──────────────┤
  │  Buyer agent   │  custom code │  custom code │  custom code │
  │  Seller agent  │  custom code │  custom code │  custom code │
  │  LangGraph node│  custom code │  custom code │  custom code │
  └────────────────┴──────────────┴──────────────┴──────────────┘
  = 3 agents × 3 data sources = 9 custom integrations

  WITH MCP (this server):
  ┌────────────────┬──────────────────────────────────────────────┐
  │                │       pricing_server.py  (one server)        │
  ├────────────────┼──────────────────────────────────────────────┤
  │  Buyer agent   │  call_tool("get_market_price")               │
  │  Seller agent  │  call_tool("get_market_price")               │
  │  LangGraph node│  call_tool("get_market_price")               │
  └────────────────┴──────────────────────────────────────────────┘
  = 3 agents × 1 MCP call = 3 integrations

  Switching data source (Zillow → Redfin → live MLS)?
    WITHOUT MCP: modify code in every agent
    WITH MCP:    change ONE function in pricing_server.py — agents never know
""")
    _wait(step_mode, "  [ENTER: see how agents connect to this server →] ")

    # ── Step 7: How agents connect ────────────────────────────────────────────
    _section("How agents connect — stdio vs SSE transport")
    print("""
  STDIO TRANSPORT (Module 4 — buyer_adk.py, seller_adk.py):
    MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["m2_mcp/pricing_server.py"],  ← spawns THIS file as subprocess
            )
        )
    )
    tools = await toolset.get_tools()  ← calls MCP list_tools(), gets schemas
    # Agent now has get_market_price + calculate_discount as callable tools

  SSE TRANSPORT (network mode — multiple simultaneous clients):
    Terminal 1: python m2_mcp/pricing_server.py --sse --port 8001
    Terminal 2: python m2_mcp/sse_demo_client.py          ← connects over HTTP
    Terminal 3: python m2_mcp/sse_demo_client.py --both   ← connects to both servers

  Same MCP protocol. Same tools. Same agent code. Just a different transport.

  KEY INSIGHT:
    The agent doesn't know or care whether it's using stdio or SSE.
    It calls list_tools() and call_tool() the same way either way.
""")


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Real Estate Pricing MCP Server — supports stdio, SSE, and demo modes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python pricing_server.py              # demo mode (default when run in a terminal)
  python pricing_server.py --fast       # demo without pauses
  python pricing_server.py --check      # verify server loads correctly
  python pricing_server.py --sse --port 8001  # HTTP/SSE server mode
  python pricing_server.py --server     # force stdio server mode (agents use this automatically)
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
        help="Use SSE transport instead of stdio. Runs as HTTP server."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port number for SSE transport (default: 8001)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host for SSE transport (default: 0.0.0.0)"
    )
    args = parser.parse_args()

    if args.check:
        # Lightweight health check used by tests/scripts to validate imports/tool registration.
        tools = list(mcp._tool_manager._tools.keys())
        print(f"pricing_server OK  tools={tools}")
        sys.exit(0)
    elif args.sse:
        # SSE mode: run as HTTP endpoint for network clients and multi-client setups.
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        print(f"Real Estate Pricing MCP Server (SSE mode)")
        print(f"   Listening on: http://{args.host}:{args.port}/sse")
        print(f"   Connect via: SseServerParams(url='http://localhost:{args.port}/sse')")
        print(f"   Tools: get_market_price, calculate_discount")
        print(f"   Ctrl+C to stop.")
        mcp.run(transport="sse")
    elif args.server or not sys.stdin.isatty():
        # stdio server mode: either explicitly requested (--server) or auto-detected because
        # stdin is a pipe — meaning an agent spawned this process as a subprocess.
        mcp.run()
    else:
        # Interactive terminal (default): run the teaching demo.
        # Students can run: python pricing_server.py
        # --demo flag is accepted as an alias for backwards compatibility.
        _run_demo(step_mode=not args.fast)
