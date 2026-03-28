---
globs: ["yazot/**/*.py"]
---
# Concurrency patterns

- `ZoteroClient._call` and `Collection._call` wrap all pyzotero calls with an optional `asyncio.Semaphore`
- Semaphore is created in `ZoteroClient.__init__` only for web mode (`Settings.web_zotero_max_concurrent_requests`)
- Local mode: semaphore is `None`, no rate limiting
- All `Collection` instances receive the semaphore from `ZoteroClient` — rate limit is global per client
- When adding new parallel operations: do NOT create local semaphores — rely on the client-level one in `_call`
