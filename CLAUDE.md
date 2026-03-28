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
├── mcp_server.py         # FastMCP tools/resources — точка входа
├── zotero_client.py      # ZoteroClient — обёртка pyzotero, local/web режимы
├── client_router.py      # ZoteroClientRouter — роутинг read→local, write→web
├── protocols.py          # ZoteroClientProtocol + @webonly декоратор
├── models.py             # Все Pydantic-модели (ZoteroItem, Note, SearchParams...)
├── crossref_client.py    # Получение метаданных по DOI через Crossref API
├── fulltext_resolver.py  # Каскадный поиск fulltext: Unpaywall → CORE → Libgen
├── pdf_utils.py          # Shared: extract_text_from_pdf(bytes) → str
├── note_manager.py       # CRUD заметок (зависит от ZoteroClientProtocol)
├── chunker.py            # ResponseChunker (items) + TextChunker (fulltext)
├── verifier.py           # NoteVerifier — проверка цитат в заметках против fulltext
├── formatters.py         # Конвертация text↔HTML для заметок
├── config.py             # Settings (pydantic-settings, .env)
└── exceptions.py         # Иерархия ошибок на базе ToolError
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
# Установка dev-зависимостей (обязательно в новом worktree!)
uv sync --group dev

# Запуск сервера
uv run python -m yazot.mcp_server

# Быстрые unit-тесты (без live Zotero)
uv run pytest tests/test_formatters.py tests/test_response_chunker.py tests/test_text_chunker.py tests/test_client_router.py -q

# Все тесты (часть требует запущенный Zotero + API key)
uv run pytest
uv run pytest tests/test_formatters.py -v     # конкретный файл
uv run pytest -k "test_search" -v              # по имени

# Линтеры (pre-commit: black, ruff, mypy) — запускать последовательно, не параллельно
uv run ruff check yazot/ tests/
uv run black --check yazot/ tests/
uv run mypy yazot/

# Все pre-commit хуки
pre-commit run --all-files
```

**Хуки Claude Code**: PostToolUse на Edit/Write автоматически запускает ruff --fix + black на .py файлах.

## Environment

Конфигурация через `.env` (pydantic-settings). Два режима:
- **Local** (`ZOTERO_LOCAL=true`): подключение к локальному Zotero (localhost:23119), read-only
- **Web** (`ZOTERO_LOCAL=false`): требует `ZOTERO_LIBRARY_ID` + `ZOTERO_API_KEY`, полный доступ

Для тестов: `.env.test` (загружается автоматически через `conftest.py`)

## Conventions

- Все модели — Pydantic v2 BaseModel (не словари)
- Тесты: моки через `unittest.mock`, фикстуры в `conftest.py`
- Ошибки: кастомные исключения из `exceptions.py`, не голые Exception
- `ZoteroItemData.doi` может быть `""` (пустая строка), не только `None` — нормализуй через `or None`
- PDF attachment: `router.attach_pdf(item_key, filepath)` — НЕ через `_client` напрямую
- PDF extraction: `pdf_utils.extract_text_from_pdf(bytes)` — shared утилита, не дублировать
- E2E error tests: `Client.call_tool` бросает `ToolError` по умолчанию — используй `pytest.raises(ToolError)`
- Mock httpx responses: `from tests.conftest import make_httpx_response`
