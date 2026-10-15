# android-architecture-skills

Agent skill that makes coding agents follow Google's official Android app architecture
guidance ([developer.android.com/topic/architecture](https://developer.android.com/topic/architecture)).

## What's inside

```
skills/android-architecture/
├── SKILL.md                       core principles, layer rules, decision guides, red flags
├── references/
│   ├── ui-layer.md                UiState, state holders, state production, events, Compose
│   ├── data-layer.md              repositories, data sources, SSOT, threading, offline-first
│   ├── domain-layer.md            when and how to write use cases
│   ├── coroutines-and-flows.md    dispatchers, scopes, cancellation, Flow, coroutine tests
│   ├── dependency-injection.md    Hilt components/scopes, qualifiers, Nav3 ViewModels
│   ├── modularization.md          module types, feature api/impl, dependency inversion
│   ├── testing.md                 what to test, fakes, StateFlow tests
│   ├── views.md                   differences for Views/Fragments projects
│   ├── templates.md               complete feature slice (data → UI → DI → tests)
│   ├── recommendations-checklist.md  every official recommendation with ID + priority
│   └── sources.md                 scraped pages and dates
├── scripts/audit_architecture.py  heuristic scanner for common violations (stdlib only)
└── evals/                         3 test cases (review, build, refactor)
```

Source pages were collected with the Firecrawl CLI on 2026-10-26.

## Install

Claude Code (project): symlink or copy the folder into `.claude/skills/`:
```bash
ln -s ../../skills/android-architecture .claude/skills/android-architecture
```
Other agents that read `.agents/skills/` (Codex, etc.): same into `.agents/skills/`.
Both links already exist in this repository.

Run the scanner on any Android project:
```bash
python3 skills/android-architecture/scripts/audit_architecture.py path/to/project [--format json] [--min-severity medium]
```

## Evaluation (iteration 1)

Three tasks, each run with and without the skill; pass rate = share of checks passed.

| Model | With skill | Without skill | Token overhead |
|---|---|---|---|
| Opus 5.5 | 100% | 100% | +43% |
| Haiku | 100% | 84% | +47% |

Without the skill, Haiku kept a ViewModel → UI `Channel` for events (contrary to the
strongly-recommended rule), used `SharingStarted.Eagerly`, synced offline follow taps
only when the screen reopened (no WorkManager), and missed `collectAsState()` in review.
Opus already knows the guidance; with the skill its reviews cite the official
recommendation IDs/priorities. Results and HTML viewers:
`skills/android-architecture-workspace/iteration-1*/` (gitignored).

## License

Apache License 2.0, see [LICENSE](LICENSE).

The guidance in `skills/android-architecture/` is adapted from
[Android Developers](https://developer.android.com/topic/architecture) documentation,
© Google LLC, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
(code samples under Apache 2.0). See [NOTICE](NOTICE). This project is not affiliated
with or endorsed by Google.
