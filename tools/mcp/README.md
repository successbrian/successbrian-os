# Ecosystem Data MCP server

Exposes the ecosystem database as MCP tools so agents query it
conversationally instead of hand-writing SQL.

## Tools

- `second_brain_search` — search learnings by keyword
- `pipeline_health` — latest health check + active alerts
- `ingest_candidates` — proposed income streams/audiences/campaigns
- `inbox_recent` — recent dashboard inbox reports

## Run

```bash
python3 ecosystem_data.py   # stdio transport
```

Wire into an MCP client config:

```json
{
  "mcpServers": {
    "ecosystem-data": {
      "command": "python3",
      "args": ["/home/successbrian/mcp-servers/ecosystem_data.py"]
    }
  }
}
```

Read-only: every tool is a SELECT. Nothing here writes.
