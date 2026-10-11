---
tags: [skill-creator]
max_turns: 40
timeout_seconds: 1200
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

We're adding a user profile screen to our Android app (Kotlin, Jetpack Compose, Hilt, Room, Retrofit, Navigation 3). The screen shows the user's display name, avatar and follower count from GET /users/{id}, and has a Follow/Unfollow button (POST /users/{id}/follow, DELETE to unfollow). It has to keep working offline — show whatever we last had and not lose the user's follow tap if they're offline. Other screens open it with a user id.

Write the Kotlin source for this feature (data layer, UI layer, DI module, and unit tests for the ViewModel and repository) as files under a profile/ folder. Don't bother with Gradle files or a full project — just the sources.
