# UI layer — detailed rules

Source: developer.android.com/topic/architecture/ui-layer, …/ui-layer/stateholders,
…/ui-layer/state-production, …/ui-layer/events, …/develop/ui/compose/architecture,
…/develop/ui/compose/state-hoisting.

## Contents
1. What the UI layer is
2. UI state: definition, immutability, naming
3. Types of logic and where each lives
4. State holders: ViewModel vs plain class
5. Producing UI state (pipelines, APIs, stateIn)
6. Exposing and consuming UI state
7. UI events (user events, ViewModel events, navigation)
8. Loading, errors, user messages
9. Lifecycle-aware work in Compose
10. Paging, navigation, adaptive UI
11. Common mistakes

---

## 1. What the UI layer is

The UI layer is the pipeline that converts application data into something the UI can
render, renders it, and feeds user input back. It does four things in a loop:

1. Consume app data and transform it into UI-renderable data (UI state).
2. Turn UI state into UI elements.
3. Consume user input events and reflect their effects in the UI state.
4. Repeat.

It consists of **UI elements** (composables; or Views/Fragments in legacy code) and
**state holders** (ViewModel or plain classes) that hold data, expose it and handle logic.

Jetpack Compose is the recommended toolkit. Use a **single-activity** app; the one
`Activity` hosts Compose destinations, navigated with Navigation 3.

## 2. UI state

*If the UI is what the user sees, the UI state is what the app says they should see.*

Two kinds:
- **Screen UI state** — *what* to display (articles, user name, flags). Comes from app
  data, produced by business logic, usually lives in a ViewModel.
- **UI element state** — properties intrinsic to an element (scroll position, drawer
  open, expanded). Hoisted into the caller or a plain state holder (`LazyListState`,
  `DrawerState`, `ScaffoldState`).

Rules:
- **Immutable.** Model screen state as a `data class` with `val`s (or a `sealed interface`
  when states are mutually exclusive). Immutability gives a consistent snapshot in time.
- **Never mutate UI state in the UI** unless the UI is the sole source of that data. If a
  composable flips `item.bookmarked`, it now competes with the data layer as a source of
  truth → inconsistency bugs. Send an event instead.
- **Naming:** `functionality + UiState` — `NewsUiState`, `NewsItemUiState`,
  `AuthorScreenUiState`.
- **Derived values** can be computed properties on the state:
  `val NewsUiState.canBookmarkNews get() = isSignedIn && isPremium`.
- **Contain everything needed to render.** The UI should not reach into repositories to
  fill gaps.

```kotlin
data class NewsUiState(
    val isSignedIn: Boolean = false,
    val isPremium: Boolean = false,
    val newsItems: List<NewsItemUiState> = emptyList(),
    val userMessages: List<Message> = emptyList(),
)

// Mutually exclusive states → sealed interface
sealed interface AuthorUiState {
    data object Loading : AuthorUiState
    data class Success(val author: Author) : AuthorUiState
    data object Error : AuthorUiState
}
```

## 3. Types of logic

| Logic | What it is | Examples | Where it lives |
|---|---|---|---|
| **Business logic** | Implementation of product requirements for app data — *what to do* with state changes | bookmark an article, make a payment, validate a date of birth, store a preference | Data layer (repositories) or domain layer (use cases). The ViewModel *delegates* to them. **Never in composables.** |
| **UI logic / UI behavior logic** | *How* to display state changes | pick a string from `Resources`, navigate on click, show a snackbar/toast, scroll to an item, choose nav rail vs bottom bar | The UI itself, or a plain-class UI state holder. **Not in the ViewModel**, especially when it needs `Context`/`Resources`. |

Ordering rule: **business logic is always applied before UI logic** in the production
pipeline. Business logic must never depend on UI logic.

Lifecycle split:

| UI-lifecycle independent | UI-lifecycle dependent |
|---|---|
| Business logic, screen UI state | UI logic (permissions, localized strings, configuration-dependent resources) |

## 4. State holders

A state holder produces UI state and contains the logic needed for it. Every UI element
has a 1:1 relationship with its state holder, and the state holder must accept any user
action that can change that UI state.

### Business-logic state holder → `ViewModel`
Properties:
- Produces screen UI state from data/domain layer + user events.
- Retained across `Activity` recreation (configuration changes).
- Long-lived: kept while the destination is on the back stack; cleared when popped.
- Unique to its screen, not reusable (`TaskEditViewModel`, `TaskListViewModel`). The
  *same* ViewModel can serve phone/tablet/TV variants of that screen.
- After process death it must be able to rebuild its last state: keep the *minimum*
  (IDs, user input) in `SavedStateHandle` and reload the rest from the data layer.

