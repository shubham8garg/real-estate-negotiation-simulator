# Exercise 2: Change CLI Default Rounds (Code Change)

## Goal
Practice editing argparse defaults.

## Edit
In `m3_langgraph_multiagents/main_langgraph_multiagent.py`, change the default for `--rounds` from `5` to `3`.

## Hint
Find this argument:

```python
parser.add_argument("--rounds", type=int, default=5, ...)
```

## Verify
```bash
python m3_langgraph_multiagents/main_langgraph_multiagent.py
```

## Expected
Startup output shows `Max Rounds:     3` when no `--rounds` flag is passed.
