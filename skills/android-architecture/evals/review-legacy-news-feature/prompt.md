---
tags: [skill-creator]
max_turns: 30
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

Check out the news feature in app/src/main/java/com/example/news. It's old code, and we want to bring it in line with Google's Android app architecture guide before adding offline support. Do a review covering what's broken/violating the guidelines, its severity, and how to fix it. Put the results in review.md without modifying any code for now.

Input files: app/src/main/java/com/example/news/NewsViewModel.kt, app/src/main/java/com/example/news/NewsScreen.kt, app/src/main/java/com/example/news/Data.kt, app/src/main/java/com/example/news/MainActivity.kt
