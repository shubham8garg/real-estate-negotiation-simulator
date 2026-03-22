"""
GitHub MCP Demo Client
======================
This script demonstrates connecting to GitHub's official MCP server
and calling its tools — the same pattern used by our real estate agents.

WHY THIS DEMO EXISTS:
  GitHub is a tool every engineer knows. By seeing MCP work with GitHub
  first, you understand the protocol before we introduce our custom servers.
  The pattern is IDENTICAL for our pricing_server.py and inventory_server.py.

PREREQUISITES:
  1. Node.js 18+ installed (for npx)
  2. GitHub Personal Access Token
     - Go to: GitHub → Settings → Developer Settings → Personal Access Tokens → Classic
     - Scopes needed: repo, read:org (or just public_repo for public repos)
  3. Set environment variable: GITHUB_TOKEN=ghp_your_token_here

HOW TO RUN:
  export GITHUB_TOKEN=ghp_your_token_here
  python m2_mcp/github_demo_client.py

WHAT THIS DEMONSTRATES:
  1. Connecting to an MCP server via stdio transport
  2. Listing available tools (auto-discovery)
  3. Calling tools with structured arguments
  4. Parsing structured results
  5. How the LLM "sees" MCP tools (as function schemas)
"""

import asyncio
import json
import os
import sys
import time
from typing import Any

# MCP Python SDK
# Install: pip install mcp
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


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


