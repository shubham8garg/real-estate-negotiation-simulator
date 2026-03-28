"""
MODULE 1 — EXERCISE 1 SOLUTION: Add a TIMEOUT Terminal State
=============================================================
This file is the COMPLETE SOLUTION for Exercise 1.
It is a self-contained copy of state_machine.py with the TIMEOUT
state added. The original state_machine.py is NOT modified.

WHAT WAS CHANGED vs the original state_machine.py:
  1. NegotiationState enum   — added TIMEOUT
  2. FailureReason enum      — added WALL_CLOCK_TIMEOUT
  3. FSMContext dataclass     — added deadline_seconds, start_time
  4. TRANSITIONS table        — TIMEOUT added with empty set()
  5. NegotiationFSM.start()  — records start_time = time.time()
  6. process_turn()          — checks wall-clock before turn counter
  7. is_terminal()           — includes TIMEOUT
  8. check_invariants()      — validates TIMEOUT state

Search for "# SOLUTION:" comments to find every change.

HOW TO RUN (step-by-step with pauses):
  python m1_baseline/solution/sol01_state_machine_timeout.py

HOW TO RUN (no pauses):
  python m1_baseline/solution/sol01_state_machine_timeout.py --fast

TERMINATION PROOF FOR TIMEOUT:
  TIMEOUT has an empty transition set — once entered, no transitions
  are possible. The deadline check in process_turn() adds an additional
  path to a terminal state, which can only make termination happen
  SOONER, never later. The guarantee is fully preserved.
"""

import argparse
import os
import sys
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


# ─── Optional import of agents from naive_negotiation.py ─────────────────────
try:
    _here = os.path.dirname(os.path.abspath(__file__))
    _root = os.path.dirname(os.path.dirname(_here))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from m1_baseline.naive_negotiation import (
        NaiveBuyer, NaiveSeller,
        BUYER_MAX_PRICE, SELLER_MIN_PRICE, SELLER_ASKING_PRICE, PROPERTY_ADDRESS,
    )
    _AGENTS_AVAILABLE = True
except Exception:
    _AGENTS_AVAILABLE = False


# ─── Display helpers ──────────────────────────────────────────────────────────

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
    print("\n" + "━" * width)
    print("  " + title)
    print("━" * width)


def _show_fsm(fsm: "NegotiationFSM", label: str = "") -> None:
    terminal = "YES — no further transitions possible" if fsm.is_terminal() else "No"
    agreed = f"  agreed_price:   ${fsm.context.agreed_price:,.0f}" if fsm.context.agreed_price else ""
    reason = f"  failure_reason: {fsm.context.failure_reason.name}" if fsm.context.failure_reason else ""
    elapsed = ""
    if fsm.context.start_time is not None:
        elapsed = f"  elapsed:        {time.time() - fsm.context.start_time:.2f}s / {fsm.context.deadline_seconds:.0f}s deadline"
    prefix = f"  [{label}]" if label else " "
    print(f"""
{prefix}
  state:       {fsm.state.name}
  turn_count:  {fsm.context.turn_count} / {fsm.context.max_turns}{agreed}{reason}{elapsed}
  is_terminal: {terminal}""")


# ─────────────────────────────────────────────────────────────────────────────
# STATE DEFINITIONS — with SOLUTION changes marked
# ─────────────────────────────────────────────────────────────────────────────

class NegotiationState(Enum):
    IDLE        = auto()    # Not yet started
    NEGOTIATING = auto()    # Active
    AGREED      = auto()    # Terminal: deal reached ✓
    FAILED      = auto()    # Terminal: no deal ✗
    TIMEOUT     = auto()    # SOLUTION: Terminal: wall-clock deadline exceeded ⏱


class FailureReason(Enum):
    MAX_TURNS_EXCEEDED  = auto()
    REJECTED_BY_BUYER   = auto()
    REJECTED_BY_SELLER  = auto()
    POLICY_VIOLATION    = auto()
    INVALID_TRANSITION  = auto()
    WALL_CLOCK_TIMEOUT  = auto()    # SOLUTION: wall-clock deadline exceeded


# ─── FSM Context ──────────────────────────────────────────────────────────────

