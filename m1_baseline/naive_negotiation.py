"""
BASELINE SYSTEM: Naive Real Estate Negotiation
===============================================

This file intentionally demonstrates how most first-attempt agent systems fail.
It represents the "obvious" implementation that seems reasonable but breaks down
in practice.

╔══════════════════════════════════════════════════════════════════════════════╗
║  THIS CODE IS INTENTIONALLY BROKEN -- IT IS THE PROBLEM WE'RE SOLVING        ║
╚══════════════════════════════════════════════════════════════════════════════╝

INTENTIONAL PROBLEMS IN THIS CODE:
1. Raw string communication between agents
2. No schema validation -- messages can be anything
3. No state machine -- just a while True loop
4. No turn limits -- can loop forever
5. Ambiguous parsing -- regex on free-form text
6. No termination guarantees
7. Silent failures when parsing goes wrong
8. No grounded context -- prices are hardcoded (should come from MCP)
9. No observability -- can't see what happened
10. No evaluation -- can't measure quality

This is the MOTIVATING FAILURE that drives the entire architecture:
  MCP    -> solves problem #8  (grounded context)
  A2A    -> solves problems #1, #2, #5 (structured messages, schema validation)
  FSM    -> solves problems #3, #4, #6 (state machine + termination guarantee)
  LangGraph -> solves problems #3, #9 (workflow graph + observability)

HOW TO RUN:
  python m1_baseline/naive_negotiation.py

WHAT TO WATCH FOR:
  • Demo 1: "Works by luck" -- notice how fragile the success is
  • Demo 2: Impossible agreement -- loop runs until emergency exit
  • Failure mode demos -- see all 4 ways the regex parser breaks

COMPARE WITH:
    python m3_langgraph_multiagents/main_langgraph_multiagent.py   ← The fixed version (MCP + typed messages + LangGraph)
"""

import argparse
import inspect
import re
import sys
import textwrap
import time
from typing import Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# STEP-MODE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _wait(step_mode: bool, prompt: str = "  [ENTER to continue →] ") -> None:
    """Pause for ENTER if step mode is on."""
    if step_mode:
        input(prompt)
    else:
        time.sleep(0.3)


def _header(title: str, width: int = 65) -> None:
    """Print a prominent section header."""
    print("\n" + "╔" + "═" * (width - 2) + "╗")
    pad = (width - 2 - len(title)) // 2
    print("║" + " " * pad + title + " " * (width - 2 - pad - len(title)) + "║")
    print("╚" + "═" * (width - 2) + "╝")


def _section(title: str, width: int = 65) -> None:
    """Print a sub-section separator."""
    print("\n" + "─" * width)
    print("  " + title)
    print("─" * width)


def _print_source(method, notes: list = None) -> None:
    """
    Pretty-print the source of a method with line numbers.
    Strips common leading whitespace (dedent) so indentation is clean.
    Optionally prints teaching notes below the code.
    """
    raw = inspect.getsource(method)
    src = textwrap.dedent(raw)
    lines = src.rstrip().split("\n")

    # ── code block ────────────────────────────────────────────────────────────
    print()
    print("  " + "┄" * 63)
    for i, line in enumerate(lines, 1):
        # Clip very long lines so they don't wrap badly on small terminals
        display = line if len(line) <= 90 else line[:87] + "…"
        print(f"  {i:3d} │ {display}")
    print("  " + "┄" * 63)

    # ── teaching notes ────────────────────────────────────────────────────────
    if notes:
        print()
        for note in notes:
            print(f"  ▶  {note}")


# ─────────────────────────────────────────────────────────────────────────────
# AGENT CODE WALKTHROUGH  (shown before demos)
# ─────────────────────────────────────────────────────────────────────────────

