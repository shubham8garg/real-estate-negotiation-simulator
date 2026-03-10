# Solution 1: Add Transition Logger

## Code change
In `m1_baseline/state_machine.py` inside `start()`:

```python
def start(self) -> bool:
	if self.state != NegotiationState.IDLE:
		return False
	self.state = NegotiationState.NEGOTIATING
	print("[FSM] Transition: IDLE -> NEGOTIATING")
	return True
```

## Verify
```bash
python m1_baseline/state_machine.py
```
