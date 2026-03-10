# Exercise 2: Improve Result Label (Code Change)

## Goal
Make final output text clearer.

## Edit
In `m4_adk_multiagents/a2a_protocol_http_orchestrator.py`, change:

```python
print("\n=== A2A ORCHESTRATION RESULT ===")
```

to:

```python
print("\n=== A2A NEGOTIATION RESULT ===")
```

## Verify
Run one round and confirm the new heading appears:

```bash
python m4_adk_multiagents/a2a_protocol_http_orchestrator.py --seller-url http://127.0.0.1:9102 --rounds 1
```