def _show_agent_code(step_mode: bool) -> None:
    """
    Pretty-print NaiveBuyer and NaiveSeller source method by method,
    pausing between each one so the instructor can explain.
    """
    _header("The Agents: How Naive Agents Are Written")
    print("""
  Before running the negotiation, let's look at how these agents are coded.
  These are INTENTIONALLY naive — they are the problem we are solving.

  We will read each method together:
    NaiveBuyer   __init__ → make_initial_offer → respond_to_counter
    NaiveSeller  __init__ → respond_to_offer
""")
    _wait(step_mode, "  [ENTER: NaiveBuyer.__init__ →] ")

    # ── NaiveBuyer.__init__ ───────────────────────────────────────────────────
    _section("NaiveBuyer — __init__  (how the buyer agent is created)")
    print("""
  The buyer is created with a name and a max_price (their budget ceiling).
  State is stored as plain Python attributes — no schema, no validation.
""")
    _print_source(NaiveBuyer.__init__, notes=[
        "max_price  — the buyer's absolute ceiling. Hardcoded at call site ($460K).",
        "current_offer — a single float. No history, no audit trail. Easy to corrupt.",
        "No message schema. Any string can be passed in — nothing is enforced.",
    ])
    _wait(step_mode, "  [ENTER: make_initial_offer() →] ")

    # ── NaiveBuyer.make_initial_offer ─────────────────────────────────────────
    _section("NaiveBuyer — make_initial_offer()  (the opening bid)")
    print("""
  The first offer: a hardcoded percentage of the budget, returned as a raw string.
  No market data. No MCP. Just math.
""")
    _print_source(NaiveBuyer.make_initial_offer, notes=[
        "Offer = max_price × 0.923 — an arbitrary multiplier, not from market data.",
        "Returns a raw STRING. The seller must PARSE this string to find the price.",
        "Parsing strings is fragile — the seller's regex might grab the wrong number.",
        "In Module 2 (MCP), the buyer calls get_market_price() to justify every offer.",
    ])
    _wait(step_mode, "  [ENTER: respond_to_counter() — the fragile parser →] ")

    # ── NaiveBuyer.respond_to_counter ────────────────────────────────────────
    _section("NaiveBuyer — respond_to_counter()  (the fragile parser)")
    print("""
  The buyer's response logic: regex to extract a price, then decide to accept or counter.
  This is where most of the fragility lives.
""")
    _print_source(NaiveBuyer.respond_to_counter, notes=[
        "re.search(r'\\$?([\\d,]+...)') — grabs the FIRST number found in the string.",
        "  'I paid $350K renovating, counter is $477K'  →  extracts $350K (WRONG!).",
        "if not price_match: return old offer string  →  SILENT FAILURE, no error raised.",
        "Returns a string with 'ACCEPT' embedded — seller checks: 'ACCEPT' in msg.upper().",
        "No message ID, no round number, no timestamp — zero observability.",
    ])
    _wait(step_mode, "  [ENTER: NaiveSeller.__init__ →] ")

    # ── NaiveSeller.__init__ ──────────────────────────────────────────────────
    _section("NaiveSeller — __init__  (how the seller agent is created)")
    print("""
  The seller is created with a name, floor price, and asking price.
  All three are HARDCODED at the call site — no live data, no MCP.
""")
    _print_source(NaiveSeller.__init__, notes=[
        "min_price — the seller's floor. Baked into the constructor call.",
        "  In real life only the seller's agent knows this. Here it's visible in source.",
        "  In Module 2 (MCP), this comes from get_minimum_acceptable_price() — private.",
        "asking_price — where the seller starts. Also hardcoded, not from market data.",
    ])
    _wait(step_mode, "  [ENTER: respond_to_offer() — the seller's decision logic →] ")

    # ── NaiveSeller.respond_to_offer ─────────────────────────────────────────
    _section("NaiveSeller — respond_to_offer()  (parsing + decision, all mixed together)")
    print("""
  The seller's entire logic in one method: parse the buyer's string, decide what to do.
  Business logic and parsing are entangled — hard to change either one.
""")
    _print_source(NaiveSeller.respond_to_offer, notes=[
        "if 'ACCEPT' in buyer_message.upper() — keyword search, not a typed field.",
        "Same fragile regex — extracts first number. Could grab renovation cost instead.",
        "if not price_match: return a vague string  →  SILENT FAILURE again.",
        "self.current_price * 0.95 — mechanical 5% reduction, no market reasoning.",
        "  In Module 2 (MCP), seller calls get_inventory_level() to justify each counter.",
        "'final' in buyer_message.lower() — detects buyer ceiling via keyword scanning.",
        "  'This is NOT my final offer, but $430K' → would incorrectly match 'final'.",
    ])
    _wait(step_mode, "  [ENTER: now watch these agents run in Demo 1 →] ")


