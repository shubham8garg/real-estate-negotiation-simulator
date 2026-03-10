# Solution 1: Change Orchestrator Default Rounds

## Code change
In `m4_adk_multiagents/a2a_protocol_http_orchestrator.py`, update:

```python
parser.add_argument("--rounds", type=int, default=5)
```

to:

```python
parser.add_argument("--rounds", type=int, default=3)
```

## Verify
```bash
python m4_adk_multiagents/a2a_protocol_http_orchestrator.py --seller-url http://127.0.0.1:9102
```
