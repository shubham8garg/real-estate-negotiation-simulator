# Solution 2: Improve Result Label

## Code change
In `m4_adk_multiagents/a2a_protocol_http_orchestrator.py`, change:

```python
print("\n=== A2A ORCHESTRATION RESULT ===")
```

to:

```python
print("\n=== A2A NEGOTIATION RESULT ===")
```

## Verify
```bash
python m4_adk_multiagents/a2a_protocol_http_orchestrator.py --seller-url http://127.0.0.1:9102 --rounds 1
```
