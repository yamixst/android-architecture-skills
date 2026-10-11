---
name: android-architecture
description: Apply Google's official Android app architecture guidance (developer.android.com/topic/architecture) when writing, reviewing, or refactoring Android/Kotlin code. Covers layered architecture (UI, optional domain, data), unidirectional data flow, single source of truth, ViewModel and UiState design, state holders, UI events, repositories and data sources, use cases, offline-first sync, coroutines/Flow usage across layers, Hilt dependency injection, modularization, and testing with fakes. Use this skill whenever the task touches an Android codebase's structure — creating a screen, feature, ViewModel, repository, use case, DAO/data source, Hilt module, or Gradle module; deciding where logic or state belongs; fixing state/lifecycle bugs; reviewing a PR or auditing a project for architecture problems; or migrating legacy code (God Activities, AndroidViewModel, LiveData event wrappers, GlobalScope) — even if the user never says "architecture".
---

# Android architecture (Google guidelines)

This skill encodes the architecture Google recommends for Android apps. Use it to make
code land in the right layer, keep data flowing one way, and stay testable. The
recommendations come with priorities (Strongly recommended / Recommended / Optional);
treat "strongly recommended" items as the default and deviate only with a stated reason.

## How to use this skill

1. **Classify the task**: *build* (new screen/feature/class), *review/audit*
   (find violations), or *refactor/migrate* (move code toward the target shape).
2. **Inspect the project first** — toolkit (Compose vs Views), DI (Hilt/Koin/manual),
   navigation library, module layout, existing naming and result/error types. Follow
   the project's established conventions where they don't contradict the core rules
   below; consistency is part of good architecture.
3. **Apply the core rules and decision guides below.** This file is enough for most
   tasks. Open a reference only for the specific detail you're unsure about — usually
   one or two files, not all of them (e.g. `templates.md` when scaffolding a whole
   feature, `data-layer.md` §12 for offline sync design, `recommendations-checklist.md`
   for a formal review). See the index at the end.
4. **Self-check against "Red flags"** before finishing. For reviews, cite the
   recommendation IDs and priorities from `references/recommendations-checklist.md`.
5. Optionally run `python3 scripts/audit_architecture.py <project-or-module-dir>`
   for a fast heuristic scan (it reports candidates — confirm each by reading the code;
   it can't see design-level problems such as two sources of truth).

**Review/audit output:** for each finding give the location (`file:line`), what is
violated (recommendation ID + Google priority), the practical impact (your severity:
does it cause bugs, block the planned work, or just add debt?), and a concrete fix.
Then sketch the target shape and an incremental migration order. Also report real
bugs you notice on the way, even if they aren't architectural.

## Core principles

- **Separation of concerns.** Activities/Fragments/composables only display UI and
  forward user input. Don't store app data or state in app components (the OS
  destroys them at will) and keep Android framework classes (`Context`, `Toast`,
  `Resources`) in the UI layer.
- **Drive UI from data models**, preferably persistent ones (survive process death,
  work offline).
- **Single source of truth (SSOT).** Each data type has one owner that alone mutates
  it, exposes it as an immutable type, and offers functions/accepts events to change it.
  Offline-first: the local database is the SSOT.
- **Unidirectional data flow (UDF).** State flows down (data → repository → ViewModel →
  UI); events flow up (UI → ViewModel → repository). The UI never changes state
  directly — it calls the state owner.
- **Adaptive.** Handle configuration changes and window size changes; preserve UI state
  across them.

## The layers and dependency direction

```
UI layer        Composables / Activity / Fragment  ──►  State holders (screen ViewModel, plain UI-state classes)
                                                                   │  StateFlow<UiState> down, function calls up
Domain layer    (optional) Use cases: GetXUseCase ─────────────────┤
                                                                   ▼
Data layer      Repositories (public entry point, SSOT, business logic) ──► Data sources (one source each:
                                                                             Room DAO, DataStore, API, WorkManager, system provider)
```

Dependencies point **downward only**. Nothing below the UI knows about the UI.
ViewModels and use cases talk to **repositories**, never to data sources, DAOs, API
clients, `SharedPreferences`, Firebase, location/Bluetooth/connectivity providers.

## Core rules (the condensed checklist)

**UI layer**
- Screen UI state is an **immutable** `XUiState` (data class, or sealed interface for
  exclusive states) containing everything needed to render.
- One **screen-level ViewModel** per destination; expose `val uiState: StateFlow<XUiState>`.
  Build it with `stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), initial)`
  when it comes from streams; otherwise private `MutableStateFlow` + `asStateFlow()` and
  `update {}`.
- ViewModels hold **no** `Context`, `Activity`, `Fragment`, `Resources`, `View`,
  `NavController` or other lifecycle-bound types. Don't use `AndroidViewModel`.