def _load_env_file_if_present(env_path: str = ".env") -> None:
    """
    Load KEY=VALUE pairs from a local .env file into process environment.

    Notes:
    - Existing environment variables are preserved (shell/export wins).
    - This keeps the demo easy to run across shells without extra setup.
    """
    if not os.path.exists(env_path):
        return

    try:
        with open(env_path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        # Non-fatal for demo use; normal env vars may still be present.
        pass


# ─── Configuration ────────────────────────────────────────────────────────────

_load_env_file_if_present()

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()

# Catch: unset, empty string, or still set to the placeholder value
_PLACEHOLDER_PREFIXES = ("your_token", "ghp_your", "<your", "TOKEN_HERE")
if not GITHUB_TOKEN or any(GITHUB_TOKEN.lower().startswith(p) for p in _PLACEHOLDER_PREFIXES):
    print("ERROR: GITHUB_TOKEN environment variable is not set (or is still a placeholder).")
    print("   Get a token at: GitHub -> Settings -> Developer Settings -> Personal Access Tokens")
    print("   Then run: export GITHUB_TOKEN=ghp_your_token")
    sys.exit(1)


# ─── Demo Sections ────────────────────────────────────────────────────────────

async def demo_section_1_connection(session: ClientSession, step_mode: bool = True) -> None:
    """
    DEMO SECTION 1: Connecting and Initializing
    =============================================
    Shows how a client establishes a connection with an MCP server.
    Under the hood, this sends:
        {"jsonrpc": "2.0", "method": "initialize", "params": {...}}
    """
    _header("SECTION 1: Connection & Initialization")
    print("""
  Connected to GitHub MCP server via stdio transport.

  What just happened under the hood:
    1. Our Python process spawned a child process:
         npx -y @modelcontextprotocol/server-github
    2. Communication via stdin/stdout pipes (stdio transport)
    3. Sent:  {"jsonrpc": "2.0", "method": "initialize", "params": {...}}
    4. Server responded with its capabilities

  This is IDENTICAL to how our buyer agent connects to pricing_server.py:
    Instead of npx, it spawns: python m2_mcp/pricing_server.py
    Same JSON-RPC handshake. Same stdio pipes. Same protocol.
""")
    _wait(step_mode, "  [ENTER: see tool discovery →] ")


async def demo_section_2_tool_discovery(session: ClientSession, step_mode: bool = True) -> list:
    """
    DEMO SECTION 2: Tool Discovery (list_tools)
    =============================================
    This is the key MCP feature — auto-discovery of available tools.
    When an LLM agent calls list_tools(), it gets back complete JSON schemas
    for every available function. The LLM then knows EXACTLY how to call each tool.

    Compare to:
    - REST APIs: You must read documentation manually
    - OpenAPI: You write a spec, then generate code
    - MCP: Tools self-describe their schemas automatically
    """
    _header("SECTION 2: Tool Discovery — session.list_tools()")
    print("""
  This is the KEY MCP feature: auto-discovery.
  The agent calls session.list_tools() → receives full JSON schemas for every tool.
  No docs needed. No manual function registration. The LLM knows exactly how to call each tool.

  Compare to traditional approaches:
    REST API:  read documentation, write auth, construct URL, parse response manually
    OpenAPI:   write a YAML spec, generate client code, handle versioning
    MCP:       call list_tools() — schemas are automatically generated from @mcp.tool()
""")
    _wait(step_mode, "  [ENTER: list all GitHub MCP tools →] ")

    tools_response = await session.list_tools()
    tools = tools_response.tools

    _section(f"GitHub MCP server exposes {len(tools)} tools")
    print()
    for i, tool in enumerate(tools, 1):
        print(f"  {i:2}. {tool.name}")
        print(f"       {tool.description[:70]}...")
        print()

    print("  This is what an LLM agent sees when it connects to any MCP server.")
    print("  The agent doesn't need to know GitHub's API — it learns from the schemas.")
    _wait(step_mode, "  [ENTER: see the full JSON schema for search_repositories →] ")

    _section("Full JSON schema for 'search_repositories' (what the LLM receives)")
    print("""
  This schema is what the LLM sees. It uses it to construct tool calls.
  Same pattern in our pricing_server.py — every @mcp.tool() generates a schema.
""")
    for tool in tools:
        if tool.name == "search_repositories":
            schema = {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.inputSchema.model_dump() if hasattr(tool.inputSchema, "model_dump") else tool.inputSchema,
            }
            text = json.dumps(schema, indent=2)
            for line in text.split("\n")[:40]:
                print("  " + line)
            if len(text.split("\n")) > 40:
                print("  ... (truncated)")
            break
    print()
    _wait(step_mode, "  [ENTER: call tools live →] ")

    return tools


async def demo_section_3_tool_calls(session: ClientSession, step_mode: bool = True) -> None:
    """
    DEMO SECTION 3: Calling Tools
    ==============================
    Shows how to call an MCP tool with structured arguments.
    This is IDENTICAL to how our buyer agent calls get_market_price().
    """
    _header("SECTION 3: Calling Tools — session.call_tool()")
    print("""
  Calling a tool is one line: await session.call_tool(name, arguments)
  This is IDENTICAL to how our real estate agents call:
    get_market_price("742 Evergreen Terrace, Austin, TX 78701")
    get_inventory_level("78701")
    get_minimum_acceptable_price("742-evergreen-austin-78701")

  The pattern: discover → call → parse result. Same for GitHub or our servers.
""")
    _wait(step_mode, "  [ENTER: Tool Call 1 — get_me() →] ")

    tools_response = await session.list_tools()
    tools_by_name = {tool.name: tool for tool in tools_response.tools}

    def build_args_from_schema(tool_name: str, mappings: dict[str, Any]) -> dict[str, Any]:
        """Build arguments using only keys present in the tool's input schema."""
        tool = tools_by_name.get(tool_name)
        if tool is None:
            return {}

        input_schema = tool.inputSchema.model_dump() if hasattr(tool.inputSchema, "model_dump") else tool.inputSchema
        properties = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}

        resolved_args: dict[str, Any] = {}
        for param_name, candidate_values in mappings.items():
            if param_name not in properties:
                continue
            for candidate in candidate_values:
                if candidate is not None:
                    resolved_args[param_name] = candidate
                    break

        return resolved_args

    # ── Tool Call 1: Get current user ────────────────────────────────────────
    _section("Tool Call 1: get_me()")
    print("""
  Purpose:   Get the authenticated user's info
  Arguments: none — the server uses GITHUB_TOKEN from its environment
  Under the hood:  {"jsonrpc":"2.0","method":"tools/call","params":{"name":"get_me","arguments":{}}}
""")
    if "get_me" in tools_by_name:
        try:
            me_result = await session.call_tool("get_me", {})
            me_data = _parse_tool_result(me_result)
            print(f"  Result:")
            print(f"    Username:     {me_data.get('login', 'N/A')}")
            print(f"    Name:         {me_data.get('name', 'N/A')}")
            print(f"    Public repos: {me_data.get('public_repos', 'N/A')}")
            print()
        except Exception as e:
            print(f"  get_me failed: {e}")
            print()
    else:
        print("  Skipped: current server version does not expose get_me().")
        print()
    _wait(step_mode, "  [ENTER: Tool Call 2 — search_repositories() →] ")

    # ── Tool Call 2: Search repositories ─────────────────────────────────────
    _section("Tool Call 2: search_repositories(query='real estate python mcp')")
    print("""
  Purpose:   Search GitHub for repositories — same as an agent researching the domain
  This is the same call pattern as:
    get_market_price("742 Evergreen Terrace, Austin, TX 78701", "single_family")
  in our real estate pricing server.
""")
    _wait(step_mode, "  [ENTER: run search →] ")

    try:
        search_repos_args = build_args_from_schema(
            "search_repositories",
            {
                "query": ["real estate pricing python"],
                "q": ["real estate pricing python"],
                "perPage": [5],
                "per_page": [5],
                "limit": [5],
            },
        )
        search_result = await session.call_tool(
            "search_repositories",
            search_repos_args,
        )
        search_data = _parse_tool_result(search_result)

        repos = search_data.get("items", [])
        total = search_data.get("total_count", 0)

        print(f"   Found {total} repositories. Top {len(repos)}:")
        print()
        for repo in repos:
            print(f"      stars={repo.get('stargazers_count', 0):5} | {repo.get('full_name', 'N/A')}")
            print(f"             {(repo.get('description') or 'No description')[:60]}")
            print()

    except Exception as e:
        print(f"  search_repositories failed: {e}")
        print()
    _wait(step_mode, "  [ENTER: Tool Call 3 — search_code() →] ")

    # ── Tool Call 3: Search code ──────────────────────────────────────────────
    _section("Tool Call 3: search_code(query='def negotiate real estate python')")
    print("""
  Purpose:  Search code across GitHub — like an agent finding reference implementations
""")
    _wait(step_mode, "  [ENTER: run search →] ")

    try:
        search_code_args = build_args_from_schema(
            "search_code",
            {
                "query": ["def negotiate real estate python"],
                "q": ["def negotiate real estate python"],
                "perPage": [3],
                "per_page": [3],
                "limit": [3],
            },
        )
        code_result = await session.call_tool(
            "search_code",
            search_code_args,
        )
        code_data = _parse_tool_result(code_result)
        items = code_data.get("items", [])

        print(f"   Found {code_data.get('total_count', 0)} code matches. Top {len(items)}:")
        for item in items[:3]:
            print(f"      {item.get('repository', {}).get('full_name', 'N/A')} -> {item.get('name', 'N/A')}")
        print()

    except Exception as e:
        print(f"  search_code failed: {e}")
        print()
    _wait(step_mode, "  [ENTER: see MCP vs direct API comparison →] ")


