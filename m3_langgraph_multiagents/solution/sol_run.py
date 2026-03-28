"""
MODULE 3 — SOLUTION RUNNER: Negotiation with Deadlock Detection + Convergence
==============================================================================
Runs the LangGraph negotiation using the solution file (sol_langgraph_flow.py)
which has BOTH M3 exercise solutions applied:
  - Exercise 1: Stale-price deadlock detection in route_after_seller()
  - Exercise 2: Convergence auto-accept at midpoint in seller_node()

This runner is based on main_langgraph_multiagent.py but imports from
sol_langgraph_flow.py instead of langgraph_flow.py.

HOW TO RUN:
  python m3_langgraph_multiagents/solution/sol_run.py
  python m3_langgraph_multiagents/solution/sol_run.py --fast
  python m3_langgraph_multiagents/solution/sol_run.py --rounds 3
  python m3_langgraph_multiagents/solution/sol_run.py --rounds 5 --fast

REQUIRES:
  OPENAI_API_KEY environment variable (or .env file at repo root)
"""

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── Display Helpers ──────────────────────────────────────────────────────────

def _header(title: str, width: int = 65) -> None:
    print("\n" + "╔" + "═" * (width - 2) + "╗")
    pad = (width - 2 - len(title)) // 2
    print("║" + " " * pad + title + " " * (width - 2 - pad - len(title)) + "║")
    print("╚" + "═" * (width - 2) + "╝")


# ─── Environment helpers ──────────────────────────────────────────────────────

def _load_env_file_if_present(env_path: Path) -> None:
    if not env_path.exists():
        return
    try:
        with env_path.open("r", encoding="utf-8") as env_file:
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
        pass


_load_env_file_if_present(REPO_ROOT / ".env")


def check_environment() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY is not set.")
        print("   export OPENAI_API_KEY=<your_key>")
        print()
        print("Get your key at: https://platform.openai.com/api-keys")
        sys.exit(1)


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="M3 Solution Runner — Deadlock Detection + Convergence",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python m3_langgraph_multiagents/solution/sol_run.py
  python m3_langgraph_multiagents/solution/sol_run.py --fast
  python m3_langgraph_multiagents/solution/sol_run.py --rounds 3
  python m3_langgraph_multiagents/solution/sol_run.py --rounds 5 --fast
""",
    )
    parser.add_argument("--fast",          action="store_true", help="Disable step-mode pauses")
    parser.add_argument("--rounds",        type=int,   default=5,    help="Max negotiation rounds (default: 5)")
    parser.add_argument("--session",       type=str,   default=None, help="Session ID (default: auto-generated)")
    parser.add_argument("--buyer-budget",  type=float, default=460_000, help="Buyer max budget (default: 460000)")
    parser.add_argument("--seller-minimum",type=float, default=445_000, help="Seller floor price (default: 445000)")
    args = parser.parse_args()

    step_mode = not args.fast
    session_id = args.session or f"sol_{uuid.uuid4().hex[:8]}"

    check_environment()

    _header("Module 3 — Solution: Deadlock Detection + Convergence")
    print(f"""
  Stack:      OpenAI GPT-4o + MCP + LangGraph
  Solutions:  Ex1 (deadlock detection) + Ex2 (convergence auto-accept)
  Flow file:  m3_langgraph_multiagents/solution/sol_langgraph_flow.py

  Solutions applied to this run:
    Ex1: route_after_seller() checks last 4 prices — if all same → deadlocked
    Ex2: seller_node() checks gap ≤ 2% before LLM call → auto-accept at midpoint

  Property:      742 Evergreen Terrace, Austin, TX 78701
  Listed at:     $485,000
  Buyer budget:  ${args.buyer_budget:,.0f}
  Seller floor:  ${args.seller_minimum:,.0f}  (mortgage payoff — seller-confidential)
  Max rounds:    {args.rounds}
  Session:       {session_id}
""")

    if step_mode:
        input("  [ENTER: start negotiation →] ")

    from m3_langgraph_multiagents.solution.sol_langgraph_flow import run_negotiation

    try:
        final_state = await run_negotiation(
            session_id=session_id,
            property_address="742 Evergreen Terrace, Austin, TX 78701",
            listing_price=485_000.0,
            buyer_budget=args.buyer_budget,
            seller_minimum=args.seller_minimum,
            max_rounds=args.rounds,
            step_mode=step_mode,
        )

        status = final_state.get("status", "unknown")
        agreed_price = final_state.get("agreed_price")

        print("\n  What the solutions did in this run:")
        if status == "agreed" and agreed_price:
            history = final_state.get("history", [])
            convergence_rounds = [h for h in history if h.get("convergence")]
            if convergence_rounds:
                print("  ✓ Ex2 TRIGGERED: Seller auto-accepted at midpoint")
                print(f"    Convergence round: {convergence_rounds[0].get('round')}")
                print(f"    Midpoint accepted: ${agreed_price:,.0f}")
            else:
                print("  ✓ Ex2 NOT triggered: Deal reached via normal LLM negotiation")
        elif status == "deadlocked":
            print("  ✓ Ex1 TRIGGERED: Stale-price deadlock detected")
            print("    Without Ex1: would have looped forever repeating same prices")
        else:
            print(f"  Status: {status} — solutions may not have triggered this run")

        print()
        print("  Compare to original (without solutions):")
        print("    python m3_langgraph_multiagents/main_langgraph_multiagent.py")
        print()
        print("  Run again with different params:")
        print("    python m3_langgraph_multiagents/solution/sol_run.py --rounds 3 --fast")
        print()

        return final_state

    except KeyboardInterrupt:
        print("\n\n  Negotiation interrupted.")
        sys.exit(0)

    except Exception as e:
        print(f"\n  ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
