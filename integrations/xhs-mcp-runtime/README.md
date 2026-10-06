# TravelMind Xiaohongshu MCP runtime

This directory pins `@sillyl12324/xhs-mcp` and runs it through
`read-only-server.mjs`.

The wrapper exposes only account authentication, search, and note-detail tools.
It does **not** expose publishing, liking, collecting, commenting, following,
deleting, or other platform-write operations. Image understanding is also
disabled during collection.

## Setup and use

From the project root:

```powershell
python scripts/setup_xhs_mcp.py
python main.py
python -m scripts.manage_xhs status
python -m scripts.manage_xhs login --name TravelMind
python -m scripts.manage_xhs check-login <session-id>
python -m scripts.manage_xhs crawl --account TravelMind --city 北京 --notes-per-cell 3
```

The local browser session and MCP SQLite database are stored in `.xhs-mcp/`,
which is excluded from Git. Raw TravelMind evidence is stored under the RAG raw
data directory. Search security tokens are used transiently and are never
stored. Comment bodies and direct author identifiers are excluded from the raw
archive.

The upstream package is MIT-licensed, but platform content is not covered by
that software license. Keep the corpus private, use bounded request rates, and
review Xiaohongshu's current terms before any redistribution or production use.
