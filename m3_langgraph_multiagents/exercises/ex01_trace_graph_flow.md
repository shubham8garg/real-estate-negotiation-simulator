# Exercise 1: Add Router Debug Print (Code Change)

## Goal
Make routing decisions visible in logs.

## Edit
In `m3_langgraph_multiagents/langgraph_flow.py`, inside one router function (for example `route_after_seller`), add a debug print right before returning.

## What to add
Example:

```python
print(f"[LangGraph Router] status={status}, round={state.get('round_number')}")
```

## Verify
```bash
python m3_langgraph_multiagents/main_langgraph_multiagent.py --rounds 2
```

## Expected
Router logs appear each iteration.