- UI collects with `collectAsStateWithLifecycle()` (Compose) or `repeatOnLifecycle`
  (Views).
- **Don't send one-off events from the ViewModel to the UI** (no `Channel`/`SharedFlow`/
  `SingleLiveEvent` for navigation, toasts, snackbars). Handle the event in the
  ViewModel, put the outcome in UI state; the UI reacts and reports back when consumed
  (e.g. `userMessageShown()`).
- Business logic → ViewModel delegating to repositories/use cases. UI logic (strings
  from resources, navigation, snackbar display, scroll, animation) → the UI or a plain
  `@Stable` state-holder class created with `remember…()`.
- Only the route/entry composable knows the ViewModel; stateless screen composables and
  reusable components get **state + lambdas** (`onItemClick: (Id) -> Unit`). Never pass
  a ViewModel down.
- Single-activity app; Compose for new UI; Navigation 3 for multi-screen navigation;
  pass **IDs** between destinations, not objects.
- Don't override `Activity` lifecycle callbacks for UI work: `LifecycleStartEffect`,
  `LifecycleResumeEffect`, `repeatOnLifecycle`.

**Data layer**
- A **repository per data type** (even with a single data source); it is the only entry
  point. Data sources wrap exactly one source.
- Expose `suspend fun` for one-shot operations and `Flow` for streams; exposed data is
  **immutable**; map DTOs/entities to external models inside the layer.
- Everything is **main-safe**: the class doing blocking work switches dispatcher itself,
  using an **injected** `CoroutineDispatcher`.
- Operation lifetime: screen-bound → caller's scope; must finish while app is alive →
  injected app-scoped `CoroutineScope`; must survive process death → WorkManager.
- Errors: exceptions (rethrow `CancellationException`) or the project's typed result;
  ViewModel maps them to UI state.

**Domain layer (optional)**
- Add use cases only for business logic that is **reused** by several ViewModels or is
  **complex**. One action per use case, `operator fun invoke`, stateless, main-safe,
  depends on repositories/other use cases. Name: `VerbNounUseCase`.

**Cross-cutting**
- Coroutines + Flow between layers; no `GlobalScope`; no hardcoded dispatchers; don't
  expose mutable types; the ViewModel creates coroutines, data/domain expose `suspend`/`Flow`.
- **Constructor injection** (Hilt recommended). Scope a binding only when it holds
  shared mutable state or is expensive and widely used.
- Tests: ViewModels (incl. flows) and repositories/data sources at minimum; **fakes over
  mocks**; assert on `StateFlow.value`.

## Decision guides

**Where does this logic go?**
- Does it implement a product rule about app data (validate, compute price, decide
  eligibility, bookmark, sync)? → *business logic* → repository (or use case if reused/
  complex), invoked by the ViewModel.
- Is it about *how* to show something (which string, which layout for this window size,
  navigate, show snackbar, scroll)? → *UI logic* → composable or plain state holder.
- Needs `Context`/`Resources`? → it's UI logic (resolve in UI) or a system data source
  (wrap in a data source behind a repository). It does not belong in a ViewModel.

**ViewModel or plain state holder?**
Business logic or must survive configuration change / live as long as the destination
→ ViewModel at screen level. UI-element state and UI logic, reusable component → plain
class + `remember…()`. Hoist state to the lowest common ancestor of its readers/writers.

**How do I handle this event?**
1. UI-only state change (expand, toggle visibility) → handle in the UI.
2. Needs business logic → call a ViewModel function → state update.
3. Plain navigation from a click → hoisted lambda to whoever owns navigation.
4. Outcome produced in the ViewModel (login succeeded, error) → field in UI state → UI
   reacts (e.g. `LaunchedEffect(uiState.isLoggedIn)`) and calls back if it's consumable.

**Do I need a use case?** Only if the logic is reused across ViewModels, combines
several repositories non-trivially, or makes a ViewModel too complex. A use case that
only forwards one repository call is noise.

**Which persistence?** Queryable/relational/partial updates → Room. Small key-value or
typed settings → DataStore. Blobs/JSON → file. Always behind a data source named
by data + Local/Remote, not by technology.

**Which write strategy (offline-first)?** Must be online (payments) → online-only.
Non-critical (analytics) → queued. User data that must not be lost → lazy (local first,
then sync via WorkManager).

**Modularize?** Small app → packages (`ui`, `domain`, `data`) are fine. Growing app/
multiple teams/form factors → `:app`, `:feature:x:api|impl`, `:core:data`,
`:core:database`, `:core:network`, `:core:model`, `:core:domain`, `:core:ui`,
`:core:testing`. Feature impls never depend on other feature impls.

## Canonical shape (Compose + Hilt)

