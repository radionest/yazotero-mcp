---
globs: ["yazot/**/*.py"]
---
# Concurrency patterns

- **Non-paginated calls**: `ZoteroClient._call` and `Collection._call` wrap pyzotero calls with semaphore + `asyncio.to_thread` using a shared client
- **Paginated calls**: `_fetch_all_paginated()` uses an isolated pyzotero client (via `_make_client()`) and acquires the semaphore per page, not per pagination sequence. This avoids thread pool exhaustion and shared mutable state (`self.links`, `self.url_params`) races
- Semaphore is created in `ZoteroClient.__init__` only for web mode (`Settings.web_zotero_max_concurrent_requests`)
- Local mode: semaphore is `None`, no rate limiting
- All `Collection` instances receive the semaphore and `_make_client` factory from `ZoteroClient` — rate limit is global per client
- When adding new parallel operations: do NOT create local semaphores — use `_fetch_all_paginated()` for paginated calls, `_call()` for single calls
