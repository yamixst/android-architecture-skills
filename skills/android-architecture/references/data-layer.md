# Data layer (and offline-first) — detailed rules

Source: developer.android.com/topic/architecture/data-layer,
…/data-layer/offline-first, …/topic/architecture (guide), …/recommendations.

## Contents
1. Structure: repositories and data sources
2. Public API shape (suspend + Flow), immutability
3. Single source of truth
4. Threading (main-safety)
5. Lifecycle and scoping of data-layer objects
6. Models per layer and mapping
7. Operation types → which scope runs them
8. Errors
9. Persistence choice: Room / DataStore / file
10. Caching in memory
11. WorkManager tasks as a data source
12. Offline-first: reads, writes, sync, conflicts
13. Naming
14. Testing the data layer
15. Common mistakes

---

## 1. Structure

The data layer holds **application data and business logic** (the rules for how data is
created, stored and changed). It is made of **repositories**, each with **zero to many
data sources**.

```
UI / domain  ──►  XRepository  ──►  XRemoteDataSource  (network: Retrofit/Ktor API)
                               └─►  XLocalDataSource   (Room DAO / DataStore / file)
                               └─►  XTasksDataSource   (WorkManager)
```

Repository responsibilities:
- Expose data to the rest of the app.
- Centralize changes to the data.
- Resolve conflicts between data sources.
- Abstract data sources away from the rest of the app.
- Contain business logic.

Data source responsibilities: work with **exactly one** source of data (a file, a
network API, a database, a DataStore, a system provider such as location/Bluetooth/
connectivity). Data sources are the bridge between the app and the system.

Rules:
- **Repositories are the only entry point** to the data layer. ViewModels, use cases,
  workers, services never depend on a data source, DAO, Retrofit service or
  `SharedPreferences` directly.
- **Create a repository even if it has a single data source** (strongly recommended) —
  it gives you a seam for caching, mapping and offline-first later.
- One repository per **type of data** (`NewsRepository`, `PaymentsRepository`), not per
  screen.
- Repositories may depend on other repositories when data is aggregated
  (`UserRepository` → `LoginRepository`, `RegistrationRepository`). Avoid cycles.
- Inject data sources via the constructor (DI); depend on interfaces where you need
  swappable implementations (tests, flavors).
- In small apps a `data` package is enough; in larger apps, data modules
  (see `modularization.md`).

## 2. Public API shape

| Need | Expose |
|---|---|
| One-shot CRUD (create/read once/update/delete) | `suspend fun` |
| Be notified of changes over time | `Flow<T>` |

```kotlin
interface NewsRepository {
    fun getNewsResourcesStream(query: NewsQuery = NewsQuery()): Flow<List<NewsResource>>
    suspend fun toggleBookmark(newsResourceId: String, bookmarked: Boolean)
    suspend fun sync(): Boolean
}
```
- **Exposed data must be immutable** (`val`s, read-only `List`), so no one can tamper
  with it and it's safe across threads.
- Don't expose `MutableStateFlow`, `MutableList`, DAO entities or network DTOs.
- Don't expose `LiveData` from the data layer (it's a UI-layer, main-thread type). Use
  `Flow`.

## 3. Single source of truth (SSOT)

- Each repository defines **one** source of truth; the data it exposes always comes
  from that source.
- The SSOT can be the database, an in-memory cache, or (rarely) the network.
  Different repositories may have different SSOTs.
- **For offline-first support, the local data source (e.g. Room) is the recommended
  SSOT.** Network results are written to the DB; readers observe the DB.
- Only the SSOT mutates its data; it exposes immutable data and functions/events to
  request changes.

## 4. Threading

- Every repository and data source must be **main-safe**: callable from the main
  thread. The class that does blocking work moves it to the right dispatcher itself
  (`withContext(ioDispatcher)` for blocking I/O, `Dispatchers.Default` for CPU).
- Room, Retrofit and Ktor `suspend` APIs are already main-safe — don't wrap them in
  `withContext(Dispatchers.IO)` needlessly.
- **Inject dispatchers** (constructor parameter, Hilt qualifier) instead of hardcoding
  `Dispatchers.IO` — makes tests deterministic.

```kotlin
class NewsRemoteDataSource @Inject constructor(
    private val newsApi: NewsApi,
    @Dispatcher(IO) private val ioDispatcher: CoroutineDispatcher,
) {
    /** Main-safe: moves the blocking call to the IO dispatcher. */
    suspend fun fetchLatestNews(): List<NetworkArticle> =
        withContext(ioDispatcher) { newsApi.fetchLatestNews() }
}
```

## 5. Lifecycle and scoping

- Data-layer objects live while referenced. A class with in-memory state (a cache, a
  mutex) must be shared → **scope it** in the DI container:
  - Crucial to the whole app → `@Singleton` (application scope).
  - Only needed in one flow (registration, checkout) → scope to that flow's owner
    (e.g. a navigation back-stack entry / graph, a dedicated component).
- Stateless classes need no scope.

## 6. Models per layer