# ─────────────────────────────────────────────────────────────────────────────
# PROPERTY CONTEXT (hardcoded -- PROBLEM #8)
# In the real version these come from MCP servers (pricing_server.py,
# inventory_server.py). Hardcoded values go stale and can't be validated.
# ─────────────────────────────────────────────────────────────────────────────

PROPERTY_ADDRESS = "742 Evergreen Terrace, Austin, TX 78701"
LISTING_PRICE = 485_000          # Should come from MCP get_market_price()
BUYER_MAX_PRICE = 460_000        # Budget -- should inform via A2A, not hardcoded
SELLER_MIN_PRICE = 445_000       # Floor -- should come from MCP get_minimum_acceptable_price()
SELLER_ASKING_PRICE = 477_000    # Initial counter -- should be informed by MCP data


# ─────────────────────────────────────────────────────────────────────────────
# NAIVE BUYER AGENT
# ─────────────────────────────────────────────────────────────────────────────

class NaiveBuyer:
    """
    A naive buyer agent that communicates via raw strings.

    PROBLEMS:
    - No structured message format (strings, not Pydantic models)
    - State is implicit (just self.current_offer) and easy to corrupt
    - Strategy is entangled with parsing logic -- hard to change either
    - No access to market data -- relies on hardcoded BUYER_MAX_PRICE
    - Can't express conditions, closing timeline, or concessions
    """

    def __init__(self, name: str, max_price: float):
        self.name = name
        self.max_price = max_price
        self.current_offer = None

    def make_initial_offer(self) -> str:
        """Generate initial offer as raw string."""
        # Start at about 87% of max price (roughly $425K for our $460K budget)
        self.current_offer = self.max_price * 0.923
        return (
            f"I'd like to purchase {PROPERTY_ADDRESS}. "
            f"My offer is ${self.current_offer:,.2f}. "
            f"This is contingent on home inspection."
        )

    def respond_to_counter(self, seller_message: str) -> str:
        """
        Parse seller's response and decide next action.

        PROBLEM #5: This regex parsing is fragile and will fail on:
        - Different number formats ($477,000 vs $477K vs 477000)
        - Typos ("$477,00" vs "$477,000")
        - Unexpected message structures
        - Multiple prices in one message ("I paid $350K, now asking $477K")
        - Non-English responses

        PROBLEM #7: Silent failure -- if we can't parse, we just repeat our offer
        and the negotiation continues without either side knowing something broke.
        """
        # Try to extract price from seller's message
        # ╔══════════════════════════════════════════════════════════════════╗
        # ║ PROBLEM: This regex matches the FIRST number it finds.           ║
        # ║ In "I paid $350K renovating, so my counter is $477,000" it       ║
        # ║ extracts $350,000 -- the WRONG price!                              ║
        # ╚══════════════════════════════════════════════════════════════════╝
        price_match = re.search(r'\$?([\d,]+(?:\.\d{2})?)', seller_message)

        if not price_match:
            # ╔═══════════════════════════════════════════════════════════╗
            # ║  SILENT FAILURE (Problem #7): We don't know what the      ║
            # ║  seller said, but we'll just keep going. This is a bug.   ║
            # ╚═══════════════════════════════════════════════════════════╝
            return f"I'm confused by your response. My offer remains ${self.current_offer:,.2f}."

        seller_price = float(price_match.group(1).replace(',', ''))

        # Accept if seller came down to or below our max
        if seller_price <= self.max_price:
            return f"ACCEPT: I'll purchase the property at ${seller_price:,.2f}."

        # Increase our offer by 10% but never exceed max
        self.current_offer = min(self.current_offer * 1.10, self.max_price)

        if self.current_offer >= self.max_price:
            return (
                f"My final offer is ${self.current_offer:,.2f}. "
                "That is my absolute maximum. Take it or leave it."
            )

        return (
            f"I can increase my offer to ${self.current_offer:,.2f}. "
            "I hope we can find a middle ground."
        )


# ─────────────────────────────────────────────────────────────────────────────
# NAIVE SELLER AGENT
# ─────────────────────────────────────────────────────────────────────────────

