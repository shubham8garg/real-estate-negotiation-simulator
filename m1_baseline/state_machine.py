"""
Finite State Machine for Negotiation
======================================
Layer 7 of the 10-layer architecture -- solves the termination problem
that breaks naive_negotiation.py.

WHAT THIS SOLVES:
  naive_negotiation.py uses a while True loop with only an emergency
  exit at 100 turns. This FSM provides a MATHEMATICAL GUARANTEE of
  termination:

  1. States AGREED and FAILED have NO outgoing transitions (terminal)
  2. Turn count is bounded by max_turns
  3. Every transition either:
     a) Moves to a terminal state (no further transitions possible), OR
     b) Increments the turn count (bounded -- can't loop forever)
  Therefore, Termination is GUARANTEED.

HOW TO RUN (demo):
  python m1_baseline/state_machine.py

HOW THIS CONNECTS TO THE REST OF THE WORKSHOP:
  ┌─────────────────────────────────────────────────────────────────┐
  │  naive_negotiation.py                                           │
  │    while True: ...  <-- no guarantee                             │
  │         ↓                                                       │
  │  state_machine.py (this file)                                   │
  │    NegotiationFSM   <-- termination guaranteed at code level      │
  │         ↓                                                       │
  │  m3_langgraph_multiagents/langgraph_flow.py                                │
  │    StateGraph       <-- termination guaranteed at workflow level  │
  │    (LangGraph IS a state machine -- but for entire workflows)    │
  └─────────────────────────────────────────────────────────────────┘

  The progression shows WHY LangGraph exists: it provides the same
  FSM guarantees as NegotiationFSM, but for complex multi-step
  workflows with conditional routing and parallel agents.

CREDIT:
  Core FSM design adapted from jeev1992/Agent-Negotiation-System (04_fsm/),
  updated for the real estate workshop context (max_turns=5).
"""

import argparse
import inspect
import os
import re
import sys
import textwrap
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

# ── Optional import of agents from naive_negotiation.py ──────────────────────
# Used in scenario demos to show real buyer/seller dialogue alongside FSM state.
# Falls back gracefully if import is unavailable.
try:
    _here = os.path.dirname(os.path.abspath(__file__))
    _root = os.path.dirname(_here)
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from m1_baseline.naive_negotiation import (   # noqa: E402
        NaiveBuyer, NaiveSeller,
        BUYER_MAX_PRICE, SELLER_MIN_PRICE, SELLER_ASKING_PRICE, PROPERTY_ADDRESS,
    )
    _AGENTS_AVAILABLE = True
except Exception:
    _AGENTS_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# STEP-MODE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _wait(step_mode: bool, prompt: str = "  [ENTER to continue →] ") -> None:
    """Pause for ENTER if in step mode, else add a short delay."""
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
    print("\n" + "━" * width)
    print("  " + title)
    print("━" * width)


def _print_source(method, notes: list = None) -> None:
    """Pretty-print a method's source with line numbers and optional teaching notes."""
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


def _show_fsm(fsm: "NegotiationFSM", label: str = "") -> None:
    """Print a compact FSM status line."""
    terminal = "YES — no further transitions possible" if fsm.is_terminal() else "No"
    agreed = f"  agreed_price:   ${fsm.context.agreed_price:,.0f}" if fsm.context.agreed_price else ""
    reason = f"  failure_reason: {fsm.context.failure_reason.name}" if fsm.context.failure_reason else ""
    prefix = f"  [{label}]" if label else " "
    print(f"""
{prefix}
  state:       {fsm.state.name}
  turn_count:  {fsm.context.turn_count} / {fsm.context.max_turns}{agreed}{reason}
  is_terminal: {terminal}""")


# ─────────────────────────────────────────────────────────────────────────────
# STATE DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

class NegotiationState(Enum):
    """
    The finite set of states a negotiation can be in.

    KEY INSIGHT: There are exactly 4 states, and only 2 are terminal.
    This small, explicit set is what makes termination provable.
    Compare to naive_negotiation.py where state was implicit and unbounded.
    """
    IDLE        = auto()    # Not yet started -- waiting for first offer
    NEGOTIATING = auto()    # Active -- offers being exchanged
    AGREED      = auto()    # Terminal: deal reached ✓
    FAILED      = auto()    # Terminal: no deal ✗


class FailureReason(Enum):
    """
    Why a negotiation failed.

    Storing the reason enables:
    - Better user-facing messages
    - Analytics (which failure type is most common?)
    - Strategy adjustment in next session
    """
    MAX_TURNS_EXCEEDED  = auto()    # Ran out of rounds without agreement
    REJECTED_BY_BUYER   = auto()    # Buyer walked away
    REJECTED_BY_SELLER  = auto()    # Seller rejected outright
    POLICY_VIOLATION    = auto()    # Message violates negotiation rules
    INVALID_TRANSITION  = auto()    # Tried an impossible state transition


# ─────────────────────────────────────────────────────────────────────────────
# FSM CONTEXT
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FSMContext:
    """
    Context tracked alongside the FSM state.

    This is similar to LangGraph's NegotiationState TypedDict -- it holds
    the data that persists across state transitions. The difference is that
    LangGraph's state is much richer (full message history, both agents'
    offers, etc.) while FSMContext just tracks what the FSM needs.
    """
    turn_count:     int                      = 0
    max_turns:      int                      = 5      # Match our workshop config (5 rounds)
    last_offer:     Optional[float]          = None   # Most recent price on the table
    agreed_price:   Optional[float]          = None   # Set when AGREED
    failure_reason: Optional[FailureReason]  = None   # Set when FAILED


