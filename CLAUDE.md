# YAZot MCP Server

MCP server for Zotero libraries: search, evaluate scientific articles, analyze PDF full texts, and manage annotations.

## Tech Stack

- Python 3.12, type hints everywhere (including `type` alias syntax, generics `[T]`)
- FastMCP 2.x — MCP server (`@mcp.tool`, `@mcp.resource` decorators)
- Pydantic v2 + pydantic-settings — models and configuration
- pyzotero — Zotero API client (local + web)
- httpx — async HTTP (Crossref API)
- beautifulsoup4 — HTML note parsing
- uv — package manager, lockfile `uv.lock`

## Architecture

```
yazot/
├── mcp_server.py         # FastMCP tools/resources — entry point
├── zotero_client.py      # ZoteroClient — pyzotero wrapper, local/web modes
├── client_router.py      # ZoteroClientRouter — routes read→local, write→web
├── protocols.py          # ZoteroClientProtocol + @webonly decorator
├── models.py             # All Pydantic models (ZoteroItem, Note, SearchParams...)
├── crossref_client.py    # DOI metadata retrieval via Crossref API
├── fulltext_resolver.py  # Cascading fulltext search: Unpaywall → CORE → Libgen
├── pdf_utils.py          # Shared: extract_text_from_pdf(bytes) → str
├── note_manager.py       # Note CRUD (depends on ZoteroClientProtocol)
├── chunker.py            # ResponseChunker (items) + TextChunker (fulltext)
├── verifier.py           # NoteVerifier — verifies note citations against fulltext
├── formatters.py         # text↔HTML conversion for notes
├── config.py             # Settings (pydantic-settings, .env)
└── exceptions.py         # Error hierarchy based on ToolError
```

## Key Patterns

- **Protocol-based DI**: `ZoteroClientProtocol` in `protocols.py`, implemented by `ZoteroClient` and `ZoteroClientRouter`
- **Router pattern**: `ClientRouter` routes read→local (faster), write→web (local is read-only)
- **@webonly decorator**: marks methods requiring web API; raises `WebOnlyOperationError` in local mode
- **Chunking**: responses > `max_chunk_size` tokens are split into chunks with `chunk_id` + `has_more`.
  `MAX_CHUNK_SIZE` (default=5000 tokens ≈ 20K chars) — tuned for Claude Code tool result limit (~10K tokens).
  Token estimation: `len(text) // 4`. `ResponseChunker` additionally subtracts `METADATA_OVERHEAD=2000` from the limit.
- **Error hierarchy**: all exceptions inherit `ToolError` (FastMCP) → visible to MCP client even with `mask_error_details=True`
- **ABC**: `ZoteroItemIterator`, `ZoteroCollectionBase` — abstract bases in `models.py`

## Development

```bash
# Install dev dependencies (required in new worktrees!)
uv sync --group dev

# Run server
uv run python -m yazot.mcp_server

# Unit tests (no live Zotero needed, parallelizable)
uv run pytest tests/unit/ -q
uv run pytest tests/unit/ -n auto -q           # parallel via xdist

# E2E tests (requires TEST_ZOTERO_API_KEY)
uv run pytest tests/e2e/ -q

# External API tests (real Crossref calls)
uv run pytest tests/external/ -q

# All tests
uv run pytest
uv run pytest tests/unit/test_formatters.py -v # specific file
uv run pytest -k "test_search" -v              # by name
uv run pytest -m unit -q                       # by marker

# Linters (pre-commit: ruff, mypy) — run sequentially, not in parallel
uv run ruff check yazot/ tests/
uv run ruff format --check yazot/ tests/
uv run mypy yazot/

# All pre-commit hooks
pre-commit run --all-files
```

**Claude Code hooks**: PostToolUse on Edit/Write auto-runs ruff --fix + ruff format on .py files.

## Worktree Workflow

- Feature development: always enter a worktree via `EnterWorktree` before making changes
- Quick fixes, typos, config changes — work directly in main, no worktree needed
- To resume work in an existing worktree — use `EnterWorktree` with the same name. Never `cd` into the worktree path directly
- Worktrees contain only git-tracked files. `hooks/`, `settings.json`, `settings.local.json` live in `$CLAUDE_PROJECT_DIR/.claude/` and are shared — edit them from the main project path
- `ExitWorktree(remove)` requires `discard_changes=true` if there are commits not in main (even if already pushed)
- The Stop hook blocks session end in a worktree — ask the user to choose:
  1. **Push + PR**: commit all, `git push -u origin <branch>`, `gh pr create`, then `ExitWorktree(remove, discard_changes=true)`
  2. **Keep**: `ExitWorktree(keep)` — worktree stays for later
  3. **Discard**: `ExitWorktree(remove, discard_changes=true)`

## Environment

Configuration via `.env` (pydantic-settings). Two modes:
- **Local** (`ZOTERO_LOCAL=true`): connects to local Zotero (localhost:23119), read-only
- **Web** (`ZOTERO_LOCAL=false`): requires `ZOTERO_LIBRARY_ID` + `ZOTERO_API_KEY`, full access

For tests: `.env.test` (auto-loaded via `conftest.py`)

## Conventions

- All models — Pydantic v2 BaseModel (not dicts)
- Tests: mocks via `unittest.mock`, fixtures in `conftest.py`, pytest-asyncio (`asyncio_mode="auto"`)
- All MCP tools and I/O are async
- Commit messages, PR titles/body, code comments — always in English
- Errors: custom exceptions from `exceptions.py`, never bare Exception
- `ZoteroItemData.doi` can be `""` (empty string), not just `None` — normalize via `or None`
- PDF attachment: `router.attach_pdf(item_key, filepath)` — NOT via `_client` directly
- PDF extraction: `pdf_utils.extract_text_from_pdf(bytes)` — shared utility, do not duplicate
- E2E error tests: `Client.call_tool` raises `ToolError` by default — use `pytest.raises(ToolError)`
- Mock httpx responses: `from tests.conftest import make_httpx_response`