class NaiveSeller:
    """
    A naive seller agent that communicates via raw strings.

    PROBLEMS:
    - No access to grounded context (pricing rules, inventory, CRM)
    - min_price and asking_price are hardcoded (should come from MCP)
    - No validation of buyer's messages -- can be manipulated by malformed input
    - Can't express conditions, timeline requirements, or contingency rejections
    - Mixed parsing and business logic makes both harder to change
    """

    def __init__(self, name: str, min_price: float, asking_price: float):
        self.name = name
        self.min_price = min_price      # PROBLEM #8: Should come from MCP get_minimum_acceptable_price()
        self.asking_price = asking_price
        self.current_price = asking_price

    def respond_to_offer(self, buyer_message: str) -> str:
        """
        Parse buyer's offer and respond.

        PROBLEM #5: Extremely brittle parsing.
        PROBLEM #8: No market data -- just mechanically reducing the asking price.
        """
        # Check for acceptance keywords (PROBLEM: keyword matching is fragile)
        if "ACCEPT" in buyer_message.upper():
            price_match = re.search(r'\$?([\d,]+(?:\.\d{2})?)', buyer_message)
            if price_match:
                accepted_price = float(price_match.group(1).replace(',', ''))
                return f"DEAL! We have a sale at ${accepted_price:,.2f}. Congratulations!"

        # Try to extract offered price
        price_match = re.search(r'\$?([\d,]+(?:\.\d{2})?)', buyer_message)

        if not price_match:
            # ╔═══════════════════════════════════════════════════════════╗
            # ║  SILENT FAILURE (Problem #7): Can't parse, but we         ║
            # ║  continue anyway -- the negotiation proceeds on bad data.  ║
            # ╚═══════════════════════════════════════════════════════════╝
            return f"I didn't catch your offer. The property is listed at ${self.current_price:,.2f}."

        offered_price = float(price_match.group(1).replace(',', ''))

        # Accept if at or above our minimum
        if offered_price >= self.min_price:
            return f"DEAL! I accept ${offered_price:,.2f}. We have a sale!"

        # Reduce by 5% each round (mechanical -- no market reasoning)
        # PROBLEM #8: In reality, the seller should query inventory levels,
        # days-on-market, and comparable sales via MCP to justify each counter
        self.current_price = max(self.current_price * 0.95, self.min_price)

        if "final" in buyer_message.lower() or "maximum" in buyer_message.lower():
            # PROBLEM: We're relying on detecting "final" in the buyer's message
            # This is easily gamed: "This is NOT my final offer, but it's $430K"
            if offered_price >= self.min_price * 0.95:
                return f"DEAL! Given your commitment, I'll accept ${offered_price:,.2f}."
            return (
                f"I cannot go that low. My minimum is ${self.min_price:,.2f}. "
                "I'm afraid we can't make this work. REJECT."
            )

        return (
            f"Thank you for your offer. I can counter at ${self.current_price:,.2f}. "
            "The property has had significant recent renovations."
        )


# ─────────────────────────────────────────────────────────────────────────────
# THE MAIN LOOP (The Biggest Problem)
# ─────────────────────────────────────────────────────────────────────────────