Use ViewModels **at screen level only**: screen-level composables, navigation
destinations/graphs. For complex composables that need their own scope, use
`rememberViewModelStoreOwner()` to scope a ViewModel to the call site.
Do **not** use ViewModels in reusable UI components.

### UI-logic state holder → plain class
Properties:
- Manages UI element state and UI logic.
- Does **not** survive recreation (it may reference UI-scoped things like `Resources`,
  `NavHostController`, `WindowSizeClass`). Persist what's needed through
  `rememberSaveable`.
- Reusable across screens.
- Created with a `remember…` function, annotated `@Stable`.

```kotlin
@Stable
class AppState(
    val windowSizeClass: WindowSizeClass,
    private val drawerState: DrawerState,
) {
    val shouldShowBottomBar: Boolean            // UI logic
        get() = !windowSizeClass.isWidthAtLeastBreakpoint(WindowSizeClass.WIDTH_DP_MEDIUM_LOWER_BOUND)
}

@Composable
fun rememberAppState(
    windowSizeClass: WindowSizeClass = currentWindowAdaptiveInfo().windowSizeClass,
    drawerState: DrawerState = rememberDrawerState(DrawerValue.Closed),
): AppState = remember(windowSizeClass, drawerState) { AppState(windowSizeClass, drawerState) }
```

### Choosing
- Need business logic and state that outlives configuration changes / lives as long as
  the destination → `ViewModel`.
- Short-lived UI state and UI logic only → plain class (or just `remember` in the
  composable for trivial cases).
- **Hold state as low as possible while keeping proper ownership** (produce it closest to
  where it is consumed).

### Where to hoist (Compose)
- Hoist UI state to the **lowest common ancestor** of all composables that read and
  write it; expose immutable state + event lambdas from the owner.
- The lowest common ancestor may be the ViewModel when business logic reads/writes the
  state (e.g. a `TextField` whose input drives suggestions from the repository). For
  text input hoisted into a ViewModel, use `var input by mutableStateOf(""); private set`
  — Compose text APIs work best with Compose state.
- **Property drilling** (passing state and individual lambdas down several levels) is
  preferred over wrapper objects that bundle state + callbacks: it keeps each
  composable's responsibilities visible and passes only what each needs.
- Pass composables the minimum data (`Header(title, subtitle)` rather than
  `Header(news)`): more reusable, fewer recompositions.
- Compose UI-element state holders with suspend/animation methods (`DrawerState.close()`)
  need a Composition-scoped context: pass `rememberCoroutineScope()` from the UI and
  `withContext(uiScope.coroutineContext)`, otherwise `viewModelScope` throws
  "MonotonicFrameClock is not available".

### Composing state holders
- A state holder may depend on others with **equal or shorter** lifetime (UI-logic holder
  → UI-logic holder; screen ViewModel → nothing UI-scoped).
- Never pass a ViewModel into a plain state holder or into a reusable composable. Pass
  only the data (`StateFlow`/values) and lambdas it needs.

## 5. Producing UI state

*State is; events happen.* Events (user input, repository emissions, timeouts) are the
inputs; UI state is the output.

| Pipeline stage | API |
|---|---|
| Input | Coroutines (`suspend`) and Flows — work off the main thread |
| Output | Observable holder: `StateFlow` (default) or Compose `State` |

| Input kind | Output |
|---|---|
| One-shot APIs only (`suspend` calls, sync calls) | `StateFlow` (`MutableStateFlow` + `update {}`) or Compose `mutableStateOf` |
| Streams (Flows from repositories) | `StateFlow` via `combine(...)…stateIn(...)` |
| Both | `StateFlow`; streams are the constraint — turn one-shot results into private `MutableStateFlow`s and `combine` them |

Requirements of every pipeline:
- **Lifecycle aware** — consumes no resources when UI isn't visible (unless required).
- **Easy to consume** by the UI.

### Stream input
```kotlin
@HiltViewModel
class InterestsViewModel @Inject constructor(
    authorsRepository: AuthorsRepository,
    topicsRepository: TopicsRepository,
) : ViewModel() {
    val uiState: StateFlow<InterestsUiState> = combine(
        authorsRepository.getAuthorsStream(),
        topicsRepository.getTopicsStream(),
    ) { authors, topics -> InterestsUiState.Interests(authors, topics) }
        .stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5_000),
            initialValue = InterestsUiState.Loading,
        )
}
```
- `SharingStarted.WhileSubscribed(5_000)` — active only while UI collects (5 s survives
  configuration change without restarting upstream). The default choice.
- `SharingStarted.Lazily` — keep active while the user may come back (back stack /
  offscreen tab).

### One-shot input
```kotlin
private val _uiState = MutableStateFlow(DiceUiState())
val uiState: StateFlow<DiceUiState> = _uiState.asStateFlow()

fun rollDice() {
    _uiState.update { it.copy(first = Random.nextInt(1, 7), rolls = it.rolls + 1) }
}
```
Always use `update {}` (atomic) rather than `value = value.copy(...)` when concurrent
updates are possible.

