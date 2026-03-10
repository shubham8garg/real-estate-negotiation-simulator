# Solution 1: Add a Simple MCP Tool

## Code change
In `m2_mcp/pricing_server.py`, add:

```python
@mcp.tool()
def get_property_tax_estimate(price: float, tax_rate: float = 0.02) -> dict:
	annual_tax = int(price * tax_rate)
	return {
		"price": price,
		"tax_rate": tax_rate,
		"estimated_annual_tax": annual_tax,
	}
```

## Verify
```bash
python m2_mcp/pricing_server.py
```