async def demo_section_4_comparison(session: ClientSession, step_mode: bool = True) -> None:
    """
    DEMO SECTION 4: MCP vs Direct API Comparison
    =============================================
    Shows the difference between calling GitHub via MCP vs direct REST API.
    """
    _header("SECTION 4: MCP vs Direct GitHub API — Side by Side")

    print("WITHOUT MCP (direct API call):")
    print("-" * 40)
    print("""
  import requests

  headers = {
      "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
      "Accept": "application/vnd.github+json"
  }
  response = requests.get(
      "https://api.github.com/search/repositories",
      headers=headers,
      params={"q": "real estate python", "per_page": 5}
  )
  repos = response.json()["items"]
  # You wrote auth, URL construction, params, response parsing manually.
  # Every agent that needs GitHub must duplicate this code.
""")

    print("WITH MCP (our demo above):")
    print("-" * 40)
    print("""
  result = await session.call_tool(
      "search_repositories",
      {"query": "real estate python", "perPage": 5}
  )
  repos = parse_result(result)
  # Auth is handled by the MCP server (via GITHUB_TOKEN env var)
  # Schema is auto-discovered (no docs needed)
  # Every agent reuses the same server
  # Switching from GitHub to GitLab? Swap server, same client code.
""")

    print("""
  KEY INSIGHT:
    Our real estate pricing server works EXACTLY the same way.
    Instead of GitHub's REST API, it wraps Zillow/MLS pricing data.
    Our buyer and seller agents call it with the SAME client pattern.

    Any MCP-compatible server. Same client code. Different data.
    That's the N×M problem solved.
""")
    _wait(step_mode, "  [ENTER: connect this to our workshop →] ")