- The network (`NetworkArticle`/`ArticleApiModel`) and the database (`ArticleEntity`)
  each have their own model; the repository exposes a third, clean **external model**
  (`Article`) containing only what the app needs.
- Keep DTOs and entities `internal` to the data layer/module.
- Map with extension functions: `NetworkAuthor.asEntity()`, `AuthorEntity.asExternalModel()`.
- **At minimum, create a new model whenever a data source receives data that doesn't
  match what the rest of the app expects.** In complex apps, a model per layer is
  recommended; in simple apps, don't add mapping that brings nothing.
- The UI layer may wrap data models in `UiState` classes.

## 7. Operation types and their scope

| Type | Lives as long as | Example | Run it in |
|---|---|---|---|
| **UI-oriented** | the screen is shown; cancel when user leaves | load news for the visible screen | caller's scope (`viewModelScope`) — repository just exposes `suspend`/`Flow` |
| **App-oriented** | the app process is alive | finish caching a network result even if the user navigates away | an **injected application `CoroutineScope`** (`externalScope` / `@ApplicationScope`, `SupervisorJob() + Dispatchers.Default`) — never `GlobalScope`, never create your own scope inside the class |
| **Business-oriented** | must complete, survives process death | upload a photo, sync pending writes | **WorkManager** |

App-oriented pattern:
```kotlin
class NewsRepository @Inject constructor(
    private val remote: NewsRemoteDataSource,
    @ApplicationScope private val externalScope: CoroutineScope,
) {
    private val mutex = Mutex()
    private var latestNews: List<Article> = emptyList()

    suspend fun getLatestNews(refresh: Boolean = false): List<Article> =
        if (refresh) {
            externalScope.async {
                remote.fetchLatestNews().map { it.asExternalModel() }
                    .also { result -> mutex.withLock { latestNews = result } }
            }.await()   // caller may be cancelled; work in externalScope continues
        } else {
            mutex.withLock { latestNews }
        }
}
```

## 8. Errors

- Use Kotlin's built-in mechanisms: exceptions from `suspend` functions (`try/catch`
  at the caller where appropriate), `catch` operator on flows.
- The data layer may translate low-level errors into **domain-specific exceptions**
  (`UserNotAuthenticatedException`) or a typed result if the codebase already uses one.
- The UI layer (ViewModel) is expected to handle them and turn them into UI state.
- Never swallow `CancellationException`.

## 9. Persistence choice

| Data | Store |
|---|---|
| Large datasets that are queried, need referential integrity or partial updates | **Room** (`XLocalDataSource` wraps a DAO; injecting the DAO directly into the repository is acceptable when no extra logic is needed) |
| Small key-value or typed settings, read/written whole | **DataStore** (Preferences or Proto). One DataStore per related group of settings (`NotificationsDataStore`, `NewsPreferencesDataStore`), so the flow emits only on relevant changes |
| Chunks of data (a JSON blob, a bitmap) | **File** (handle threading yourself) |

Callers must not know *how* data is saved: name the source by data + Local/Remote
(`UserPreferencesLocalDataSource`), not by technology (`UserSharedPreferencesDataSource`),
so you can migrate SharedPreferences → DataStore without touching callers.
`SharedPreferences` for new code: prefer DataStore.

## 10. In-memory caching

- Cache in the repository or data source, protected for concurrent access
  (`Mutex`, or a `MutableStateFlow` used as the cache).
- If the cache must survive leaving the screen, the fetch must run in the app-scoped
  `externalScope` (section 7) and the repository must be scoped (`@Singleton`).

## 11. WorkManager tasks as a data source

- Wrap scheduling in a data source owned by a repository: `NewsTasksDataSource`
  (enqueue/cancel unique periodic work). All tasks for one data type live in one class.
- The `Worker` (`CoroutineWorker`, `@HiltWorker`) depends on the **repository** and
  calls e.g. `newsRepository.refreshLatestNews()`; it contains no business logic itself.
- Use unique work + constraints (`NetworkType.CONNECTED`/`UNMETERED`, charging).
- Trigger startup work from an App Startup `Initializer` that calls the repository/
  sync manager, not from `Activity.onCreate`.

## 12. Offline-first

An offline-first app performs all (or a critical subset) of its core functionality
without the network: it shows local data immediately, stays usable on a flaky
connection, and fetches data under good conditions.

Model: every repository that touches the network has **at least two data sources**:
- **Local data source** — the canonical **source of truth**, the *exclusive* source of
  reads for higher layers. Room / DataStore / files.
- **Network data source** — the actual state of the world; the local copy syncs with
  it. **UI and domain layers never talk to the network directly**; the repository
  does, and writes results into the local source.

Reads:
- Expose reads as `Flow` from the local source (reactive). Readers must handle
  emissions when sync finishes. The repository notifies readers *only* by updating the
  local source.
- ViewModel: `repository.getXStream().stateIn(viewModelScope, WhileSubscribed(5_000), …)`.
- Local read errors: `catch` in the flow or LCE sealed state.
- Network read errors: retry with **exponential backoff** (don't retry auth errors
  until credentials change; cap retries) or **queue reads** until connectivity returns
  (Room-backed queue drained by WorkManager).