@dataclass
class FSMContext:
    turn_count:        int                      = 0
    max_turns:         int                      = 5
    last_offer:        Optional[float]          = None
    agreed_price:      Optional[float]          = None
    failure_reason:    Optional[FailureReason]  = None
    # SOLUTION: wall-clock deadline tracking
    deadline_seconds:  float                    = 60.0   # max negotiation time
    start_time:        Optional[float]          = None   # set by start()


# ─── The FSM ──────────────────────────────────────────────────────────────────

class NegotiationFSM:

    # SOLUTION: TIMEOUT added to transition table with empty set()
    # This single line is what preserves the termination guarantee.
    # TIMEOUT is reachable from NEGOTIATING, but has no outgoing transitions.
    TRANSITIONS: dict[NegotiationState, set[NegotiationState]] = {
        NegotiationState.IDLE:        {NegotiationState.NEGOTIATING, NegotiationState.FAILED},
        NegotiationState.NEGOTIATING: {NegotiationState.NEGOTIATING, NegotiationState.AGREED,
                                       NegotiationState.FAILED, NegotiationState.TIMEOUT},
        NegotiationState.AGREED:      set(),    # TERMINAL
        NegotiationState.FAILED:      set(),    # TERMINAL
        NegotiationState.TIMEOUT:     set(),    # SOLUTION: TERMINAL — empty set
    }

    def __init__(self, max_turns: int = 5, deadline_seconds: float = 60.0):
        self.state = NegotiationState.IDLE
        self.context = FSMContext(max_turns=max_turns, deadline_seconds=deadline_seconds)

    @property
    def is_active(self) -> bool:
        return self.state == NegotiationState.NEGOTIATING

    def is_terminal(self) -> bool:
        # SOLUTION: TIMEOUT included — it has empty transition set
        return self.state in {NegotiationState.AGREED, NegotiationState.FAILED,
                               NegotiationState.TIMEOUT}

    def can_transition(self, to_state: NegotiationState) -> bool:
        return to_state in self.TRANSITIONS[self.state]

    def start(self) -> bool:
        if self.state != NegotiationState.IDLE:
            return False
        self.state = NegotiationState.NEGOTIATING
        # SOLUTION: record wall-clock start time
        self.context.start_time = time.time()
        return True

    def process_turn(self) -> bool:
        if not self.is_active:
            return False

        # SOLUTION: Check wall-clock deadline BEFORE the turn counter.
        # Timeout is a harder constraint — it overrides everything else.
        if self.context.start_time is not None:
            elapsed = time.time() - self.context.start_time
            if elapsed > self.context.deadline_seconds:
                self.state = NegotiationState.TIMEOUT
                self.context.failure_reason = FailureReason.WALL_CLOCK_TIMEOUT
                return False

        self.context.turn_count += 1
        if self.context.turn_count >= self.context.max_turns:
            self.state = NegotiationState.FAILED
            self.context.failure_reason = FailureReason.MAX_TURNS_EXCEEDED
            return False
        return True

    def accept(self, price: float) -> bool:
        if not self.is_active:
            return False
        self.state = NegotiationState.AGREED
        self.context.agreed_price = price
        return True

    def reject(self, by_buyer: bool = True) -> bool:
        if not self.is_active:
            return False
        self.state = NegotiationState.FAILED
        self.context.failure_reason = (
            FailureReason.REJECTED_BY_BUYER if by_buyer
            else FailureReason.REJECTED_BY_SELLER
        )
        return True

    def check_invariants(self) -> bool:
        assert self.context.turn_count >= 0
        assert self.context.turn_count <= self.context.max_turns

        if self.state == NegotiationState.AGREED:
            assert self.context.agreed_price is not None

        if self.state == NegotiationState.FAILED:
            assert self.context.failure_reason is not None

        # SOLUTION: TIMEOUT requires WALL_CLOCK_TIMEOUT reason
        if self.state == NegotiationState.TIMEOUT:
            assert self.context.failure_reason == FailureReason.WALL_CLOCK_TIMEOUT, (
                "TIMEOUT state requires failure_reason = WALL_CLOCK_TIMEOUT"
            )

        # Core guarantee: all terminal states must have empty transition sets
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


# ─── Solution Walkthrough Demo ────────────────────────────────────────────────

