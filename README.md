# Zotero MCP Server v2.0

A simplified MCP (Model Context Protocol) server for Zotero library management, focusing on research evaluation, full-text analysis, and annotation management.

## Features

- **Collection Search & Evaluation** - Search and evaluate items in Zotero collections
- **Full-text Analysis** - Analyze PDFs for research methodology, key points, and summaries
- **Note Management** - Create, read, update, and search research annotations
- **Type Safety** - Full Pydantic models for all data structures
- **Simple Architecture** - KISS & YAGNI principles applied

## Project Structure

```
zotero-mcp-simple/
├── src/
│   ├── mcp_server.py          # FastMCP server with tools
│   ├── zotero_client.py       # Simple client (local/web)
│   ├── text_analyzer.py       # Full-text analysis
│   ├── note_manager.py        # Note CRUD operations
│   ├── chunker.py             # Response chunking
│   └── config.py              # Environment config
├── tests/
│   └── test_core.py           # Basic tests
├── requirements.txt
├── .env.example
└── README.md
```

## Setup

1. Clone repository
2. Copy `.env.example` to `.env` and configure
3. Install dependencies: `pip install -r requirements.txt`
4. Run server: `python src/mcp_server.py`

## Configuration

See `.env.example` for required environment variables.

## Development

This project uses git worktrees for development:
- `main` - stable release
- `develop` - development branch
<<<<<<< HEAD
- Feature branches as needed
=======
- Feature branches as needed
>>>>>>> ed7107b (Initial project setup with gitignore and README)
