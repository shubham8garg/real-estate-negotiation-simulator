# Solution 2: Add Max-Turns Warning

## Code change
In `m1_baseline/state_machine.py` inside `process_turn()`:

```python
if self.context.turn_count >= self.context.max_turns:
	print(f"[FSM] Max turns reached: {self.context.turn_count}/{self.context.max_turns}")
	self.state = NegotiationState.FAILED
```

## Verify
```bash
pytest tests/test_fsm.py -v
```
