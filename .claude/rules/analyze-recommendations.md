---
description: Guidelines for /analyze skill recommendations
---

# Analyze recommendations

When ranking solutions in `/analyze` reports:

- Prefer **root-cause fixes** over defensive workarounds
- "Single point of change" is a pro, but "masks the bug instead of fixing it" is a stronger con
- A fix that changes 3 files but eliminates the bug is better than a 1-file fix that hides it in serialization