def run_naive_negotiation(
    buyer: NaiveBuyer,
    seller: NaiveSeller,
    verbose: bool = True,
    step_mode: bool = False,
    fast_scroll: bool = False,
) -> Tuple[bool, Optional[float], int]:
    """
    Run a naive negotiation between buyer and seller.

    THE CORE PROBLEMS IN THIS FUNCTION:

    Problem #3 -- No state machine:
        The code has no explicit states. When is it "buyer's turn"? When is it
        "seller's turn"? We track this with a boolean flag (is_buyer_turn)
        which is error-prone and doesn't scale to 3+ agents.

    Problem #4 -- No turn limits (the while True):
        If buyer max_price ($460K) < seller min_price ($500K), there is NO
        possible agreement. The loop will run forever. The "emergency exit"
        at 100 turns is a band-aid, not a fix.

    Problem #6 -- No termination guarantee:
        We check for "DEAL" and "REJECT" in the string output. What if the
        LLM says "We have a DEAL-breaker here"? It matches "DEAL"! What if
        it spells "REJECT" as "Rejected"? We miss it!

    Problem #9 -- Zero observability:
        There's no structured log. You can't easily reconstruct what happened,
        calculate convergence rate, or audit why a deal failed.

    Returns:
        (success: bool, final_price: Optional[float], turns: int)
    """
    # LEARNER NOTE:
    # This function is the runtime engine for one negotiation session.
    # Inputs: buyer + seller agent objects.
    # Output: (did_we_get_a_deal, final_price_if_any, number_of_turns)
    if verbose:
        print("\n" + "=" * 65)
        print("NAIVE REAL ESTATE NEGOTIATION (Intentionally Broken)")
        print(f"Property: {PROPERTY_ADDRESS}")
        print(f"Listing: ${LISTING_PRICE:,.0f}  |  Buyer max: ${buyer.max_price:,.0f}  |  Seller min: ${seller.min_price:,.0f}")
        print("=" * 65)

    # turn counts total messages exchanged AFTER buyer's opening message.
    turn = 0
    current_message = buyer.make_initial_offer()
    # Control flag for turn-taking. This is a fragile stand-in for a real FSM state.
    is_buyer_turn = False  # Buyer just went, so seller goes next

    if verbose:
        print(f"\n[Turn {turn}] {buyer.name}:\n  {current_message}")
        if fast_scroll:
            time.sleep(0.12)
        else:
            _wait(step_mode, "  [ENTER for seller response →] ")

    # ╔════════════════════════════════════════════════════════════════════╗
    # ║  DANGER: while True with no guaranteed exit condition!             ║
    # ║  If buyer max < seller min, agents can NEVER agree.               ║
    # ║  This will run FOREVER without the emergency exit at 100 turns.   ║
    # ║                                                                    ║
    # ║  FIX: Use NegotiationFSM from m1_baseline/state_machine.py           ║
    # ║  BETTER FIX: Use LangGraph from m3_langgraph_multiagents/langgraph_flow.py   ║
    # ╚════════════════════════════════════════════════════════════════════╝
    while True:
        turn += 1

        # ── Emergency exit (band-aid, not a fix) ──────────────────────────────
        if turn > 100:
            if verbose:
                print(f"\n[EMERGENCY] Exceeded 100 turns -- forcing exit without agreement")
            return False, None, turn

        # ── Take a turn ────────────────────────────────────────────────────────
        # The same string variable (current_message) keeps getting overwritten.
        # There is no typed event history, so debugging later is difficult.
        if is_buyer_turn:
            current_message = buyer.respond_to_counter(current_message)
            speaker = buyer.name
        else:
            current_message = seller.respond_to_offer(current_message)
            speaker = seller.name

        if verbose:
            label = "Buyer" if is_buyer_turn else "Seller"  # who just spoke
            next_label = "seller" if is_buyer_turn else "buyer"
            print(f"\n[Turn {turn}] {speaker}:\n  {current_message}")

        # ── Check termination via STRING MATCHING (Problem #6) ─────────────────
        # FRAGILE: "DEAL-breaker", "DEAL with the renovation costs", etc. all match
        # LEARNER NOTE:
        # This is "keyword protocol" — outcome control based on text tokens.
        # In robust systems, this should be explicit state transitions.
        if "DEAL" in current_message.upper():
            price_match = re.search(r'\$?([\d,]+(?:\.\d{2})?)', current_message)
            final_price = float(price_match.group(1).replace(',', '')) if price_match else None
            if verbose:
                status = f"${final_price:,.2f}" if final_price else "unknown price"
                print(f"\n  [DEAL] Agreement reached at {status} after {turn} turns")
            return True, final_price, turn

        if "REJECT" in current_message.upper():
            if verbose:
                print(f"\n  [FAILED] Negotiation failed after {turn} turns — seller rejected")
            return False, None, turn

        # Flip turn for the next loop iteration.
        is_buyer_turn = not is_buyer_turn

        if verbose:
            next_speaker = "buyer" if is_buyer_turn else "seller"
            if fast_scroll:
                time.sleep(0.12)
            else:
                _wait(step_mode, f"  [ENTER for {next_speaker} response →] ")


# ─────────────────────────────────────────────────────────────────────────────
# FAILURE MODE DEMONSTRATIONS
# ─────────────────────────────────────────────────────────────────────────────

