# Exercise 2: Add Max-Turns Warning (Code Change)

## Goal
Log exactly when the FSM hits the round limit.

## Edit
In `m1_baseline/state_machine.py`, inside `process_turn()`, add a print statement in the block:

```python
if self.context.turn_count >= self.context.max_turns:
```

## What to add
Before setting `self.state = NegotiationState.FAILED`, add:

```python
print(f"[FSM] Max turns reached: {self.context.turn_count}/{self.context.max_turns}")
```

## Verify
```bash
pytest tests/test_fsm.py -v
```

## Expected
Tests still pass and the warning appears when limit logic is hit in demo runs.
