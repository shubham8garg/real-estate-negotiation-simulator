# Solution 2: Change CLI Default Rounds

## Code change
In `m3_langgraph_multiagents/main_langgraph_multiagent.py`, change:

```python
parser.add_argument(
	"--rounds",
	type=int,
	default=5,
	help="Maximum number of negotiation rounds (default: 5)"
)
```

to:

```python
parser.add_argument(
	"--rounds",
	type=int,
	default=3,
	help="Maximum number of negotiation rounds (default: 3)"
)
```

## Verify
```bash
python m3_langgraph_multiagents/main_langgraph_multiagent.py
```