def run_solution_demo(step_mode: bool) -> None:
    _header("Exercise 1 Solution — TIMEOUT Terminal State")
    print("""
  This file is the COMPLETE SOLUTION for M1 Exercise 1.
  The original state_machine.py is UNCHANGED — this is a separate file.

  We added a TIMEOUT state that fires when the wall-clock deadline is exceeded.
  The key constraint: TIMEOUT must be TERMINAL (empty transition set).
  Otherwise, the termination guarantee would be broken.

  Search for "# SOLUTION:" in this file to find every change.
""")
    _wait(step_mode, "  [ENTER: see the 5 key changes →] ")

    # ── Change 1: Enum ────────────────────────────────────────────────────────
    _section("Change 1 of 5 — NegotiationState enum")
    print("""
  ORIGINAL (state_machine.py):
    IDLE, NEGOTIATING, AGREED, FAILED

  SOLUTION (this file):
    IDLE, NEGOTIATING, AGREED, FAILED, TIMEOUT  ← one new line

  That's it. But the enum alone is not enough — we need to wire it in.
""")
    _wait(step_mode, "  [ENTER: Change 2 — transition table →] ")

    # ── Change 2: Transition table ────────────────────────────────────────────
    _section("Change 2 of 5 — TRANSITIONS table (THE critical change)")
    print("""
  ORIGINAL:
    NegotiationState.NEGOTIATING: {NEGOTIATING, AGREED, FAILED}
    NegotiationState.AGREED:      set()   ← terminal
    NegotiationState.FAILED:      set()   ← terminal

  SOLUTION:
    NegotiationState.NEGOTIATING: {NEGOTIATING, AGREED, FAILED, TIMEOUT}
    NegotiationState.AGREED:      set()   ← terminal
    NegotiationState.FAILED:      set()   ← terminal
    NegotiationState.TIMEOUT:     set()   ← TERMINAL — THIS IS THE KEY LINE

  Why is TIMEOUT: set() the critical line?
    Empty set = no outgoing transitions = once entered, cannot be exited.
    That's the definition of a terminal state.
    The termination guarantee holds: TIMEOUT is just one more terminal state.
""")
    _wait(step_mode, "  [ENTER: Change 3 — FSMContext deadline fields →] ")

    # ── Change 3: FSMContext ──────────────────────────────────────────────────
    _section("Change 3 of 5 — FSMContext: deadline_seconds + start_time")
    print("""
  Added to FSMContext dataclass:
    deadline_seconds: float = 60.0   # max wall-clock time (configurable)
    start_time: Optional[float] = None  # set when start() is called

  These two fields are the data that makes the deadline check possible.
  Without start_time, we have nothing to measure elapsed time against.
""")
    _wait(step_mode, "  [ENTER: Change 4 — process_turn() deadline check →] ")

    # ── Change 4: process_turn ────────────────────────────────────────────────
    _section("Change 4 of 5 — process_turn() wall-clock check")
    print("""
  Added at the TOP of process_turn(), before the turn counter:

    elapsed = time.time() - self.context.start_time
    if elapsed > self.context.deadline_seconds:
        self.state = NegotiationState.TIMEOUT
        self.context.failure_reason = FailureReason.WALL_CLOCK_TIMEOUT
        return False

  WHY before the turn counter?
    Timeout is a HARDER constraint — it must override everything else.
    If the deadline fires at turn 3 out of 5, we stop immediately.
    We don't wait for max_turns.

  WHY return False?
    Same as when max_turns is exceeded — tells the caller to stop looping.
""")
    _wait(step_mode, "  [ENTER: Change 5 — is_terminal() + check_invariants() →] ")

    # ── Change 5: is_terminal + invariants ────────────────────────────────────
    _section("Change 5 of 5 — is_terminal() and check_invariants()")
    print("""
  is_terminal() — one word added:
    ORIGINAL: return self.state in {AGREED, FAILED}
    SOLUTION: return self.state in {AGREED, FAILED, TIMEOUT}

  If you forget this, the negotiation loop will try to continue after
  TIMEOUT fires — is_terminal() returns False, so the while loop keeps going.
  This is the kind of subtle bug that causes production incidents.

  check_invariants() — one new assertion:
    if self.state == TIMEOUT:
        assert failure_reason == WALL_CLOCK_TIMEOUT

  Invariant checking catches FSM-level bugs early and gives clear error
  messages instead of silent corruption.
""")
    _wait(step_mode, "  [ENTER: run live scenarios →] ")

    # ── Scenario A: Normal deal (no timeout) ──────────────────────────────────
    _section("Scenario A — Normal deal (TIMEOUT never fires)")
    print("  Deadline: 60 seconds. This negotiation takes <1 second. TIMEOUT stays dormant.\n")

    fsm = NegotiationFSM(max_turns=5, deadline_seconds=60.0)
    fsm.start()
    _show_fsm(fsm, "after start()")
    _wait(step_mode)

    for price in [440_000, 455_000, 462_000]:
        fsm.process_turn()
        fsm.accept(price)
        if fsm.is_terminal():
            break

    _show_fsm(fsm, f"AGREED at ${fsm.context.agreed_price:,.0f}")
    fsm.check_invariants()
    print("  check_invariants() passed ✓")
    _wait(step_mode, "  [ENTER: Scenario B — max turns →] ")

    # ── Scenario B: Max turns (FAILED) ────────────────────────────────────────
    _section("Scenario B — Max turns exceeded (FAILED, not TIMEOUT)")
    print("  5 turns at 60s deadline — negotiation hits turn limit first.\n")

    fsm2 = NegotiationFSM(max_turns=5, deadline_seconds=60.0)
    fsm2.start()
    while fsm2.is_active:
        if not fsm2.process_turn():
            break
        fsm2.context.last_offer = 440_000  # no agreement reached

    _show_fsm(fsm2, "max turns exceeded")
    assert fsm2.state == NegotiationState.FAILED
    assert fsm2.context.failure_reason == FailureReason.MAX_TURNS_EXCEEDED
    print("  State = FAILED (not TIMEOUT) — turn counter fired first ✓")
    _wait(step_mode, "  [ENTER: Scenario C — TIMEOUT fires →] ")

    # ── Scenario C: TIMEOUT fires ─────────────────────────────────────────────
    _section("Scenario C — TIMEOUT fires (deadline_seconds = 0.01s)")
    print("  Deadline: 0.01 seconds — guaranteed to expire before the first turn.\n")

    fsm3 = NegotiationFSM(max_turns=5, deadline_seconds=0.01)
    fsm3.start()
    time.sleep(0.02)   # exceed the deadline
    result = fsm3.process_turn()

    _show_fsm(fsm3, "after process_turn() with expired deadline")
    assert result is False, "process_turn() should return False when TIMEOUT fires"
    assert fsm3.state == NegotiationState.TIMEOUT
    assert fsm3.context.failure_reason == FailureReason.WALL_CLOCK_TIMEOUT
    fsm3.check_invariants()
    print("  State = TIMEOUT ✓")
    print("  failure_reason = WALL_CLOCK_TIMEOUT ✓")
    print("  TRANSITIONS[TIMEOUT] = set() (empty) ✓  — termination guarantee preserved")
    print("  check_invariants() passed ✓")
    _wait(step_mode, "  [ENTER: see the termination proof →] ")

    # ── Termination proof ─────────────────────────────────────────────────────
    _section("Termination Proof — Why TIMEOUT doesn't break the guarantee")
    print("""
  The termination guarantee requires:
    1. Terminal states have EMPTY transition sets (cannot be exited)
    2. Every non-terminal path either reaches a terminal state
       OR increments a bounded counter

  Does TIMEOUT satisfy these?

  ✓ Property 1: TIMEOUT: set()  — empty set, cannot be exited
  ✓ Property 2: The deadline check is an ADDITIONAL path to a terminal
                state. It can only make termination happen SOONER,
                never later.

  Informal proof (2 sentences):
    TIMEOUT has an empty transition set, so once entered it cannot
    be exited — it is terminal. The deadline check provides an
    additional path to a terminal state, which can only make
    termination happen sooner than the turn counter alone.  QED.
""")


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="M1 Exercise 1 Solution — TIMEOUT state demo"
    )
    parser.add_argument("--fast", action="store_true", help="Skip interactive pauses")
    args = parser.parse_args()

    run_solution_demo(step_mode=not args.fast)