# ─────────────────────────────────────────────────────────────────────────────
# THE FSM
# ─────────────────────────────────────────────────────────────────────────────

class NegotiationFSM:
    """
    Finite State Machine for negotiation lifecycle.

    TERMINATION GUARANTEE (informal proof):
    ─────────────────────────────────────────
    Define measure M = (is_terminal, turn_count).
    Ordering: terminal < non-terminal; lower turn_count < higher.

    Each call to process_turn():
      Case A: is_terminal becomes True  -> M strictly decreases (non-terminal -> terminal)
      Case B: turn_count increments     -> M strictly decreases (same category, lower count)

    Since M is bounded below (is_terminal=True is the minimum) and strictly
    decreasing, the FSM MUST reach a terminal state in finite steps. QED.

    CONTRAST WITH naive_negotiation.py:
      while True:
          if "DEAL" in message: break  <-- depends on string content; can be fooled
          if turn > 100: break         <-- emergency exit, not a guarantee

    WITH FSM:
      while not fsm.is_terminal():
          if not fsm.process_turn(): break  <-- guaranteed to terminate

    RELATIONSHIP TO LANGGRAPH:
      LangGraph provides the same guarantee at workflow level:
      - Terminal nodes (END) have no outgoing edges
      - Cycle detection prevents infinite loops
      - Max steps can be set in graph.compile()
    """

    # ── Transition table ───────────────────────────────────────────────────────
    # This is the heart of the FSM. Read it as:
    #   "From state X, you may transition to any state in the set Y"
    #
    # TERMINAL STATES (AGREED, FAILED) have EMPTY sets -- no outgoing transitions.
    # This is what guarantees they can never be exited once entered.
    TRANSITIONS: dict[NegotiationState, set[NegotiationState]] = {
        NegotiationState.IDLE:        {NegotiationState.NEGOTIATING, NegotiationState.FAILED},
        NegotiationState.NEGOTIATING: {NegotiationState.NEGOTIATING, NegotiationState.AGREED, NegotiationState.FAILED},
        NegotiationState.AGREED:      set(),    # <-- TERMINAL: no outgoing transitions
        NegotiationState.FAILED:      set(),    # <-- TERMINAL: no outgoing transitions
    }

    def __init__(self, max_turns: int = 5):
        # LEARNER NOTE:
        # `state` is the control state (where we are in lifecycle),
        # `context` is the data state (facts we carry across transitions).
        self.state = NegotiationState.IDLE
        self.context = FSMContext(max_turns=max_turns)

    # ── Inspection ────────────────────────────────────────────────────────────

    def get_state(self) -> NegotiationState:
        """Return current state."""
        return self.state

    @property
    def is_active(self) -> bool:
        """True if negotiation is in progress (NEGOTIATING state)."""
        return self.state == NegotiationState.NEGOTIATING

    def is_terminal(self) -> bool:
        """
        True if in AGREED or FAILED -- no further transitions possible.
        Use this as the loop exit condition instead of checking strings.
        """
        return self.state in {NegotiationState.AGREED, NegotiationState.FAILED}

    def can_transition(self, to_state: NegotiationState) -> bool:
        """Check if a transition is valid without performing it."""
        return to_state in self.TRANSITIONS[self.state]

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """
        Begin the negotiation. Returns False if already started.
        IDLE -> NEGOTIATING
        """
        # Only valid once: IDLE -> NEGOTIATING.
        # Any second call is rejected (returns False) to keep lifecycle clean.
        if self.state != NegotiationState.IDLE:
            return False
        self.state = NegotiationState.NEGOTIATING
        return True

    def process_turn(self) -> bool:
        """
        Record that a turn has occurred. Returns False if max turns exceeded.

        THIS IS THE KEY TO TERMINATION GUARANTEE:
        Every active turn increments turn_count.
        When turn_count >= max_turns, we transition to FAILED automatically.
        Since turn_count is an integer bounded by max_turns, it can never
        increment forever -- termination is guaranteed.

        Returns:
            True  -- turn recorded, negotiation continues
            False -- max turns exceeded, moved to FAILED
        """
        if not self.is_active:
            return False

        # One call = one negotiation step.
        self.context.turn_count += 1

        # When the cap is hit, we force a terminal failure state.
        # This removes the possibility of endless loops.
        if self.context.turn_count >= self.context.max_turns:
            # Auto-transition to FAILED -- no more turns allowed
            self.state = NegotiationState.FAILED
            self.context.failure_reason = FailureReason.MAX_TURNS_EXCEEDED
            return False

        return True

    def record_turn(self) -> None:
        """
        Alternative to process_turn() for use with external loop controllers
        (like LangGraph) that manage their own round counting.
        Does not enforce max_turns -- call process_turn() if you want that.
        """
        if self.is_active:
            self.context.turn_count += 1

    # ── Terminal transitions ───────────────────────────────────────────────────

    def accept(self, price: float) -> bool:
        """
        Both parties agree on a price.
        NEGOTIATING -> AGREED

        Returns False if not currently active.
        """
        # Guard clause: acceptance is only legal during NEGOTIATING.
        if not self.is_active:
            return False
        self.state = NegotiationState.AGREED
        self.context.agreed_price = price
        return True

    def reject(self, by_buyer: bool = True) -> bool:
        """
        One party rejects -- ends negotiation without a deal.
        NEGOTIATING -> FAILED

        Returns False if not currently active.
        """
        # Guard clause: rejection is only legal during NEGOTIATING.
        if not self.is_active:
            return False
        self.state = NegotiationState.FAILED
        self.context.failure_reason = (
            FailureReason.REJECTED_BY_BUYER if by_buyer
            else FailureReason.REJECTED_BY_SELLER
        )
        return True

    def transition_to_failed(self, reason: FailureReason = FailureReason.POLICY_VIOLATION) -> bool:
        """Transition to FAILED for any reason (policy violation, error, etc.)."""
        if not self.is_active:
            return False
        self.state = NegotiationState.FAILED
        self.context.failure_reason = reason
        return True

    # ── Invariant checking ────────────────────────────────────────────────────

    def check_invariants(self) -> bool:
        """
        Assert that all FSM invariants hold.

        These should NEVER be violated. If they are, there's a bug in the
        FSM logic itself. Call this in tests and at key checkpoints.

        Raises AssertionError if any invariant is violated.
        """
        # Turn count must be non-negative
        assert self.context.turn_count >= 0, "Turn count cannot be negative"

        # Turn count cannot exceed max_turns (FSM should have stopped it)
        assert self.context.turn_count <= self.context.max_turns, (
            f"Turn count {self.context.turn_count} exceeds max {self.context.max_turns}"
        )

        # Terminal states must have required context data
        if self.state == NegotiationState.AGREED:
            assert self.context.agreed_price is not None, (
                "AGREED state requires agreed_price to be set"
            )

        if self.state == NegotiationState.FAILED:
            assert self.context.failure_reason is not None, (
                "FAILED state requires failure_reason to be set"
            )

        # Terminal states must have empty transition sets (the core guarantee)
        if self.is_terminal():
            assert len(self.TRANSITIONS[self.state]) == 0, (
                f"Terminal state {self.state} should have no outgoing transitions"
            )

        return True

    def __repr__(self) -> str:
        return (
            f"NegotiationFSM(state={self.state.name}, "
            f"turn={self.context.turn_count}/{self.context.max_turns})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# AGENT COMPARISON — Do the agents change when we add an FSM?
# ─────────────────────────────────────────────────────────────────────────────

def _show_agent_fsm_comparison(step_mode: bool) -> None:
    """
    Show that NaiveBuyer and NaiveSeller are UNCHANGED in the FSM version.
    Only the orchestration loop changes. Print both loops side-by-side.
    """
    _header("Do the Agents Change When We Add an FSM?")
    print("""
  Short answer: NO.

  NaiveBuyer and NaiveSeller are imported UNCHANGED from naive_negotiation.py.
  The FSM wraps around the agents — it does not replace them.

  What changes is the ORCHESTRATION LOOP:
    naive_negotiation.py  →  while True: ... if "DEAL" in message: break
    state_machine.py      →  while not fsm.is_terminal(): ... fsm.process_turn()

  Let's look at both loops now.
""")
    _wait(step_mode, "  [ENTER: see the import statement (agents unchanged) →] ")

    # ── Show the import ────────────────────────────────────────────────────────
    _section("The import: same agents, zero code changes")
    print("""
  At the top of state_machine.py:

    from m1_baseline.naive_negotiation import (
        NaiveBuyer, NaiveSeller,
        BUYER_MAX_PRICE, SELLER_MIN_PRICE, SELLER_ASKING_PRICE, PROPERTY_ADDRESS,
    )

  These are the EXACT same classes from naive_negotiation.py.
  NaiveBuyer.__init__, make_initial_offer(), respond_to_counter() — all unchanged.
  NaiveSeller.__init__, respond_to_offer() — all unchanged.

  The FSM is an orchestration layer ON TOP of the agents.
  It controls WHEN agents speak and WHAT to do with the result.
  It does not change HOW the agents think or what they say.
""")
    _wait(step_mode, "  [ENTER: see the naive orchestration loop →] ")

    # ── Naive loop ─────────────────────────────────────────────────────────────
    _section("NAIVE loop (naive_negotiation.py) — the problem")
    print("""
  The orchestration loop in run_naive_negotiation():
""")
    if _AGENTS_AVAILABLE:
        from m1_baseline.naive_negotiation import run_naive_negotiation
        _print_source(run_naive_negotiation, notes=[
            "while True  →  NO termination guarantee. Could run forever.",
            "if 'DEAL' in message.upper()  →  string matching. 'DEALBREAKER' would match.",
            "if turn > 100  →  emergency exit, not a proof. 100 wasted API calls.",
            "is_buyer_turn = not is_buyer_turn  →  state is a boolean. Fragile.",
        ])
    else:
        print("""
  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
    1 │ def run_naive_negotiation(buyer, seller, ...):
    2 │     turn = 0
    3 │     is_buyer_turn = False
    4 │     while True:                           # ← NO guarantee
    5 │         if is_buyer_turn:
    6 │             message = buyer.respond_to_counter(message)
    7 │         else:
    8 │             message = seller.respond_to_offer(message)
    9 │         if "DEAL" in message.upper():      # ← string match, easily fooled
   10 │             return True, price, turn
   11 │         if "REJECT" in message.upper():    # ← string match
   12 │             return False, None, turn
   13 │         if turn > 100:                     # ← band-aid, not a proof
   14 │             return False, None, turn
   15 │         is_buyer_turn = not is_buyer_turn  # ← boolean state, fragile
  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
""")
        print("  ▶  while True  →  NO termination guarantee. Could run forever.")
        print("  ▶  'DEAL' in message  →  string matching. 'DEALBREAKER' would match.")
        print("  ▶  turn > 100  →  emergency exit, not a proof. 100 wasted API calls.")
        print("  ▶  is_buyer_turn boolean  →  state is implicit. Falls apart with 3 agents.")

    _wait(step_mode, "  [ENTER: see the FSM orchestration loop →] ")

    # ── FSM loop ───────────────────────────────────────────────────────────────
    _section("FSM loop (state_machine.py) — the fix")
    print("""
  The orchestration loop in Scenario 1 (and all 3 scenarios):

  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
    1 │ fsm = NegotiationFSM(max_turns=5)
    2 │ fsm.start()                               # IDLE → NEGOTIATING
    3 │
    4 │ while not fsm.is_terminal():              # ← ALWAYS terminates
    5 │     if is_buyer_turn:
    6 │         message = buyer.respond_to_counter(message)
    7 │     else:
    8 │         message = seller.respond_to_offer(message)
    9 │
   10 │     if "DEAL" in message.upper():
   11 │         fsm.accept(price=price)            # NEGOTIATING → AGREED (terminal)
   12 │     elif "REJECT" in message.upper():
   13 │         fsm.reject(by_buyer=is_buyer_turn) # NEGOTIATING → FAILED (terminal)
   14 │     else:
   15 │         fsm.process_turn()                 # increments turn, FAILS at max_turns
   16 │
   17 │     is_buyer_turn = not is_buyer_turn
  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄

  ▶  Lines 1–2: agents unchanged — same NaiveBuyer, NaiveSeller call
  ▶  Line 4:   while not fsm.is_terminal() — terminates because AGREED/FAILED
                 have EMPTY transition sets (proven at class definition time)
  ▶  Lines 11, 13: fsm.accept() / fsm.reject() — explicit named events,
                 not keyword guessing
  ▶  Line 15:  fsm.process_turn() — auto-transitions to FAILED at max_turns=5,
                 no 100-turn emergency exit needed
""")
    _wait(step_mode, "  [ENTER: see the change summary table →] ")

    # ── Change summary ─────────────────────────────────────────────────────────
    _section("What changed vs what stayed the same")
    print("""
  ╔══════════════════════════╦══════════════════════════╦══════════════════════════╗
  ║ Concern                  ║ Naive (while True)       ║ FSM (while not terminal) ║
  ╠══════════════════════════╬══════════════════════════╬══════════════════════════╣
  ║ NaiveBuyer code          ║ defined here             ║ UNCHANGED (imported)     ║
  ║ NaiveSeller code         ║ defined here             ║ UNCHANGED (imported)     ║
  ║ Loop condition           ║ while True               ║ while not is_terminal()  ║
  ║ Termination mechanism    ║ string match + turn>100  ║ TRANSITIONS[state]=set() ║
  ║ Max rounds               ║ 100 (arbitrary)          ║ 5 (enforced by FSM)      ║
  ║ State representation     ║ bool (is_buyer_turn)     ║ NegotiationState enum    ║
  ║ Why it stopped           ║ unknown (no record)      ║ failure_reason enum      ║
  ║ Can you replay it?       ║ No                       ║ Yes (FSMContext)          ║
  ╚══════════════════════════╩══════════════════════════╩══════════════════════════╝

  KEY INSIGHT:
    The agents are decoupled from the orchestration.
    You can swap the FSM for LangGraph (Module 3) and the agents still don't change.
    You can swap NaiveBuyer for an ADK-based buyer (Module 4) and the FSM still works.
    Separation of concerns: agent logic vs lifecycle control.
""")
    _wait(step_mode, "  [ENTER: now build the FSM step by step →] ")


# ─────────────────────────────────────────────────────────────────────────────
# PART 1 — FSM CONSTRUCTION (teaching walkthrough)
# ─────────────────────────────────────────────────────────────────────────────

def _teach_fsm_construction(step_mode: bool) -> None:
    """Walk through HOW an FSM is built, step by step."""

    _header("PART 1: Building the Finite State Machine")
    print("""
  Goal: replace the fragile 'while True' loop in naive_negotiation.py
  with a system that PROVABLY terminates.

  We will build the FSM in 4 steps, then run 3 scenarios through it.
""")
    _wait(step_mode, "  [ENTER for Step 1: Define the legal states →] ")

    # Step 1 ───────────────────────────────────────────────────────────────────
    _section("Step 1 of 4: Define the legal states (NegotiationState enum)")
    print("""
  An FSM has a FINITE, named set of states.
  Naming them explicitly prevents typos and makes the code self-documenting.

  class NegotiationState(Enum):
      IDLE        = auto()    # before negotiation starts  (starting state)
      NEGOTIATING = auto()    # active — offers being exchanged
      AGREED      = auto()    # deal reached               ← TERMINAL
      FAILED      = auto()    # no deal, walk-away         ← TERMINAL

  KEY INSIGHT:
    Only 2 states are terminal (AGREED, FAILED).
    The negotiation MUST end in one of them — no other exit.
    Compare to naive_negotiation.py where 'state' was just a bool (is_buyer_turn).
""")
    _wait(step_mode, "  [ENTER for Step 2: Define the transition map →] ")

    # Step 2 ───────────────────────────────────────────────────────────────────
    _section("Step 2 of 4: Define the transition map (TRANSITIONS dict)")
    print("""
  TRANSITIONS answers: "from state X, which states can we go to?"

  TRANSITIONS = {
      IDLE:        { NEGOTIATING }                    ← can only start
      NEGOTIATING: { NEGOTIATING, AGREED, FAILED }    ← continue or end
      AGREED:      set()                              ← EMPTY = terminal
      FAILED:      set()                              ← EMPTY = terminal
  }

  The EMPTY SETS are the mathematical guarantee:
    TRANSITIONS[AGREED] = set()  →  once in AGREED, there are NO valid next states
    TRANSITIONS[FAILED] = set()  →  once in FAILED, there are NO valid next states

  Proof of termination (informal):
    NEGOTIATING → FAILED auto-triggers when turn_count >= max_turns
    AGREED and FAILED have no outgoing edges (empty sets)
    Therefore: execution MUST reach AGREED or FAILED within max_turns steps. QED.
""")
    _wait(step_mode, "  [ENTER for Step 3: Compare FSM vs while True →] ")

    # Step 3 ───────────────────────────────────────────────────────────────────
    _section("Step 3 of 4: FSM vs naive while True (why this matters)")
    print("""
  NAIVE (naive_negotiation.py):
  ─────────────────────────────
    while True:
        ...
        if "DEAL" in message:  break   ← fragile: "DEAL-breaker" would match
        if turn > 100:         break   ← band-aid: not a proof

    Problems:
      • String matching is gamed easily
      • 100-turn limit is arbitrary — still wastes 95 API calls when gap is obvious
      • No audit trail: you cannot see WHY it stopped

  FSM (state_machine.py):
  ───────────────────────
    fsm = NegotiationFSM(max_turns=5)
    fsm.start()
    while not fsm.is_terminal():        ← this loop ALWAYS terminates
        ...
        if accepted:  fsm.accept(price)
        elif rejected: fsm.reject()
        else:         fsm.process_turn()  ← auto-transitions at max_turns

    Benefits:
      • Termination is a mathematical consequence of the TRANSITIONS dict
      • Max 5 rounds, not 100
      • FSMContext records why it stopped (failure_reason, agreed_price)
""")
    _wait(step_mode, "  [ENTER for Step 4: Create the FSM instance →] ")

    # Step 4 ───────────────────────────────────────────────────────────────────
    _section("Step 4 of 4: Create the FSM instance")
    print("""
  fsm = NegotiationFSM(max_turns=5)
""")
    fsm_demo = NegotiationFSM(max_turns=5)
    _show_fsm(fsm_demo, "just created")
    print("""
  The FSM starts in IDLE.
  It holds an FSMContext alongside the control state:
    • turn_count    — increments on each process_turn()
    • max_turns     — the hard cap (5 for this workshop)
    • agreed_price  — set when AGREED
    • failure_reason — set when FAILED

  Now let's run 3 scenarios through this same FSM structure.
""")
    _wait(step_mode, "  [ENTER to start Scenario 1 →] ")


# ─────────────────────────────────────────────────────────────────────────────
# PART 2 — SCENARIOS
# ─────────────────────────────────────────────────────────────────────────────

def _fsm_turn(
    fsm: NegotiationFSM,
    buyer,
    seller,
    current_message: str,
    is_buyer_turn: bool,
    turn: int,
    step_mode: bool,
):
    """
    Run one negotiation turn: agent speaks, FSM records, prints both layers.
    Returns (new_message, new_is_buyer_turn, terminal_reached).
    """
    if is_buyer_turn:
        current_message = buyer.respond_to_counter(current_message)
        speaker = buyer.name
    else:
        current_message = seller.respond_to_offer(current_message)
        speaker = seller.name

    # ── Agent layer: what was said ─────────────────────────────────────────────
    print(f"\n  ┌─ [{speaker}] Turn {turn} " + "─" * (45 - len(speaker)))
    print(f"  │  {current_message[:120]}{'...' if len(current_message) > 120 else ''}")
    print(f"  └" + "─" * 55)

    # ── FSM layer: detect event and advance state ──────────────────────────────
    if "DEAL" in current_message.upper():
        m = re.search(r'\$?([\d,]+(?:\.\d{2})?)', current_message)
        price = float(m.group(1).replace(',', '')) if m else 449_000.0
        print(f"\n  FSM EVENT: 'DEAL' in message → fsm.accept(price=${price:,.0f})")
        fsm.accept(price=price)
        _show_fsm(fsm, "TERMINAL — AGREED")
        return current_message, not is_buyer_turn, True
    elif "REJECT" in current_message.upper():
        print(f"\n  FSM EVENT: 'REJECT' in message → fsm.reject()")
        fsm.reject(by_buyer=is_buyer_turn)
        _show_fsm(fsm, "TERMINAL — FAILED (rejected)")
        return current_message, not is_buyer_turn, True
    else:
        ok = fsm.process_turn()
        _show_fsm(fsm, f"turn {turn} recorded — continues={ok}")
        if not ok:
            return current_message, not is_buyer_turn, True

    return current_message, not is_buyer_turn, fsm.is_terminal()


def _scenario1(step_mode: bool) -> None:
    """Scenario 1: Deal reached — AGREED terminal state."""
    _header("SCENARIO 1 of 3: Deal Reached (AGREED)")
    print("""
  Setup: Buyer max $460K, Seller min $445K — a ZOPA exists, deal is possible.

  Watch TWO layers simultaneously:
    AGENT LAYER  — what Alice (buyer) and Bob (seller) say to each other
    FSM LAYER    — how NegotiationFSM tracks state and enforces termination
""")
    _wait(step_mode, "  [ENTER: create FSM + agents →] ")

    fsm = NegotiationFSM(max_turns=5)
    if _AGENTS_AVAILABLE:
        buyer = NaiveBuyer("Alice (Buyer)", max_price=BUYER_MAX_PRICE)
        seller = NaiveSeller("Bob (Seller)", min_price=SELLER_MIN_PRICE, asking_price=SELLER_ASKING_PRICE)
        prop = PROPERTY_ADDRESS
    else:
        print("  [NOTE] naive_negotiation.py not importable — showing FSM-only demo")
        buyer = seller = prop = None

    print(f"""
  NegotiationFSM(max_turns=5)     created
  NaiveBuyer("Alice", max=${BUYER_MAX_PRICE if _AGENTS_AVAILABLE else 460000:,})  created
  NaiveSeller("Bob",  min=${SELLER_MIN_PRICE if _AGENTS_AVAILABLE else 445000:,}) created
""")
    _wait(step_mode, "  [ENTER: fsm.start() — IDLE → NEGOTIATING →] ")

    print("  fsm.start()   →   IDLE → NEGOTIATING")
    fsm.start()
    _show_fsm(fsm, "negotiation started")

    if not _AGENTS_AVAILABLE:
        # Fallback: FSM-only demo without agent messages
        for i in range(1, 4):
            _wait(step_mode, f"  [ENTER: Round {i} → fsm.process_turn() →] ")
            print(f"\n  fsm.process_turn()   [Round {i}]")
            fsm.process_turn()
            _show_fsm(fsm, f"round {i}")
        _wait(step_mode, "  [ENTER: fsm.accept(449_000) →] ")
        fsm.accept(price=449_000)
        _show_fsm(fsm, "TERMINAL — AGREED")
    else:
        # Real negotiation: show agent messages + FSM state side by side
        _wait(step_mode, "  [ENTER: Alice makes opening offer →] ")
        current_message = buyer.make_initial_offer()
        print(f"\n  ┌─ [Alice (Buyer)] Turn 0 (opening offer) " + "─" * 18)
        print(f"  │  {current_message[:120]}{'...' if len(current_message) > 120 else ''}")
        print(f"  └" + "─" * 55)
        print("\n  FSM: opening offer received — no state change yet (waiting for first full round)")
        _show_fsm(fsm, "after opening offer")

        is_buyer_turn = False  # seller goes next
        turn = 0
        terminal = False
        while not terminal:
            turn += 1
            next_name = buyer.name if is_buyer_turn else seller.name
            _wait(step_mode, f"  [ENTER: {next_name} responds →] ")
            current_message, is_buyer_turn, terminal = _fsm_turn(
                fsm, buyer, seller, current_message, is_buyer_turn, turn, step_mode
            )

    print()
    fsm.check_invariants()
    print("  fsm.check_invariants()  →   PASS — all invariants hold")
    print("""
  AGREED is a terminal state: TRANSITIONS[AGREED] = set()  (empty)
  Let's prove it cannot be escaped:
""")
    _wait(step_mode, "  [ENTER: try fsm.accept(440_000) after deal →] ")
    result = fsm.accept(price=440_000)
    print(f"  fsm.accept(440_000)  →  returns: {result}  ← False, state unchanged")
    print(f"  fsm.state            →  {fsm.state.name}  ← sticky, cannot be overridden")
    _wait(step_mode, "  [ENTER for Scenario 2 →] ")


def _scenario2(step_mode: bool) -> None:
    """Scenario 2: No ZOPA — seller eventually rejects — FAILED (REJECTED_BY_SELLER)."""
    _header("SCENARIO 2 of 3: No ZOPA — Seller Rejects (FAILED)")
    print("""
  Setup: Buyer max $420K, Seller min $450K — gap of $30K, NO deal possible.

  The agents will negotiate but can never agree.
  Watch: buyer hits their ceiling and says "absolute maximum".
         Seller detects this and fires "REJECT".
         FSM catches the REJECT keyword and transitions to FAILED.

  This is the same "impossible" case from naive_negotiation.py Demo 2.
  Now we can see EXACTLY how and WHY termination happens.
""")
    _wait(step_mode, "  [ENTER: create FSM + agents →] ")

    fsm2 = NegotiationFSM(max_turns=5)
    if _AGENTS_AVAILABLE:
        buyer2 = NaiveBuyer("Alice (Buyer)", max_price=420_000)
        seller2 = NaiveSeller("Bob (Seller)", min_price=450_000, asking_price=477_000)
    else:
        buyer2 = seller2 = None

    print("""
  NegotiationFSM(max_turns=5)          created
  NaiveBuyer("Alice", max=$420,000)    created  ← BELOW seller min
  NaiveSeller("Bob",  min=$450,000)    created  ← ABOVE buyer max
  Gap: $30,000 — no ZOPA
""")
    _wait(step_mode, "  [ENTER: fsm2.start() →] ")

    print("  fsm2.start()   →   IDLE → NEGOTIATING")
    fsm2.start()
    _show_fsm(fsm2, "negotiation started")

    if not _AGENTS_AVAILABLE:
        for i in range(1, 3):
            _wait(step_mode, f"  [ENTER: Round {i} →] ")
            fsm2.process_turn()
            _show_fsm(fsm2, f"round {i}")
        _wait(step_mode, "  [ENTER: fsm2.reject(by_buyer=False) →] ")
        fsm2.reject(by_buyer=False)
        _show_fsm(fsm2, "TERMINAL — FAILED (seller rejected)")
    else:
        _wait(step_mode, "  [ENTER: Alice makes opening offer →] ")
        current_message = buyer2.make_initial_offer()
        print(f"\n  ┌─ [Alice (Buyer)] Turn 0 (opening offer) " + "─" * 18)
        print(f"  │  {current_message[:120]}{'...' if len(current_message) > 120 else ''}")
        print(f"  └" + "─" * 55)
        _show_fsm(fsm2, "after opening offer")

        is_buyer_turn = False
        turn = 0
        terminal = False
        while not terminal:
            turn += 1
            next_name = buyer2.name if is_buyer_turn else seller2.name
            _wait(step_mode, f"  [ENTER: {next_name} responds →] ")
            current_message, is_buyer_turn, terminal = _fsm_turn(
                fsm2, buyer2, seller2, current_message, is_buyer_turn, turn, step_mode
            )

    print(f"""
  failure_reason: {fsm2.context.failure_reason.name if fsm2.context.failure_reason else 'N/A'}

  Key insight:
    Termination here relied on "REJECT" appearing in the seller's message.
    In naive_negotiation.py, that same check was: if "REJECT" in message.upper()
    The FSM gives this a proper name (REJECTED_BY_SELLER) and records it.
    If the LLM ever says "I decline" instead of "REJECT", both systems miss it —
    but the FSM at least has max_turns as a fallback guarantee.
""")
    _wait(step_mode, "  [ENTER: prove terminal state is sticky →] ")
    result = fsm2.accept(price=440_000)
    print(f"  fsm2.accept(440_000)  →  {result}  ← False — FAILED state has no outgoing transitions")
    print(f"  fsm2.state            →  {fsm2.state.name}")
    fsm2.check_invariants()
    print("  fsm2.check_invariants()  →   PASS")
    _wait(step_mode, "  [ENTER for Scenario 3 →] ")


def _scenario3(step_mode: bool) -> None:
    """Scenario 3: FSM forces deadlock at max_turns even when deal was possible."""
    _header("SCENARIO 3 of 3: Max Turns Exceeded (FAILED — MAX_TURNS_EXCEEDED)")
    print("""
  Setup: Buyer max $460K, Seller min $445K — a deal IS possible (same as Scenario 1).
         BUT: max_turns = 2 (very tight limit).

  The FSM cuts off the negotiation at round 2 even though the agents
  COULD have reached a deal in more rounds.

  This shows that the FSM is the authority on termination — not the agents.
  process_turn() auto-transitions to FAILED when turn_count >= max_turns.
""")
    _wait(step_mode, "  [ENTER: create FSM with max_turns=2 →] ")

    fsm3 = NegotiationFSM(max_turns=2)   # tight limit for demo
    if _AGENTS_AVAILABLE:
        buyer3 = NaiveBuyer("Alice (Buyer)", max_price=BUYER_MAX_PRICE)
        seller3 = NaiveSeller("Bob (Seller)", min_price=SELLER_MIN_PRICE, asking_price=SELLER_ASKING_PRICE)
    else:
        buyer3 = seller3 = None

    print("""
  NegotiationFSM(max_turns=2)    ← hard stop after 2 rounds
  NaiveBuyer("Alice", max=$460,000)
  NaiveSeller("Bob",  min=$445,000)
""")
    _wait(step_mode, "  [ENTER: fsm3.start() →] ")

    print("  fsm3.start()   →   IDLE → NEGOTIATING")
    fsm3.start()
    _show_fsm(fsm3, "started")

    if not _AGENTS_AVAILABLE:
        for i in range(1, 10):
            result = fsm3.process_turn()
            print(f"\n  fsm3.process_turn()   [Round {i}]")
            _show_fsm(fsm3, f"round {i} — continues={result}")
            if fsm3.is_terminal():
                print(f"\n  FSM auto-terminated at round {i}. No further rounds allowed.")
                break
            _wait(step_mode, f"  [ENTER: Round {i + 1} →] ")
    else:
        _wait(step_mode, "  [ENTER: Alice makes opening offer →] ")
        current_message = buyer3.make_initial_offer()
        print(f"\n  ┌─ [Alice (Buyer)] Turn 0 (opening offer) " + "─" * 18)
        print(f"  │  {current_message[:120]}{'...' if len(current_message) > 120 else ''}")
        print(f"  └" + "─" * 55)
        _show_fsm(fsm3, "after opening offer")

        is_buyer_turn = False
        turn = 0
        terminal = False
        while not terminal:
            turn += 1
            next_name = buyer3.name if is_buyer_turn else seller3.name
            _wait(step_mode, f"  [ENTER: {next_name} responds →] ")
            current_message, is_buyer_turn, terminal = _fsm_turn(
                fsm3, buyer3, seller3, current_message, is_buyer_turn, turn, step_mode
            )
            # If FSM hit max_turns on process_turn(), show it explicitly
            if fsm3.is_terminal() and fsm3.context.failure_reason == FailureReason.MAX_TURNS_EXCEEDED:
                print(f"""
  FSM ENFORCED TERMINATION:
    turn_count ({fsm3.context.turn_count}) >= max_turns ({fsm3.context.max_turns})
    process_turn() returned False and auto-transitioned to FAILED.
    The agents could have kept going — but the FSM said NO.
""")
                break

    _wait(step_mode, "  [ENTER to verify invariants →] ")
    fsm3.check_invariants()
    print("  fsm3.check_invariants()  →   PASS")

    print(f"""
  Final state:     {fsm3.state.name}
  Turns used:      {fsm3.context.turn_count} / {fsm3.context.max_turns}
  failure_reason:  {fsm3.context.failure_reason.name if fsm3.context.failure_reason else 'N/A'}

  The FSM is the authority. Regardless of what the agents say or do,
  the FSM enforces the max_turns limit. This is a mathematical guarantee —
  not a best-effort convention.

  Compare:
    naive_negotiation.py  →  100-turn emergency exit (arbitrary, not a proof)
    NegotiationFSM        →  max_turns enforced by process_turn() (provable)
    LangGraph (Module 3)  →  same guarantee at workflow scale via END node
""")


def _print_key_takeaways(step_mode: bool) -> None:
    """Final summary slide."""
    _header("Key Takeaways")
    _wait(step_mode, "  [ENTER to see takeaways →] ")
    print("""
  1. TERMINAL STATES CANNOT BE EXITED
       TRANSITIONS[AGREED] = set()   ← empty set = zero outgoing edges
       TRANSITIONS[FAILED] = set()   ← empty set = zero outgoing edges
       Once entered, these states are permanent. Verified by check_invariants().

  2. MAX TURNS GUARANTEES EXIT
       process_turn() auto-transitions to FAILED at max_turns.
       Loop condition: 'while not fsm.is_terminal()' — ALWAYS terminates.
       This is a proof, not a convention.

  3. FAILURE REASON ENABLES ANALYTICS
       MAX_TURNS_EXCEEDED → no ZOPA, adjust strategy next session
       REJECTED_BY_BUYER  → buyer walked — log for post-mortem
       POLICY_VIOLATION   → illegal message — raise alert

  4. LANGGRAPH IS THE SAME IDEA AT WORKFLOW SCALE
       LangGraph's StateGraph provides identical guarantees:
         - Terminal END node has no outgoing edges
         - Conditional routing enforces turn limits
         - graph.compile() validates the structure before execution

  Next step:
    python m2_mcp/pricing_server.py --check      ← verify MCP server loads
    python m3_langgraph_multiagents/main_langgraph_multiagent.py  ← LangGraph version
""")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="NegotiationFSM — interactive teaching demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python state_machine.py              # full interactive walkthrough (default)
  python state_machine.py --fast       # no pauses, run everything quickly
  python state_machine.py --skip-agents  # skip agent comparison, go straight to FSM build
  python state_machine.py --build      # only show FSM construction (no scenarios)
  python state_machine.py --scenario 1 # only Scenario 1 (deal reached)
  python state_machine.py --scenario 2 # only Scenario 2 (buyer walks away)
  python state_machine.py --scenario 3 # only Scenario 3 (max turns exceeded)
""",
    )
    parser.add_argument(
        "--fast", action="store_true",
        help="Disable step mode — run everything without pausing",
    )
    parser.add_argument(
        "--build", action="store_true",
        help="Only show the FSM construction walkthrough (skip scenarios)",
    )
    parser.add_argument(
        "--scenario", type=int, choices=[1, 2, 3], default=0,
        metavar="N",
        help="Run only one scenario: 1=deal, 2=buyer-walks, 3=max-turns",
    )
    parser.add_argument(
        "--skip-agents", action="store_true",
        help="Skip the agent comparison section and go straight to FSM construction",
    )
    args = parser.parse_args()

    step_mode = not args.fast
    run_all = (args.scenario == 0 and not args.build)

    # ── Intro ──────────────────────────────────────────────────────────────────
    if run_all:
        _header("NegotiationFSM — Termination Guarantee Demo")
        print("""
  Property: 742 Evergreen Terrace, Austin, TX 78701

  This demo has three parts:
    Part 0  — Do the agents change? (naive loop vs FSM loop, side-by-side)
    Part 1  — Building the FSM (states, transitions, why it works)
    Part 2  — 3 Scenarios through the same FSM structure

  Controls: ENTER advances one step.  Ctrl-C to exit at any time.
""")
        _wait(step_mode, "  [ENTER to begin →] ")

    # ── Part 0: Agent comparison (do agents change?) ───────────────────────────
    if run_all and not args.skip_agents:
        _show_agent_fsm_comparison(step_mode)

    # ── Part 1: FSM construction ───────────────────────────────────────────────
    if run_all or args.build:
        _teach_fsm_construction(step_mode)

    if args.build:
        return

    # ── Part 2: Scenarios ─────────────────────────────────────────────────────
    if run_all or args.scenario == 1:
        _scenario1(step_mode)

    if run_all or args.scenario == 2:
        _scenario2(step_mode)

    if run_all or args.scenario == 3:
        _scenario3(step_mode)

    # ── Takeaways ─────────────────────────────────────────────────────────────
    if run_all:
        _print_key_takeaways(step_mode)


if __name__ == "__main__":
    main()
