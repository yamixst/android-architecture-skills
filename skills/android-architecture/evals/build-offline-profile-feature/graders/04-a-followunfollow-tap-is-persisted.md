---
type: llm
focus: trace
weight: 1
---

A follow/unfollow tap is persisted locally first and synced later via WorkManager (or an equivalent persistent queue) so it is not lost offline