def demonstrate_failure_modes(step_mode: bool = False) -> None:
    """
    Demonstrate each failure mode explicitly so learners can see the problems.
    These are NOT edge cases -- they happen regularly in production.
    """
    _header("DEMO 3: Failure Mode Demonstrations")
    print("""
  Each failure below is a real bug that happens in production agent systems.
  These are the motivating problems that drive the entire architecture:
    MCP       → solves hardcoded prices (#4)
    FSM       → solves infinite loop (#2) and implicit state (#5)
    LangGraph → solves state corruption + adds observability
    Pydantic  → solves silent failures (#3) and ambiguous parsing (#1)
""")
    _wait(step_mode, "  [ENTER to see Failure Mode 1 of 5 →] ")

    # ── Failure Mode 1: Ambiguous price extraction ─────────────────────────────
    _section("Failure Mode 1 of 5: Ambiguous Message Parsing (regex grabs wrong number)")
    message = "I spent $350,000 on renovations, but my counter-offer is $477,000"
    price_match = re.search(r'\$?([\d,]+(?:\.\d{2})?)', message)
    print(f"""
  Seller message: "{message}"

  Code:    re.search(r'\\$?([\\d,]+)', seller_message)
  Result:  ${price_match.group(1) if price_match else 'None'}

  PROBLEM: Regex grabs the FIRST number it finds — $350,000 (renovation cost).
           The actual offer ($477,000) is silently ignored.
           Agent now thinks seller countered at $350K. Logic breaks silently.

  FIX:     Structured message with explicit 'price' field (negotiation_types.py).
           No parsing needed — price is always at message.price.
""")
    _wait(step_mode, "  [ENTER for Failure Mode 2 →] ")

    # ── Failure Mode 2: Infinite loop risk ─────────────────────────────────────
    _section("Failure Mode 2 of 5: No ZOPA — Infinite Loop Risk")
    print(f"""
  Buyer max price:  $430,000
  Seller min price: $450,000
  Gap:              $20,000  ← these agents can NEVER agree

  The while True loop has no way to detect this.
  It runs until the emergency exit at 100 turns.
  In production: 100 OpenAI API calls wasted. No output. No explanation.

  The 'while True' with emergency exit at 100 turns is NOT a fix —
  it's a band-aid. A real system needs a mathematical guarantee.

  FIX:     NegotiationFSM.process_turn() auto-transitions to FAILED at max_turns=5.
           The loop condition is 'while not fsm.is_terminal()' — always terminates.
""")
    _wait(step_mode, "  [ENTER for Failure Mode 3 →] ")

    # ── Failure Mode 3: Silent parsing failure ─────────────────────────────────
    _section("Failure Mode 3 of 5: Silent Parsing Failure (None propagates silently)")
    message = "I'd like to offer four hundred and thirty thousand dollars"
    price_match = re.search(r'\$?([\d,]+(?:\.\d{2})?)', message)
    print(f"""
  Buyer message:  "{message}"

  Code:    re.search(r'\\$?([\\d,]+)', buyer_message)
  Result:  {price_match}  ← None! No $ symbol, no digits found.

  In NaiveSeller.respond_to_offer():
    if not price_match:
        return "I didn't catch your offer..."   ← negotiation CONTINUES on bad data

  PROBLEM: The buyer's real offer ($430,000) is lost. The negotiation proceeds
           as if nothing happened. No error. No log. No way to know later.

  FIX:     Pydantic's NegotiationMessage enforces 'price: float' at schema level.
           A missing price raises ValidationError immediately — loud, not silent.
""")
    _wait(step_mode, "  [ENTER for Failure Mode 4 →] ")

    # ── Failure Mode 4: Hardcoded prices instead of MCP ───────────────────────
    _section("Failure Mode 4 of 5: Hardcoded Prices (no live market data)")
    print(f"""
  In naive_negotiation.py:
    SELLER_MIN_PRICE = {SELLER_MIN_PRICE:,}     ← baked into source code
    LISTING_PRICE    = {LISTING_PRICE:,}     ← baked into source code
    BUYER_MAX_PRICE  = {BUYER_MAX_PRICE:,}     ← baked into source code

  PROBLEMS:
    1. Values go stale — market changes, code doesn't.
    2. Seller's floor price is VISIBLE in source code — no privacy.
    3. Agents cannot justify offers with real market data.
    4. Changing prices requires a code edit and redeploy.

  In production these should come from live MCP tool calls:
    get_minimum_acceptable_price('742 Evergreen Terrace...')
    get_market_price('742 Evergreen Terrace...')
    get_inventory_level('78701')

  FIX:     Module 2 — MCP servers (pricing_server.py, inventory_server.py).
""")
    _wait(step_mode, "  [ENTER for Failure Mode 5 →] ")

    # ── Failure Mode 5: State corruption ──────────────────────────────────────
    _section("Failure Mode 5 of 5: Implicit State (is_buyer_turn boolean)")
    print(f"""
  In run_naive_negotiation():
    is_buyer_turn = False   ← a single boolean tracking whose turn it is

  PROBLEMS:
    1. Two-agent state fits in a bool. Three agents (add a mediator)?
       The bool breaks. You need a different data structure.
    2. Call make_initial_offer() twice by accident?
       self.current_offer gets overwritten — corrupted state, no error.
    3. No history. If you debug after the fact, you cannot reconstruct
       what happened or why a deal failed.

  FIX (next steps):
    FSM (this module):  NegotiationState enum — only 4 named states, validated transitions.
    LangGraph (M3):     NegotiationState TypedDict — full typed history, all agents' data.
""")
    _wait(step_mode, "  [ENTER to see the full failure → fix map →] ")

    _section("Summary: Every Failure Maps to a Fix")
    print("""
  #   Failure                   Fix
  ─── ────────────────────────  ──────────────────────────────────────────
   1  Ambiguous regex parsing   Typed NegotiationMessage (negotiation_types.py)
   2  Infinite loop / no ZOPA   NegotiationFSM.process_turn() + max_turns
   3  Silent parse failure      Pydantic validation — raises, never silently skips
   4  Hardcoded prices          MCP servers (pricing_server.py, inventory_server.py)
   5  Implicit / fragile state  LangGraph NegotiationState TypedDict
""")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN -- Run all demos
# ─────────────────────────────────────────────────────────────────────────────

