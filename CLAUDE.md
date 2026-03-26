# YAZot MCP Server

MCP-сервер для работы с библиотеками Zotero: поиск, оценка научных статей, анализ полных текстов PDF и управление аннотациями.

## Tech Stack

- Python 3.12, type hints везде (включая `type` alias syntax, generics `[T]`)
- FastMCP 2.x — MCP-сервер (декоратор `@mcp.tool`, `@mcp.resource`)
- Pydantic v2 + pydantic-settings — модели и конфигурация
- pyzotero — клиент Zotero API (local + web)
- httpx — async HTTP (Crossref API)
- beautifulsoup4 — парсинг HTML заметок
- uv — пакетный менеджер, lockfile `uv.lock`

## Architecture

```
yazot/
├── mcp_server.py      # FastMCP tools/resources — точка входа
├── zotero_client.py   # ZoteroClient — обёртка pyzotero, local/web режимы
├── client_router.py   # ZoteroClientRouter — роутинг read→local, write→web
├── protocols.py       # ZoteroClientProtocol + @webonly декоратор
├── models.py          # Все Pydantic-модели (ZoteroItem, Note, SearchParams...)
├── crossref_client.py # Получение метаданных по DOI через Crossref API
├── note_manager.py    # CRUD заметок (зависит от ZoteroClientProtocol)
├── chunker.py         # ResponseChunker (items) + TextChunker (fulltext)
├── formatters.py      # Конвертация text↔HTML для заметок
├── config.py          # Settings (pydantic-settings, .env)
└── exceptions.py      # Иерархия ошибок на базе ToolError
```

## Key Patterns

- **Protocol-based DI**: `ZoteroClientProtocol` в `protocols.py`, реализуют `ZoteroClient` и `ZoteroClientRouter`
- **Router pattern**: `ClientRouter` маршрутизирует read→local (быстрее), write→web (local read-only)
- **@webonly decorator**: помечает методы, требующие web API; бросает `WebOnlyOperationError` в local-режиме
- **Chunking**: ответы > `max_chunk_size` токенов разбиваются на чанки с `chunk_id` + `has_more`.
  `MAX_CHUNK_SIZE` (default=5000 токенов ≈ 20K символов) — настроен под лимит Claude Code tool result (~10K токенов).
  Оценка токенов: `len(text) // 4`. `ResponseChunker` дополнительно вычитает `METADATA_OVERHEAD=2000` из лимита.
- **Error hierarchy**: все исключения наследуют `ToolError` (FastMCP) → видны MCP-клиенту даже при `mask_error_details=True`
- **ABC**: `ZoteroItemIterator`, `ZoteroCollectionBase` — абстрактные базы в `models.py`

## Development

```bash
# Запуск сервера
uv run python -m yazot.mcp_server

# Тесты (pytest-asyncio, asyncio_mode="auto")
uv run pytest
uv run pytest tests/test_formatters.py -v     # конкретный файл
uv run pytest -k "test_search" -v              # по имени

# Линтеры (pre-commit: black, ruff, mypy)
uv run ruff check yazot/ tests/
uv run black --check yazot/ tests/
uv run mypy yazot/

# Все pre-commit хуки
pre-commit run --all-files
```

## Environment

Конфигурация через `.env` (pydantic-settings). Два режима:
- **Local** (`ZOTERO_LOCAL=true`): подключение к локальному Zotero (localhost:23119), read-only
- **Web** (`ZOTERO_LOCAL=false`): требует `ZOTERO_LIBRARY_ID` + `ZOTERO_API_KEY`, полный доступ

Для тестов: `.env.test` (загружается автоматически через `conftest.py`)

## Conventions

- Все модели — Pydantic v2 BaseModel (не словари)
- Тесты: моки через `unittest.mock`, фикстуры в `conftest.py`
- Ошибки: кастомные исключения из `exceptions.py`, не голые Exception
