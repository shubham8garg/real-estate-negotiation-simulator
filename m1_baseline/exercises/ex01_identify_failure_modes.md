# Exercise 1: Add Transition Logger (Code Change)

## Goal
Make FSM transitions easier to debug.

## Edit
In `m1_baseline/state_machine.py`, update `start()` so it prints when state changes from `IDLE` to `NEGOTIATING`.

## What to add
Add this line right after `self.state = NegotiationState.NEGOTIATING`:

```python
print("[FSM] Transition: IDLE -> NEGOTIATING")
```

## Verify
```bash
python m1_baseline/state_machine.py
```

## Expected
You see the transition log line at the beginning of the demo.
