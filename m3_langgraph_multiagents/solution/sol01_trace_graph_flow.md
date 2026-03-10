# Solution 1: Add Router Debug Print

## Code change
In `m3_langgraph_multiagents/langgraph_flow.py` inside `route_after_seller`:

```python
def route_after_seller(state: dict) -> Literal["continue", "end"]:
	status = state.get("status", "negotiating")
	print(f"[LangGraph Router] status={status}, round={state.get('round_number')}")
	if status != "negotiating":
		return "end"
	if state.get("round_number", 0) >= state.get("max_rounds", 5):
		return "end"
	return "continue"
```

## Verify
```bash
python m3_langgraph_multiagents/main_langgraph_multiagent.py --rounds 2
```
