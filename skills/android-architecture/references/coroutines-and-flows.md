# Coroutines and Flows across layers — detailed rules

Source: developer.android.com/kotlin/coroutines/coroutines-best-practices,
…/topic/libraries/architecture/coroutines, …/recommendations.

Coroutines and Flows are **the** way layers communicate (strongly recommended).

## Contract between layers

| Layer | Exposes | Creates coroutines? |
|---|---|---|
| Data (repositories, data sources) | `suspend fun` for one-shot, `Flow<T>` for change streams | Only for app-scoped work, in an **injected** external scope |
| Domain (use cases) | `suspend operator fun invoke` or `operator fun invoke(): Flow<T>` | Only `coroutineScope {}`/`supervisorScope {}` for parallel decomposition |
| ViewModel | `StateFlow<UiState>` + plain (non-suspend) functions for events | **Yes** — launches in `viewModelScope` |
| UI | — | Only UI-logic coroutines (`rememberCoroutineScope`, `LaunchedEffect`) — never business logic |

## Rules

1. **Inject dispatchers.** Never hardcode `Dispatchers.IO/Default` inside classes;
   take a `CoroutineDispatcher` constructor parameter. Tests pass a `TestDispatcher`.
2. **Suspend functions are main-safe.** The class doing blocking work moves it with
   `withContext(dispatcher)`. Callers never need to choose a dispatcher.
   Don't re-wrap already main-safe calls (Room/Retrofit/Ktor suspend APIs).
3. **The ViewModel creates coroutines** (`viewModelScope.launch`) rather than exposing
   `suspend` functions to the UI. Expose results as observable state. Views/composables
   don't launch coroutines for business logic.
4. **Don't expose mutable types.** `private val _uiState = MutableStateFlow(…)`;
   `val uiState: StateFlow<…> = _uiState.asStateFlow()`.
5. **Data/domain layers expose `suspend` and `Flow`** so the caller controls lifecycle and
   cancellation.
6. **Work that must outlive the screen**: `externalScope.launch { … }.join()` /
   `externalScope.async { … }.await()` with an injected app-scoped `CoroutineScope`
   (created by a class that lives longer — `Application`/DI singleton, or a ViewModel
   scoped to a navigation graph). Work that must survive process death → WorkManager.
7. **Avoid `GlobalScope`** (hardcoded scope, untestable). Also avoid creating ad-hoc
   `CoroutineScope(Dispatchers.IO)` inside classes — same problems, plus leaks.
8. **Make coroutines cancellable**: in loops of blocking work call `ensureActive()`
   (or `yield()`); prefer cancellable suspend APIs.
9. **Watch out for exceptions**: catch likely exceptions inside coroutines launched in
   `viewModelScope`/`lifecycleScope` and map them to UI state; unhandled exceptions
   crash the app. **Never swallow `CancellationException`** — rethrow it if you catch
   `Exception`/`Throwable`. Prefer catching specific exceptions (`IOException`,
   `HttpException`, domain exceptions).
10. **Don't use `runBlocking`** in production code paths on the main thread.

## Flow specifics

- Cold `Flow` from data layer → hot `StateFlow` in ViewModel via
  `stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), initialValue)`.
- Use `combine` to merge several streams into one UI state; `flatMapLatest` when a
  stream depends on another value (e.g. a query from `SavedStateHandle.getStateFlow`).
- Use `catch {}` for upstream errors, `onStart {}` for loading emissions,
  `distinctUntilChanged()` to avoid redundant emissions,
  `map`/`mapLatest` for transforms.
- `shareIn`/`stateIn` in repositories only with an injected external scope and when
  multiple collectors must share one upstream (e.g. a location stream).
- Collect from UI with lifecycle awareness: `collectAsStateWithLifecycle()` (Compose),
  `repeatOnLifecycle(Lifecycle.State.STARTED)` (Views). Never `lifecycleScope.launch {
  flow.collect {} }` without `repeatOnLifecycle` — it keeps collecting in the background.
- Prefer `StateFlow` over `LiveData` in new code; don't use `LiveData` below the UI
  layer.
- Avoid `SharedFlow`/`Channel` as a ViewModel → UI event bus (see ui-layer.md §7).
  Channels/SharedFlows are fine *inside* the data layer for genuine event streams.

## Testing coroutines

- `runTest { }` for coroutine tests (skips delays, virtual time).
- Inject `StandardTestDispatcher(testScheduler)` or `UnconfinedTestDispatcher(testScheduler)`;
  all test dispatchers must share one scheduler.
- For `viewModelScope` (uses `Dispatchers.Main`), set `Dispatchers.setMain(testDispatcher)`
  in a JUnit rule (`MainDispatcherRule`) and reset after.
- Testing `StateFlow` built with `stateIn(WhileSubscribed)`: start a collector in
  `backgroundScope` (`backgroundScope.launch(UnconfinedTestDispatcher()) { vm.uiState.collect() }`)
  and **assert on `uiState.value`**. Turbine is an acceptable alternative for flows
  with multiple emissions.

```kotlin
class MainDispatcherRule(
    val testDispatcher: TestDispatcher = UnconfinedTestDispatcher(),
) : TestWatcher() {
    override fun starting(description: Description) = Dispatchers.setMain(testDispatcher)
    override fun finished(description: Description) = Dispatchers.resetMain()
}
```