### Async one-shot
```kotlin
fun saveTask() {
    viewModelScope.launch {
        try {
            tasksRepository.saveTask(Task(title, description))
            _uiState.update { it.copy(isTaskSaved = true) }
        } catch (e: CancellationException) {
            throw e                       // never swallow cancellation
        } catch (e: Exception) {
            _uiState.update { it.copy(userMessage = e.toUserMessage()) }
        }
    }
}
```

### Mixed input
```kotlin
private val isTaskDeleted = MutableStateFlow(false)
val uiState: StateFlow<TaskDetailUiState> = combine(
    tasksRepository.getTaskStream(taskId),
    isTaskDeleted,
) { task, deleted -> TaskDetailUiState(task = task, isTaskDeleted = deleted) }
    .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), TaskDetailUiState())

fun deleteTask() = viewModelScope.launch {
    tasksRepository.deleteTask(taskId)
    isTaskDeleted.update { true }
}
```

### Threading
- Produce UI state on the main dispatcher. ViewModel work must be **main-safe**; data and
  domain layers move their own work off the main thread.
- If a background context is unavoidable: `withContext(dispatcher)` + `MutableStateFlow.update`
  (or `Snapshot.withMutableSnapshot` for Compose state).

### Initialization
Initialize lazily (wait for a collector via `stateIn`). Avoid kicking off loads in
`init {}` when `stateIn` can do it. If explicit start is unavoidable, expose an
idempotent `@MainThread fun initialize()`.

## 6. Exposing and consuming UI state

Expose:
- A single `val uiState: StateFlow<XUiState>` per screen. Keep the mutable backing
  property private (`_uiState`) and expose `asStateFlow()`.
- **Single stream vs multiple:** one stream for related data (consistency — e.g.
  `isSignedIn && isPremium` must be read together). Separate streams only for
  genuinely unrelated data or data with very different update frequency; use
  `distinctUntilChanged()` where needed.
- Compose-only alternative: `var uiState by mutableStateOf(X()) ; private set`.

Consume (Compose):
```kotlin
@Composable
fun NewsRoute(
    onArticleClick: (String) -> Unit,
    viewModel: NewsViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    NewsScreen(
        uiState = uiState,
        onBookmark = viewModel::toggleBookmark,
        onArticleClick = onArticleClick,
        onMessageShown = viewModel::userMessageShown,
    )
}

@Composable
internal fun NewsScreen(          // stateless: previewable and testable
    uiState: NewsUiState,
    onBookmark: (String, Boolean) -> Unit,
    onArticleClick: (String) -> Unit,
    onMessageShown: (Long) -> Unit,
    modifier: Modifier = Modifier,
) { /* ... */ }
```
- Always `collectAsStateWithLifecycle()`, not `collectAsState()`, for flows from a
  ViewModel — collection stops when the UI is not visible.
- Split a **route** composable (gets the ViewModel, collects state) from a stateless
  **screen** composable (takes state + lambdas). Only the route knows the ViewModel.

## 7. UI events

**Decision tree** (from the guide):
1. Event originates in the UI and only changes UI element state (expand, scroll,
   show tooltip)? → handle it in the UI (`remember` state / plain state holder).
2. Event needs business logic (refresh, save, validate, bookmark)? → call a ViewModel
   function. The ViewModel handles it and updates UI state.
3. Event originates in the UI and is navigation without business logic? → handle in the
   UI: hoist a lambda (`onHelpClick: () -> Unit`) to the caller that owns navigation.
4. Something happens in the ViewModel that the UI must react to (login succeeded, error,
   message)? → **ViewModel updates UI state**; the UI reacts to that state.

Rules:
- **Do not send events from the ViewModel to the UI** (no `Channel`/`SharedFlow`
  "one-off event" streams for navigation/snackbars). Process the event in the ViewModel
  immediately and reflect the result in UI state. *Don't think about what actions the UI
  needs to make; think about how those actions affect the UI state.* This makes
  events survive configuration changes and never get lost.
- **Consuming an event can update state:** after the UI shows a message, it calls back
  (`userMessageShown(id)`) so the ViewModel clears it. The state remains a faithful
  representation of what's on screen.
- **Don't pass the ViewModel down** into lists or reusable composables. Expose lambdas
  (`onItemClick: (Item) -> Unit`) and hoist events up to the route.
- **Naming:** ViewModel functions are verbs for the action (`validateInput()`,
  `login()`, `toggleBookmark()`); composable event parameters are
  `on + Verb + Target` (`onExpandClicked`, `onValueChange`).
