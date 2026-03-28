# YAZot — Yet Another Zotero MCP Server

MCP server for working with Zotero libraries from AI assistants (Claude Code, Claude Desktop, etc.). Search articles, read full texts, manage collections, create and verify annotations.

## Why another one

Existing Zotero MCP servers typically work through the web API only and return entire responses at once. YAZot does a few things differently:

**Hybrid client.** YAZot can use both the local Zotero API (localhost, read-only, fast, no rate limits) and the web API (full access, write support) simultaneously. Read operations go through the local client when available, write operations go through the web API. If the local client fails, requests fall back to web automatically. You can also run in local-only or web-only mode.

**Response chunking.** Large responses are split into chunks sized for MCP tool result limits (~10K tokens). The client receives the first chunk with a `chunk_id` and calls `get_next_chunk` to retrieve the rest. Same mechanism works for article full texts — long PDFs are split by paragraphs and sentences.

**Citation verification.** Notes created with blockquotes (`> quoted text`) can be verified against the article's full text. The server checks whether each quote actually appears in the source and tags the note as `verified` or `unverified`.

**DOI import.** Add articles by DOI — metadata is fetched from Crossref and converted to Zotero format automatically.

## Tools

| Tool | Description |
|------|-------------|
| `search_articles` | Search by query, tags, collection, item type |
| `get_collection_items` | List items in a collection (with optional subcollection recursion) |
| `get_item_fulltext` | Get PDF text (indexed API first, direct PDF parsing as fallback) |
| `create_note_for_item` | Create a note attached to an item |
| `get_item_notes` | Get all notes for an item |
| `verify_note` | Verify blockquote citations against article full text |
| `add_item_by_doi` | Import article by DOI via Crossref |
| `add_items_to_collection` | Add existing items to a collection |
| `create_collection` | Create a collection or subcollection |
| `remove_item` | Remove from collection or delete from library |
| `get_next_chunk` / `get_next_fulltext_chunk` | Retrieve remaining chunks |

Resource `resource://collections` lists all collections with keys.

## Setup

Requires Python 3.12+.

```bash
git clone <repo-url>
cd yazot-mcp-project
cp .env.example .env
# edit .env — see configuration below
uv sync
uv run python -m yazot.mcp_server
```

## Configuration

All settings are in `.env` (loaded via pydantic-settings).

```
# Web API (full access)
ZOTERO_LOCAL=false
ZOTERO_LIBRARY_ID=your_library_id
ZOTERO_API_KEY=your_api_key
ZOTERO_LIBRARY_TYPE=user

# Local API (read-only, requires Zotero 7+ running)
ZOTERO_LOCAL=true
ZOTERO_PORT=23119

# Hybrid mode: set ZOTERO_LOCAL=true AND provide ZOTERO_API_KEY + ZOTERO_LIBRARY_ID
# Reads go through local, writes through web

# Chunking
MAX_CHUNK_SIZE=5000
```

## Claude Desktop integration

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "yazot": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/yazot-mcp-project", "python", "-m", "yazot.mcp_server"],
      "env": {
        "ZOTERO_LOCAL": "true",
        "ZOTERO_LIBRARY_ID": "your_id",
        "ZOTERO_API_KEY": "your_key"
      }
    }
  }
}
```

## Development

```bash
uv sync --group dev
uv run pytest                    # all tests (some need running Zotero)
uv run pytest tests/test_formatters.py tests/test_response_chunker.py tests/test_text_chunker.py tests/test_client_router.py -q  # unit tests only
uv run ruff check yazot/ tests/
uv run black --check yazot/ tests/
uv run mypy yazot/
```

## Tech stack

Python 3.12, FastMCP 2.x, Pydantic v2, pyzotero, httpx, pypdf, beautifulsoup4.
