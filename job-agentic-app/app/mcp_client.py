import requests

def call_mcp_tool(url: str, payload: dict):
    """Generic MCP tool caller."""
    try:
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}
