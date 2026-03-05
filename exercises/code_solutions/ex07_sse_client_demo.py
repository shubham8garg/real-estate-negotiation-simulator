import asyncio
import json
import socket

from mcp import ClientSession
from mcp.client.sse import sse_client


def _is_sse_server_reachable(host: str = "localhost", port: int = 8001) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


async def call_pricing_mcp_sse(tool_name: str, arguments: dict) -> dict:
    async with sse_client("http://localhost:8001/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            if result.content and len(result.content) > 0:
                return json.loads(result.content[0].text)
    return {}


async def main() -> None:
    if not _is_sse_server_reachable():
        print("SSE pricing server is not running on http://localhost:8001/sse")
        print("Start it first: python m2_mcp/pricing_server.py --sse --port 8001")
        raise SystemExit(1)

    print("Calling pricing MCP server over SSE...")
    try:
        data = await call_pricing_mcp_sse(
            "get_market_price",
            {"address": "742 Evergreen Terrace, Austin, TX 78701", "property_type": "single_family"},
        )
        print(data.get("market_statistics", {}))
    except Exception as error:
        print(f"SSE call failed: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