```kotlin
data class NewsUiState(                                   // immutable, everything to render
    val items: List<NewsItemUiState> = emptyList(),
    val isLoading: Boolean = true,
    val userMessage: UserMessage? = null,
)

@HiltViewModel
class NewsViewModel @Inject constructor(
    private val newsRepository: NewsRepository,           // repository, not a DAO/API
) : ViewModel() {
    private val userMessage = MutableStateFlow<UserMessage?>(null)

    val uiState: StateFlow<NewsUiState> = combine(
        newsRepository.getNewsStream(), userMessage,
    ) { news, message -> NewsUiState(news.map { it.asUiState() }, isLoading = false, userMessage = message) }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), NewsUiState())

    fun toggleBookmark(id: String, bookmarked: Boolean) {  // event in, state out
        viewModelScope.launch {
            try { newsRepository.setBookmarked(id, bookmarked) }
            catch (e: IOException) { userMessage.value = UserMessage.BookmarkFailed }
        }
    }
    fun userMessageShown() { userMessage.value = null }
}

@Composable
fun NewsRoute(onOpenArticle: (String) -> Unit, viewModel: NewsViewModel = hiltViewModel()) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    NewsScreen(uiState, onOpenArticle, viewModel::toggleBookmark, viewModel::userMessageShown)
}
```
A full slice (entities, DTOs, data sources, offline-first repository, Hilt module,
navigation entry, worker, fake, ViewModel tests) is in `references/templates.md`.

## Red flags (check before finishing; each has a fix in the references)

- ViewModel/composable depends on `*Dao`, `*Api`/`*Service`, `Retrofit`, `HttpClient`,
  `SharedPreferences`, `DataStore`, `FirebaseFirestore`, `LocationManager`.
- `Context`/`Activity`/`Resources`/`View` in a ViewModel; `AndroidViewModel`.
- Public `MutableStateFlow`/`MutableLiveData`; multiple loose flags that should be one
  `UiState`; UI mutating state objects.
- `Channel`/`SharedFlow`/`SingleLiveEvent`/`Event<T>` wrapper used for navigation or
  toasts from the ViewModel.
- `collectAsState()` on ViewModel flows; `lifecycleScope.launch { flow.collect }` without
  `repeatOnLifecycle`; overriding `onResume`/`onStart` for UI work.
- ViewModel passed into child composables, list items, adapters or plain state holders.
- `GlobalScope`, `runBlocking`, hardcoded `Dispatchers.IO` in classes, ad-hoc
  `CoroutineScope(...)` inside repositories, catching `Exception` without rethrowing
  `CancellationException`.
- Network DTOs or Room entities reaching the UI; network result shown while the DB holds
  the same data (two sources of truth).
- Business logic in composables/Activities/Fragments; UI logic (string formatting with
  resources, navigation) in the ViewModel.
- Objects passed as navigation arguments instead of IDs; feature module depending on
  another feature's implementation.
- `PagingData` stored inside `UiState`.
- Mocks where a simple fake would do; ViewModels/repositories without tests.

## Pragmatism

- These are guidelines, not laws: Google states they "aren't mandatory" but make code
  more robust, testable and maintainable. Scale ceremony to the app: no domain layer or
  multi-module setup for a small app; a repository is still worth it.
- In an existing codebase, change architecture **incrementally** and in scope. Don't
  rewrite LiveData → Flow, Views → Compose, or Koin → Hilt as a side effect of an
  unrelated task; mention it as a follow-up instead.
- When you deviate from a strongly-recommended item, say why in the code review or
  summary.

## Reference index (load on demand)

| File | Read when |
|---|---|
| `references/ui-layer.md` | UiState design, state holders, state production APIs, `stateIn` policies, UI events & navigation via state, loading/errors/messages, hoisting, Compose lifecycle effects, Paging, adaptive |
| `references/data-layer.md` | Repositories, data sources, SSOT, threading, scoping, models/mapping, operation lifetimes, errors, Room/DataStore/file choice, caching, WorkManager, **offline-first** reads/writes/sync/conflicts |
| `references/domain-layer.md` | Deciding on and writing use cases |
| `references/coroutines-and-flows.md` | Dispatchers, scopes, exceptions/cancellation, Flow operators, testing coroutines |
| `references/dependency-injection.md` | Hilt modules, scopes/components table, qualifiers, app scope, ViewModels with Nav3, workers, test bindings |
| `references/modularization.md` | Module types, feature api/impl split, inter-module communication, dependency inversion, Gradle hygiene |
| `references/testing.md` | What to test, fakes, ViewModel/StateFlow tests, data and UI tests, test pyramid |
| `references/views.md` | Project uses Views/Fragments instead of Compose |
| `references/templates.md` | Scaffolding a new feature end-to-end |
| `references/recommendations-checklist.md` | Reviews/audits: every official recommendation with ID and priority |
| `references/sources.md` | Source URLs (fetch the live page if a detail must be verified) |