def _run_demo1(step_mode: bool) -> None:
    """Demo 1: Successful negotiation (ZOPA exists — deal is possible)."""
    _header("DEMO 1: When It 'Works' (By Luck — Fragile!)")
    print(f"""
  Buyer max:  ${BUYER_MAX_PRICE:,}  |  Seller min: ${SELLER_MIN_PRICE:,}
  Gap:        ZOPA EXISTS — a deal is mathematically possible.

  Watch the negotiation run. Ask yourself:
    - What if the buyer's message had "$350K renovation" in it?
    - What if the seller never says "DEAL" exactly?
    - What stops this running for 1,000 turns?
""")
    _wait(step_mode, "  [ENTER to start negotiation →] ")

    buyer = NaiveBuyer("Alice (Buyer)", max_price=BUYER_MAX_PRICE)
    seller = NaiveSeller("Bob (Seller)", min_price=SELLER_MIN_PRICE, asking_price=SELLER_ASKING_PRICE)
    success, price, turns = run_naive_negotiation(buyer, seller, verbose=True, step_mode=step_mode)

    print("\n" + "─" * 65)
    if success and price:
        savings = LISTING_PRICE - price
        print(f"  Result:      DEAL at ${price:,.2f} in {turns} turns")
        print(f"  Buyer saved: ${savings:,.0f} off the ${LISTING_PRICE:,} listing price")
    else:
        print(f"  Result:      No deal after {turns} turns")
    print("""
  Notice: It worked — but only because the numbers happened to overlap.
  The process was fragile, parsing-dependent, and has NO termination proof.
""")


def _run_demo2(step_mode: bool) -> None:
    """Demo 2: No ZOPA — shows the while True problem and keyword-matching fragility."""
    _header("DEMO 2: Impossible Agreement (No ZOPA)")
    print(f"""
  Buyer max:  $420,000  |  Seller min: $450,000
  Gap:        -$30,000  ← these agents can NEVER agree on a price

  Watch the turns scroll by. Notice:
    • The negotiation DOES terminate — but only via "REJECT" keyword in a string
    • If the LLM said "I must decline" instead of "REJECT", the check would MISS it
    • That is the real danger: termination depends on exact string content

  Running fast scroll so you can see every turn happen...
""")
    _wait(step_mode, "  [ENTER to watch turns run →] ")

    buyer2 = NaiveBuyer("Alice (Buyer)", max_price=420_000)
    seller2 = NaiveSeller("Bob (Seller)", min_price=450_000, asking_price=477_000)
    success2, price2, turns2 = run_naive_negotiation(
        buyer2, seller2, verbose=True, step_mode=False, fast_scroll=True
    )

    print(f"\n  Result:    success={success2}, final_price={price2}, turns={turns2}")
    print(f"""
  Terminated in {turns2} turns via string matching: "REJECT" in message.upper()

  Now ask: what if the LLM wrote "I'm afraid I must decline your offer" ?
    → "REJECT" not in "I'M AFRAID I MUST DECLINE YOUR OFFER"  → False
    → The loop does NOT break
    → Negotiation continues indefinitely

  That is the infinite loop problem. Without the emergency exit at turn 100,
  this runs FOREVER — consuming API calls, money, and time, silently.

  The emergency exit (turn > 100) is a band-aid, not a solution.

  FIX: NegotiationFSM.process_turn() — terminates at max_turns=5 regardless
       of what the agents say. Math, not string matching.
       → Run 'python m1_baseline/state_machine.py' to see the fix.
""")


