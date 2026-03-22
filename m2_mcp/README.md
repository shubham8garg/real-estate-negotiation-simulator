# Module 2 — MCP Servers (`m2_mcp`)

**Requires:** `GITHUB_TOKEN` for the GitHub demo. No API key needed for the pricing/inventory servers standalone.

This module introduces **MCP (Model Context Protocol)** — the standard that lets AI agents call external tools without knowing where the data comes from.

---

## What this module teaches

In Module 1, the negotiation used hardcoded prices (failure mode #8). The agents had no real market data — they just made up numbers.

MCP fixes that. It is a protocol that:
1. Lets a server **expose tools** (functions with typed inputs/outputs)
2. Lets a client **discover** those tools automatically (`list_tools`)
3. Lets a client **call** those tools over a standard interface (`call_tool`)

The agent doesn't need to know if the data comes from a database, an API, or a spreadsheet. It just calls the tool by name.

---

## File breakdown

### `github_demo_client.py` — Learn MCP with a tool you already know

Before building custom servers, this file connects to **GitHub's official MCP server** and calls its tools.

Why GitHub first? Because you already know what GitHub does. Seeing MCP work on a familiar tool makes the protocol click before you write your own.

**What it demonstrates:**
- Connecting to an MCP server over `stdio` transport
- Calling `list_tools` to discover what the server offers
- Calling a tool (`search_repositories`, etc.) with structured arguments
- Seeing how tools look to an LLM: as JSON schemas, not Python functions

**Prerequisites:**
- Node.js 18+ installed (`node --version`)
- A GitHub Personal Access Token (`repo` or `public_repo` scope)

```bash
export GITHUB_TOKEN=ghp_your_token_here
python m2_mcp/github_demo_client.py
```

---

### `sse_demo_client.py` — SSE client demo (connects over HTTP)

This script connects to the pricing and/or inventory servers running in **SSE mode** (HTTP) and calls their tools — the same protocol as `github_demo_client.py`, just a different transport.

**What it demonstrates:**
- Connecting to MCP servers via SSE (Server-Sent Events) transport
- Tool discovery and calling over HTTP
- Connecting to multiple servers from a single client

**Prerequisites:**
- Start the servers in SSE mode first (in separate terminals)

```bash
# Terminal 1:
python m2_mcp/pricing_server.py --sse --port 8001

# Terminal 2:
python m2_mcp/inventory_server.py --sse --port 8002

# Terminal 3 — run the client:
python m2_mcp/sse_demo_client.py                    # pricing server only
python m2_mcp/sse_demo_client.py --both              # both servers
```

---

### `pricing_server.py` — Custom MCP server for market pricing

This is the first custom MCP server. It wraps simulated real estate pricing data and exposes it as MCP tools.

**Tools it exposes:**

| Tool | What it does | Who uses it |
|---|---|---|
| `get_market_price(address, property_type)` | Returns comparable sales, estimated value, and market analysis | Both buyer and seller |
| `calculate_discount(base_price, market_condition, days_on_market, property_condition)` | Returns suggested offer ranges and negotiation tips | Both buyer and seller |

**Two transport modes (same server, different usage):**

```bash
# Teaching demo — default when run in a terminal (shows tool definitions and live calls)
python m2_mcp/pricing_server.py

# SSE — HTTP server, multiple clients can connect at once
python m2_mcp/pricing_server.py --sse --port 8001
```

In Modules 3 and 4, the agents start this server automatically as a subprocess (stdio mode is auto-detected). You don't need to run it manually.

---

### `inventory_server.py` — Custom MCP server for inventory + seller constraints

This server simulates an MLS (Multiple Listing Service) system. It has one public tool and one **seller-only** tool.

**Tools it exposes:**

| Tool | What it does | Who uses it |
|---|---|---|
| `get_inventory_level(zip_code)` | Returns active listings, days on market, market condition | Both buyer and seller |
| `get_minimum_acceptable_price(property_id)` | Returns the seller's absolute floor price | **Seller only** |

**The information asymmetry lesson:**

The buyer agent never connects to `get_minimum_acceptable_price`. This is intentional — in real estate, only the seller's agent knows the seller's walk-away price. The seller uses this tool to set a hard floor; the buyer has to negotiate without knowing it.

This is the same pattern used in real production systems: MCP access control means different agents get different tools.

```bash
# Teaching demo — default when run in a terminal (shows tool definitions + information asymmetry)
python m2_mcp/inventory_server.py

# SSE
python m2_mcp/inventory_server.py --sse --port 8002
```

---

## MCP in one diagram

```
AGENT                       MCP Protocol              SERVER
─────────────────           ────────────────          ──────────────────
"What tools exist?"
await session.list_tools() ─────────────────────────> Returns tool schemas
                                                       [{name, description,
                                                         inputSchema}]

"Call this tool"
await session.call_tool(    ─────────────────────────> Executes Python fn
  "get_market_price",
  {"address": "742..."}
)
                           <───────────────────────── Returns result dict
"Comps avg $462K,
listing is 4.9% above
market. I'll offer $425K."
```

The agent never imports your Python functions directly. It talks to the server over the protocol — the same way whether the server is local or remote.

---

## How to run

Both MCP servers run in **demo mode by default** when you run them in a terminal. No API keys needed.

```bash
# Teaching demos (step-by-step by default)
python m2_mcp/pricing_server.py        # walks through tool definitions + live calls
python m2_mcp/inventory_server.py      # walks through tools + information asymmetry

# Without pauses
python m2_mcp/pricing_server.py --fast
python m2_mcp/inventory_server.py --fast

# GitHub MCP demo (needs GITHUB_TOKEN + Node.js)
export GITHUB_TOKEN=ghp_your_token_here
python m2_mcp/github_demo_client.py

# SSE mode — run servers in separate terminals, then connect a client
python m2_mcp/pricing_server.py --sse --port 8001    # Terminal 1
python m2_mcp/inventory_server.py --sse --port 8002  # Terminal 2
python m2_mcp/sse_demo_client.py --both              # Terminal 3 (after servers are up)
```

**What to expect from `pricing_server.py` (demo mode):**
- Shows the `@mcp.tool()` decorator pattern with source code
- Calls `get_market_price` and `calculate_discount` live and prints results
- Explains the N×M problem MCP solves (N agents × M tools without MCP = N×M integrations)

**What to expect from `inventory_server.py` (demo mode):**
- Shows both tools: `get_inventory_level` (public) and `get_minimum_acceptable_price` (seller-only)
- Demonstrates the information asymmetry: buyer never sees the floor price
- Calls both tools live and prints the results

**Note on Modules 3 and 4:**
When agents in m3/m4 spawn these servers as subprocesses, they automatically run in stdio server mode (detected via stdin pipe). You never need to start them manually for m3/m4 to work.

---

## Exercises

| Exercise | Difficulty | Task |
|---|---|---|
| `ex01_find_mcp_tool.md` | `[Starter]` | Add a `get_property_tax_estimate` tool to the pricing server using `@mcp.tool()` |
| `ex02_compare_two_servers.md` | `[Core]` | Wire the new tool into the buyer agent's MCP planner prompt and test the full pipeline |
| `ex03_stretch_build_appraisal_server.md` | `[Stretch]` | Build an appraisal MCP server with comparable sales data and connect it to the seller agent |

Solutions are in `m2_mcp/solution/`. Each exercise includes a reflection question.

---

## Quick mental model
- If you want to see *how to build* an MCP server, read `pricing_server.py` (simpler, 2 tools) then `inventory_server.py` (adds the seller-only tool).
- The `@mcp.tool()` decorator is all you need to expose a Python function as an MCP tool.
- In Modules 3 and 4, both agents use these servers — you don't need to start them manually.
