---
tags: [skill-creator]
max_turns: 25
timeout_seconds: 900
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit, Bash]
---

у нас логин сделан через Channel с событиями (навигация + снекбар), на ревью сказали что это против гайдлайнов гугла. перепиши LoginViewModel.kt и LoginScreen.kt как положено, AuthRepository не трогай (suspend fun login(email, password), кидает исключение при ошибке). и коротко объясни в CHANGES.md что поменял и почему

Input files: LoginViewModel.kt, LoginScreen.kt