- Guard click-triggered navigation with `dropUnlessResumed { ... }`.
- If you worry an event will be consumed twice by multiple consumers, the architecture
  is wrong — move the concern higher up the tree.
- Don't consume state in the background when it doesn't make sense (e.g. toasts) —
  consume only when the UI is in the foreground.

ViewModel-driven navigation via state:
```kotlin
data class LoginUiState(
    val isLoginInProgress: Boolean = false,
    val errorMessage: String? = null,
    val isUserLoggedIn: Boolean = false,
)

@Composable
fun LoginRoute(onUserLoggedIn: () -> Unit, viewModel: LoginViewModel = hiltViewModel()) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val currentOnUserLoggedIn by rememberUpdatedState(onUserLoggedIn)
    LaunchedEffect(uiState.isUserLoggedIn) {
        if (uiState.isUserLoggedIn) currentOnUserLoggedIn()
    }
    LoginScreen(uiState = uiState, onLoginClick = viewModel::login)
}
```
If the source screen stays on the back stack (multi-step flows), keep an extra UI-side
flag (e.g. `var validationInProgress by rememberSaveable { mutableStateOf(false) }`) so
returning to the screen does not auto-navigate again. Navigation is UI logic, so that
flag lives in the UI, not in the ViewModel.

## 8. Loading, errors, user messages

- Loading: a flag in UI state (`isLoading`) or a `Loading` variant of a sealed state.
- Errors: model as data (message + optional retry action), not as exceptions thrown to
  the UI. For transient messages keep a `userMessage`/`userMessages` field and clear it
  via a "message shown" callback.
- Reading local data: `.catch { emit(XUiState.Error) }` in the flow, or the LCE
  (Loading/Content/Error) sealed pattern.
- The ViewModel holds *which* message to show (an id/enum/`@StringRes`), not formatted
  `Resources` strings — resolving strings is UI logic.

## 9. Lifecycle-aware work in Compose

Don't override `Activity` lifecycle callbacks (`onResume`, `onStart`) for UI tasks. Use:
- `LifecycleStartEffect(key) { …; onStopOrDispose { … } }` — synchronous start/stop work.
- `LifecycleResumeEffect(key) { …; onPauseOrDispose { … } }` — resume/pause work.
- `repeatOnLifecycle(Lifecycle.State.STARTED)` — asynchronous work tied to lifecycle.
- `collectAsStateWithLifecycle()` — flows.
- `rememberUpdatedState(callback)` when an effect outlives the callback it captures.

## 10. Paging, navigation, adaptive UI

- `PagingData` is not immutable — **don't put it inside UiState**. Expose
  `Flow<PagingData<T>>` as a separate property (`.cachedIn(viewModelScope)`), collect with
  `collectAsLazyPagingItems()`.
- Navigation: single activity + Navigation 3. Pass **IDs**, not objects, as navigation
  arguments/keys; the destination ViewModel loads the object from the data layer (reads
  arguments from `SavedStateHandle` or the navigation key). Keeps SSOT intact.
- Adaptive: ViewModels can expose state adapted to window size classes; derive with
  `currentWindowAdaptiveInfo()`; let `NavigationSuiteScaffold` switch between bar, rail
  and drawer. Use canonical layouts (list-detail, supporting pane, feed). Preserve UI
  state across resizing/folding/rotation (ViewModel + `rememberSaveable`).
- Build reusable, composable UI components so layouts can be rearranged per form factor.

## 11. Common mistakes (and the fix)

| Mistake | Fix |
|---|---|
| Composable calls a repository/DAO/API directly | Go through a ViewModel; ViewModel calls repository/use case |
| ViewModel passed to `LazyColumn` items or reusable components | Hoist lambdas; only the route touches the ViewModel |
| `collectAsState()` on a ViewModel flow | `collectAsStateWithLifecycle()` |
| `Channel`/`SharedFlow` of `NavigateTo`/`ShowToast` events from ViewModel | Model as UI state + "consumed" callback |
| Several `StateFlow`s that must be read together (e.g. `isLoading`, `items`, `error`) | One `UiState` data class |
| Public `MutableStateFlow` | Private `_uiState`, expose `asStateFlow()` |
| `uiState.value = uiState.value.copy(...)` from several coroutines | `_uiState.update { it.copy(...) }` |
| Loading data in `init {}` + manual `launch` for a stream | `stateIn(viewModelScope, WhileSubscribed(5_000), initial)` |
| `stringResource`-like logic or `Context` in ViewModel | Expose ids/enums; resolve in UI |
| `catch (e: Exception)` around suspend calls that swallows `CancellationException` | Rethrow `CancellationException` (or catch specific exceptions) |
| UI mutates an item's field (e.g. `item.isFavorite = true`) | Send event → ViewModel → repository → new state flows back |
| `PagingData` inside UiState | Separate `Flow<PagingData>` property |