async def demo_section_5_connection_to_our_project(session: ClientSession, step_mode: bool = True) -> None:
    """
    DEMO SECTION 5: Connecting This to Our Workshop
    ================================================
    Shows how everything learned here applies to our negotiation simulator.
    """
    _header("SECTION 5: How This Connects to Our Workshop")

    print("""
  ╔══════════════════════════════╦══════════════════════════════════════╗
  ║  GitHub MCP Server           ║  Our Real Estate MCP Servers         ║
  ╠══════════════════════════════╬══════════════════════════════════════╣
  ║  npx @modelcontextprotocol/  ║  python m2_mcp/pricing_server.py     ║
  ║       server-github          ║                                      ║
  ╠══════════════════════════════╬══════════════════════════════════════╣
  ║  search_repositories()       ║  get_market_price()                  ║
  ║  get_file_contents()         ║  calculate_discount()                ║
  ║  create_issue()              ║  get_inventory_level()               ║
  ║  list_pull_requests()        ║  get_minimum_acceptable_price()      ║
  ╠══════════════════════════════╬══════════════════════════════════════╣
  ║  GITHUB_TOKEN env var        ║  (no auth for our demo server)       ║
  ║  stdio transport             ║  stdio transport (agents use this)   ║
  ║  (SSE not shown here)        ║  SSE transport (--sse --port 8001)   ║
  ╚══════════════════════════════╩══════════════════════════════════════╝

  The buyer and seller agents connect to our MCP servers using the
  EXACT same MCPClientSession / MCPToolset pattern you just saw here.

  Next steps:
    python m2_mcp/pricing_server.py --demo      ← see tools called live
    python m2_mcp/inventory_server.py --demo    ← see information asymmetry
    python m2_mcp/sse_demo_client.py --both     ← SSE transport demo
""")


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


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main(step_mode: bool = True) -> None:
    """
    Main function — runs all demo sections sequentially.

    This function demonstrates the complete MCP client lifecycle:
    1. Create server parameters (how to spawn/connect to the server)
    2. Open the transport connection (stdio pipe)
    3. Create a client session
    4. Initialize the session (MCP handshake)
    5. Use the session to call tools
    6. Clean up when done (context managers handle this)
    """
    _header("GitHub MCP Server — Understanding MCP via a Tool You Already Know")
    print("""
  Why GitHub? Every engineer knows GitHub's API.
  By seeing MCP work with GitHub first, you understand the protocol
  before we introduce our custom real estate servers.

  The pattern is IDENTICAL for our pricing_server.py and inventory_server.py.

  5 sections:
    1. Connection & initialization (the MCP handshake)
    2. Tool discovery (list_tools — auto-discovery from schemas)
    3. Calling tools (call_tool — structured args, structured results)
    4. MCP vs direct API (side-by-side comparison)
    5. How this connects to our real estate agents

  Controls: ENTER advances. Ctrl-C to exit at any time.
""")
    _wait(step_mode, "  [ENTER: connect to GitHub MCP server →] ")

    # Define how to connect to GitHub's MCP server
    # The MCP server is spawned as a subprocess via `npx`
    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={
            **os.environ,  # inherit all system environment variables
            "GITHUB_PERSONAL_ACCESS_TOKEN": GITHUB_TOKEN,
        }
    )

    print(f"  Connecting to GitHub MCP server...")
    print(f"    Command:   npx -y @modelcontextprotocol/server-github")
    print(f"    Transport: stdio (subprocess pipes)")
    token_display = f"{GITHUB_TOKEN[:8]}..." if len(GITHUB_TOKEN) > 8 else "(set)"
    print(f"    Token:     {token_display}")
    print()

    # The stdio_client context manager:
    # - Spawns the npx subprocess
    # - Sets up stdin/stdout pipes
    # - Returns (read_stream, write_stream) for the session
    # - Cleans up the subprocess on exit
    async with stdio_client(server_params) as (read, write):

        # ClientSession context manager:
        # - Wraps the streams in MCP protocol
        # - Handles JSON-RPC message framing
        # - Provides high-level methods: list_tools, call_tool, etc.
        async with ClientSession(read, write) as session:

            # CRITICAL: Must initialize before any other calls
            # This performs the MCP handshake (exchange capabilities)
            await session.initialize()

            # Run all demo sections with step mode
            await demo_section_1_connection(session, step_mode)
            tools = await demo_section_2_tool_discovery(session, step_mode)
            await demo_section_3_tool_calls(session, step_mode)
            await demo_section_4_comparison(session, step_mode)
            await demo_section_5_connection_to_our_project(session, step_mode)

    _header("Demo Complete")
    print("""
  GitHub MCP connection closed (subprocess terminated).

  You now understand:
    • How MCP stdio transport works  (subprocess + stdin/stdout pipes)
    • How tool discovery works        (session.list_tools() → JSON schemas)
    • How tool calls work             (session.call_tool(name, args) → content blocks)
    • How results are returned        (result.content[0].text → parse JSON)

  This EXACT pattern powers our real estate negotiation agents.

  Next:
    python m2_mcp/pricing_server.py --demo    ← our custom MCP server
    python m2_mcp/inventory_server.py --demo  ← information asymmetry demo
    python m2_mcp/sse_demo_client.py --both   ← SSE transport demo
""")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="GitHub MCP Demo Client — understanding MCP via GitHub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  export GITHUB_TOKEN=ghp_your_token_here
  python github_demo_client.py            # step-by-step (default)
  python github_demo_client.py --fast     # no pauses, run at full speed
""",
    )
    parser.add_argument(
        "--fast", action="store_true",
        help="Disable step mode — run all sections without pausing",
    )
    _args = parser.parse_args()
    asyncio.run(main(step_mode=not _args.fast))