Writes are `suspend` functions. Pick a strategy per data type:

| Strategy | How | Use for |
|---|---|---|
| **Online-only** | write to network; on success update local; on failure throw | near-real-time transactions (bank transfer). Disable or explain the UI when offline |
| **Queued** | insert into a queue, drain with backoff when online (WorkManager) | non-critical, not time-sensitive (analytics, logs) |
| **Lazy** | write locally first, queue network write | user data that must not be lost (to-do items). Requires conflict resolution |

Synchronization:

| | Pull-based | Push-based |
|---|---|---|
| How | fetch on demand (e.g. just before showing a screen; Paging `RemoteMediator`) | baseline fetch at startup, then server notifies what's stale; fetch only changed data |
| Pros | simple; never fetches unneeded data | works offline indefinitely; minimal data use; good for relational data |
| Cons | heavy data use (mitigate with caching, `cachedIn`, HTTP cache); bad for relational data | versioning for conflicts; write concerns during sync; backend must support it |

Hybrid is common (feed = pull, user profile = push).

Conflict resolution usually needs versioning/timestamps; the common mobile approach
is **last write wins** (server keeps the newest timestamped write).

WorkManager is the tool for both read/write queues and connectivity monitoring:
enqueue unique sync work at startup with `ExistingWorkPolicy.KEEP` and
`NetworkType.CONNECTED`; the worker calls `repository.sync()` for each repository in
parallel and returns `Result.retry()` on failure (automatic exponential backoff).

```kotlin
class OfflineFirstTopicsRepository @Inject constructor(
    private val topicDao: TopicDao,                       // local = source of truth
    private val network: TopicsNetworkDataSource,
) : TopicsRepository {
    // Reads come only from the local source.
    override fun getTopicsStream(): Flow<List<Topic>> =
        topicDao.getTopicEntities().map { entities -> entities.map(TopicEntity::asExternalModel) }

    // Sync: network → local. Readers get the update through the Flow above.
    override suspend fun sync(): Boolean = try {
        topicDao.upsertTopics(network.getTopics().map(NetworkTopic::asEntity))
        true
    } catch (e: CancellationException) {
        throw e
    } catch (e: IOException) {
        false                                            // worker returns Result.retry()
    }
}

class SyncWorker(/* injected repositories, dispatcher */) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result = withContext(ioDispatcher) {
        val ok = awaitAll(
            async { topicsRepository.sync() },
            async { newsRepository.sync() },
        ).all { it }
        if (ok) Result.success() else Result.retry()
    }
}
```
The Now in Android sample implements this with change-list versioning and a
`DelegatingWorker` so the worker can live in a library module.

Managed alternatives (Firestore offline cache, Firebase SQL Connect) are valid: they
replace the custom local/network/sync stack, but still sit **behind a repository**.

## 13. Naming

- Repository: *type of data* + `Repository` → `NewsRepository`.
- Data source: *type of data* + *type of source* + `DataSource` → `NewsRemoteDataSource`,
  `NewsLocalDataSource`; be specific only when it matters (`NewsNetworkDataSource`,
  `NewsDiskDataSource`). Never name after the implementation detail.
- Interface implementations: meaningful prefix (`OfflineFirstNewsRepository`,
  `InMemoryNewsRepository`), else `DefaultNewsRepository`. Fakes: `FakeNewsRepository`.
- Streams: `get{Model}Stream(): Flow<Model>`, plural for lists
  (`getAuthorsStream(): Flow<List<Author>>`).

## 14. Testing

- Unit tests for repositories and data sources (strongly recommended).
- Inject **fakes** for anything reaching external resources (network, files); use real
  objects otherwise. Prefer fakes to mocks.
- Room: in-memory database in tests. Network: MockWebServer / WireMock.
- Run integration tests in a controlled environment.

## 15. Common mistakes

| Mistake | Fix |
|---|---|
| ViewModel injects `XDao`, `XApi`, `Retrofit`, `SharedPreferences`, `FirebaseFirestore` | Create/inject `XRepository` |
| Repository returns Retrofit DTO / Room entity to UI | Map to external model inside data layer |
| Repository launches work in `GlobalScope` or `CoroutineScope(Dispatchers.IO)` created internally | Inject `@ApplicationScope CoroutineScope`; for must-finish work use WorkManager |
| Repository exposes `MutableStateFlow`/`LiveData` | Expose `Flow`/`StateFlow` (read-only) |
| Hardcoded `Dispatchers.IO` | Inject `CoroutineDispatcher` |
| Network result shown directly while DB also holds data (two sources of truth) | Write network result to DB; UI observes DB |
| Worker contains business logic / talks to API directly | Worker → repository |
| One giant `AppRepository` for everything | One repository per data type |
| Repository per screen (`HomeScreenRepository`) | Repository per data type; combine in ViewModel or use case |
| Data source named after tech (`UserSharedPrefsDataSource`) | `UserPreferencesLocalDataSource` |
