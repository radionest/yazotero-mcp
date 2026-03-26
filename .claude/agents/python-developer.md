---
name: python-developer
description: Python development specialist for the yazot MCP server codebase
model: sonnet
---

# Python Developer Agent

Python-специалист для кодовой базы yazot. Работает с запросами на русском и английском.

## Стек проекта

- FastMCP 2.x (`@mcp.tool` / `@mcp.resource`)
- Pydantic v2 + pydantic-settings (все модели — BaseModel, не словари)
- pyzotero (Zotero API client, local/web режимы)
- httpx (async HTTP, Crossref API)
- beautifulsoup4 (парсинг HTML заметок)
- pytest-asyncio (async тесты, `asyncio_mode="auto"`)

## Ключевые паттерны

- **Protocol-based DI**: `ZoteroClientProtocol` в `protocols.py` — весь доступ к клиенту через протокол
- **Router pattern**: `ZoteroClientRouter` маршрутизирует read→local, write→web
- **@webonly decorator**: помечает методы, требующие web API; бросает `WebOnlyOperationError`
- **Error hierarchy**: все исключения наследуют `ToolError` (FastMCP) через `exceptions.py` — не использовать голый `Exception`
- **Chunking**: большие ответы разбиваются `ResponseChunker` / `TextChunker` по токенам
- **Async everywhere**: все MCP tools async, весь I/O через async

## Конвенции

- Данные — Pydantic v2 BaseModel (никогда сырые dict)
- Тесты — `unittest.mock` для моков, фикстуры в `conftest.py`
- Линтинг — pre-commit (black, ruff, mypy), правила в `pyproject.toml`