def main() -> None:
    """
    Interactive demo of the naive negotiation system.

    MODES:
      --step        Pause for ENTER between each negotiation turn (default for teaching)
      --fast        Run all demos without pausing
      --demo N      Run only demo N: 1=success, 2=impossible loop, 3=failure modes
    """
    parser = argparse.ArgumentParser(
        description="Naive Real Estate Negotiation — teaching demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python naive_negotiation.py              # step-by-step with code walkthrough (default)
  python naive_negotiation.py --fast       # no pauses, run everything quickly
  python naive_negotiation.py --skip-code  # skip code walkthrough, go straight to demos
  python naive_negotiation.py --demo 1     # only Demo 1 (successful negotiation)
  python naive_negotiation.py --demo 2     # only Demo 2 (infinite loop problem)
  python naive_negotiation.py --demo 3     # only Demo 3 (failure modes)
""",
    )
    parser.add_argument(
        "--fast", action="store_true",
        help="Disable step mode — run all demos without pausing",
    )
    parser.add_argument(
        "--demo", type=int, choices=[1, 2, 3], default=0,
        metavar="N",
        help="Run only one demo: 1=success, 2=infinite-loop, 3=failure-modes",
    )
    parser.add_argument(
        "--skip-code", action="store_true",
        help="Skip the agent code walkthrough and go straight to demos",
    )
    args = parser.parse_args()

    step_mode = not args.fast  # step mode on by default; --fast disables it

    # ── Intro ──────────────────────────────────────────────────────────────────
    if args.demo == 0:
        _header("Naive Real Estate Negotiation — What Goes Wrong")
        print(f"""
  Property:   {PROPERTY_ADDRESS}
  Listed at:  ${LISTING_PRICE:,}

  This file shows how MOST first-attempt agent systems fail.
  The code is INTENTIONALLY broken — it IS the problem we are solving.

  We will run 3 demos:
    Demo 1 — Successful negotiation  (appears to work, but notice how fragile)
    Demo 2 — Impossible agreement    (reveals the infinite loop problem)
    Demo 3 — Failure mode breakdown  (5 specific bugs, each with a fix)

  Controls: ENTER advances one step.  Ctrl-C to exit at any time.
""")
        _wait(step_mode, "  [ENTER to read the agent code →] ")

    # ── Agent code walkthrough (before demos, unless skipped) ──────────────────
    if args.demo == 0 and not args.skip_code:
        _show_agent_code(step_mode)

    # ── Run demos ──────────────────────────────────────────────────────────────
    if args.demo in (0, 1):
        _run_demo1(step_mode)
        if args.demo == 0:
            _wait(step_mode, "  [ENTER for Demo 2: the infinite loop problem →] ")

    if args.demo in (0, 2):
        _run_demo2(step_mode)
        if args.demo == 0:
            _wait(step_mode, "  [ENTER for Demo 3: failure modes breakdown →] ")

    if args.demo in (0, 3):
        demonstrate_failure_modes(step_mode)

    # ── Closing summary (only when running all demos) ─────────────────────────
    if args.demo == 0:
        _header("What Comes Next")
        print("""
  Every failure you just saw maps to a specific architectural fix:

  Module 1 (this file) → state_machine.py
    NegotiationFSM with TRANSITIONS dict — termination is provable

  Module 2 → m2_mcp/pricing_server.py
    MCP tools replace all hardcoded prices with live market data

  Module 3 → m3_langgraph_multiagents/langgraph_flow.py
    LangGraph replaces while True with a stateful, observable graph

  Module 4 → m4_adk_multiagents/buyer_adk.py + a2a_protocol_seller_server.py
    Google ADK + A2A: agents as independently deployable networked services

  Next step:
    python m1_baseline/state_machine.py    ← the FSM fix for this module
""")


if __name__ == "__main__":
    main()
