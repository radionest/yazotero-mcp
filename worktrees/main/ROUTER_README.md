# Zotero Client Router Documentation

## Обзор

Система поддержки локального и веб API для Zotero с автоматическим выбором клиента.

## Архитектура

### 1. Декоратор `@webonly` ([src/protocols.py](src/protocols.py))

Защищает write-операции от выполнения через локальный API:

```python
from src.protocols import webonly

class ZoteroClient:
    @webonly
    async def create_items(self, items):
        # Эта операция будет заблокирована для локального клиента
        ...
```

**Поднимает:** `WebOnlyOperationError` если клиент в режиме `local`

### 2. Router ([src/client_router.py](src/client_router.py))

Интеллектуальный выбор клиента на основе типа операции:

```python
from src.client_router import client_router

# Автоматический выбор клиента
read_client = client_router.read_client      # Предпочитает локальный (быстрее)
write_client = client_router.write_client    # Всегда веб (write support)
default = client_router.default_client       # Умный выбор

# Выбор на основе операции
client = client_router.get_client_for_operation("search")  # -> local
client = client_router.get_client_for_operation("create")  # -> web
```

### 3. Режимы работы

- **local**: Только локальный API (read-only, быстрый)
- **web**: Только веб API (полная функциональность)
- **hybrid**: Оба клиента доступны (оптимальный режим)

## Конфигурация

### Локальный режим (Zotero 7+)

```bash
ZOTERO_LOCAL=true
ZOTERO_LIBRARY_ID=1  # Любое значение для локального
```

Требования:
- Zotero 7+ запущен
- Включено "Allow other applications on this computer to communicate with Zotero"
- Эндпоинт: `http://localhost:23119/api`

### Веб режим

```bash
ZOTERO_LOCAL=false
ZOTERO_LIBRARY_ID=your_library_id
ZOTERO_API_KEY=your_api_key
ZOTERO_LIBRARY_TYPE=user  # или 'group'
```

### Гибридный режим (рекомендуется)

```bash
ZOTERO_LOCAL=true
ZOTERO_LIBRARY_ID=your_library_id
ZOTERO_API_KEY=your_api_key
ZOTERO_LIBRARY_TYPE=user
```

- Read операции → локальный API (быстро, без rate limits)
- Write операции → веб API (полная функциональность)

## Защищенные методы (webonly)

Следующие методы `ZoteroClient` защищены декоратором `@webonly`:

- `create_items()` - создание элементов
- `create_collections()` - создание коллекций
- `update_item()` - обновление элемента
- `delete_item()` - удаление элемента
- `delete_item_by_key()` - удаление по ключу
- `delete_collection_by_key()` - удаление коллекции
- `add_to_collection()` - добавление в коллекцию

## Особенности локального API

### Поддерживается:
- ✅ Чтение элементов (items)
- ✅ Чтение коллекций (collections)
- ✅ Полнотекстовый поиск (fulltext) - с января 2025
- ✅ Saved searches
- ✅ Pagination не требуется

### Не поддерживается:
- ❌ Создание/обновление/удаление элементов
- ❌ Создание/обновление/удаление коллекций
- ❌ Доступ к file:// URLs (ограничения браузера)

## Примеры использования

### В MCP tools

```python
from src.client_router import client_router

@mcp.tool
async def search_articles(query: str):
    # Автоматически использует локальный API для чтения
    client = client_router.read_client
    items = client.items.all()
    return items

@mcp.tool
async def create_note(item_key: str, content: str):
    # Автоматически использует веб API для записи
    client = client_router.write_client
    await client.create_items([...])
```

### Проверка доступности

```python
if client_router.has_local_client:
    print("Локальный API доступен")

if client_router.has_web_client:
    print("Веб API доступен")

print(f"Режим: {client_router.mode}")
```

## Обработка ошибок

```python
from src.exceptions import WebOnlyOperationError

try:
    await local_client.create_items([...])
except WebOnlyOperationError as e:
    print(f"Операция требует веб API: {e.operation}")
    # Переключиться на веб клиент
    await web_client.create_items([...])
```

## Тестирование

Запуск тестов:

```bash
pytest tests/test_client_router.py -v
```

Все тесты проверяют:
- Работу декоратора `@webonly`
- Инициализацию роутера
- Выбор клиента для различных операций
- Приоритеты локального/веб клиентов

## Преимущества

1. **Производительность**: Локальный API быстрее (нет сетевых запросов)
2. **Надежность**: Нет rate limits для локального API
3. **Безопасность**: Write операции явно защищены декоратором
4. **Гибкость**: Автоматический fallback между клиентами
5. **Прозрачность**: Роутер работает незаметно для конечного пользователя
