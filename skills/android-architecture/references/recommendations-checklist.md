# Google's official architecture recommendations — complete checklist

Faithful condensation of developer.android.com/topic/architecture/recommendations
(Compose version, page dated 2026) with the Views-page differences noted. Use this as
the authoritative checklist for code reviews and audits. Priorities are Google's:

- **SR — Strongly recommended:** implement unless it fundamentally clashes with your approach.
- **R — Recommended:** likely to improve the app.
- **O — Optional:** can improve the app in certain circumstances.

When reporting a violation, cite the item ID (e.g. `[VM-1]`) and its priority.

## Layered architecture

| ID | Pri | Recommendation | Details |
|---|---|---|---|
| LA-1 | SR | Use a clearly defined data layer | Exposes app data and contains the vast majority of business logic. Create repositories even with a single data source. Small apps: `data` package/module is fine |
| LA-2 | SR | Use a clearly defined UI layer | Displays data, primary point of interaction. Compose is the recommended toolkit. Small apps: `ui` package/module |
| LA-3 | SR | Expose application data from the data layer using a repository | Composables and ViewModels must not interact directly with a data source (databases, DataStore, SharedPreferences, Firebase APIs, GPS/location providers, Bluetooth providers, network-connectivity providers) |
| LA-4 | SR | Use coroutines and flows | To communicate between layers |
| LA-5 | R (big apps) | Use a domain layer | Use cases when business logic interacting with the data layer is reused across multiple ViewModels, or to simplify a complex ViewModel |

## UI layer

| ID | Pri | Recommendation | Details |
|---|---|---|---|
| UI-1 | SR | Follow Unidirectional Data Flow | ViewModels expose UI state via the observer pattern and receive actions from the UI through method calls |
| UI-2 | SR | Use AAC ViewModels if their benefits apply | To handle business logic and fetch app data to expose UI state |
| UI-3 | SR | Use lifecycle-aware UI state collection | `collectAsStateWithLifecycle` (Compose); `repeatOnLifecycle` (Views) |
| UI-4 | SR | Do not send events from the ViewModel to the UI | Process the event immediately in the ViewModel and update state with the result |
| UI-5 | SR (Views page: R) | Use a single-activity application | Navigation 3 (Compose) / Navigation with Fragments (Views) for multiple screens and deep links |
| UI-6 | SR | Use Jetpack Compose | For new apps on phones, tablets, foldables, Wear OS |

## ViewModel

| ID | Pri | Recommendation | Details |
|---|---|---|---|
| VM-1 | SR | Keep ViewModels independent of the Android lifecycle | No references to lifecycle-related types; don't pass `Activity`, `Fragment`, `Context`, `Resources` as dependencies. If something needs a `Context` in the ViewModel, re-evaluate the layer |
| VM-2 | SR | Use coroutines and flows | Receive app data via Kotlin flows; perform actions with `suspend` functions launched in `viewModelScope` |
| VM-3 | SR | Use ViewModels at screen level | Not in reusable UI. Use in screen-level composables, navigation destinations/graphs (Views: Activities/Fragments). For complex composables with dynamic behavior, `rememberViewModelStoreOwner()` scopes a ViewModel to the call site |
| VM-4 | SR | Use plain state holder classes in reusable UI components | So state can be hoisted and controlled externally |
| VM-5 | R (Views page: SR) | Do not use `AndroidViewModel` | Use `ViewModel`; don't use `Application` in the ViewModel — move the dependency to the UI or data layer |
| VM-6 | R | Expose a UI state | Single `uiState` property (multiple only for unrelated data); make it a `StateFlow`; build with `stateIn(… WhileSubscribed(5000) …)` when data comes as a stream; `MutableStateFlow` exposed as `StateFlow` acceptable for simple cases; `${Screen}UiState` data class with data/errors/loading, or sealed class when states are exclusive |

## Lifecycle

| ID | Pri | Recommendation | Details |
|---|---|---|---|
| LC-1 | SR | Use lifecycle-aware effects in composables instead of overriding `Activity` lifecycle callbacks | `LifecycleStartEffect` (sync start/stop), `LifecycleResumeEffect` (sync resume/pause), `repeatOnLifecycle` (async), `collectAsStateWithLifecycle` (flows). Views: `DefaultLifecycleObserver` / `repeatOnLifecycle`, don't override `onResume` etc. |

## Handle dependencies

| ID | Pri | Recommendation | Details |
|---|---|---|---|
| DI-1 | SR | Use dependency injection | Mainly constructor injection when possible |
| DI-2 | SR | Scope to a component when necessary | When the type holds mutable data that must be shared, or is expensive to initialize and widely used |
| DI-3 | R | Use Hilt | Hilt or manual DI in simple apps; Hilt when the project has multiple screens with ViewModels, WorkManager, or ViewModels scoped to the navigation back stack |

## Testing

| ID | Pri | Recommendation | Details |
|---|---|---|---|
| T-1 | SR | Know what to test | At minimum: unit tests for ViewModels (incl. Flows); unit tests for repositories and data sources; UI navigation tests for CI regression; Macrobenchmark performance tests (startup, rendering) |
| T-2 | SR | Prefer fakes to mocks | |
| T-3 | SR | Test StateFlows | Assert on `value` whenever possible; use `WhileSubscribed` |

## Performance

| ID | Pri | Recommendation | Details |
|---|---|---|---|
| P-1 | SR | Use R8 to shrink and optimize | Full mode in release builds |
| P-2 | SR | Implement Baseline Profiles and Startup Profiles | Pre-compile critical paths; reduces TTID/TTFD, jank, ANRs |
| P-3 | SR | Test performance with Macrobenchmark | Prevent regressions |

## Models

| ID | Pri | Recommendation | Details |
|---|---|---|---|
| M-1 | R | Create a model per layer in complex apps | Remote data source maps network model to a simpler class; repositories map DAO models to what the UI needs; ViewModels may wrap data models in `UiState` |

## Naming conventions

| ID | Pri | Recommendation | Details |
|---|---|---|---|
| N-1 | O | Methods are verb phrases | `makePayment()` |
| N-2 | O | Properties are noun phrases | `inProgressTopicSelection` |
| N-3 | O | Streams: `get{Model}Stream()` | `getAuthorStream(): Flow<Author>`, `getAuthorsStream(): Flow<List<Author>>` |
| N-4 | O | Interface implementations have meaningful names | `OfflineFirstNewsRepository`, `InMemoryNewsRepository`; fall back to `DefaultNewsRepository`; fakes `FakeAuthorsRepository` |

## General best practices (from the Guide to app architecture — not prioritized, "not mandatory but in most cases make the codebase more robust")

| ID | Practice |
|---|---|
| G-1 | Don't store data in app components (activities, services, receivers are short-lived entry points) |
| G-2 | Reduce dependencies on Android classes — only app components use `Context`, `Toast`, etc. |
| G-3 | Define clear boundaries of responsibility between modules (don't spread networking across classes; don't mix caching and binding in one class) |
| G-4 | Expose as little as possible from each module |
| G-5 | Focus on the unique core of the app; let Jetpack handle boilerplate |
| G-6 | Use canonical layouts and app design patterns (adaptive) |
| G-7 | Preserve UI state across configuration changes (resize, fold, rotation) |
| G-8 | Design reusable and composable UI components |
| G-9 | Make each part testable in isolation |
| G-10 | Types are responsible for their concurrency policy (main-safe) |
| G-11 | Persist as much relevant and fresh data as possible (offline) |

## Additional rules from the layer guides (not in the table, but stated as rules)

| ID | Rule | Source |
|---|---|---|
| X-1 | Other layers never access data sources directly; repositories are the entry point | data layer |
| X-2 | Data exposed by the data layer is immutable | data layer |
| X-3 | Each repository defines a single source of truth; offline-first → local DB is the SSOT | data layer |
| X-4 | Repositories and data sources are main-safe | data layer |
| X-5 | Business-oriented operations that must survive process death → WorkManager; app-oriented → injected external scope | data layer |
| X-6 | Business logic is never in the UI; UI logic stays in the UI (not in the ViewModel when it needs `Context`) | UI layer |
| X-7 | UI state is immutable; UI never mutates it directly unless it's the sole source | UI layer |
| X-8 | Business logic is applied before UI logic in the state production pipeline | state holders |
| X-9 | State holders depend only on holders of equal or shorter lifetime; don't pass ViewModels to plain state holders or reusable composables | state holders |
| X-10 | `PagingData` exposed in its own stream, not inside UiState | UI layer |
| X-11 | Pass IDs (not objects) between screens/features | modularization |
| X-12 | Use cases: single responsibility, no mutable data, main-safe | domain layer |
| X-13 | Inject dispatchers; avoid `GlobalScope`; ViewModel creates coroutines; don't expose mutable types | coroutines best practices |
| X-14 | Don't swallow `CancellationException` when catching exceptions in coroutines | state production samples |
