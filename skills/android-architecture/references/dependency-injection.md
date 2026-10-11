# Dependency injection — detailed rules

Source: developer.android.com/training/dependency-injection, …/hilt-android,
…/topic/architecture/recommendations (Handle dependencies).

## Principles

- **Use DI** (strongly recommended): classes declare dependencies instead of
  constructing them. Prefer **constructor injection** everywhere you control the
  constructor. Field injection only in framework-instantiated classes (`Activity`,
  `Service`, `BroadcastReceiver`) — and then only to get the entry point, not to hold
  data.
- DI (or a service locator) lets you swap test and production implementations and
  keeps object graphs consistent.
- **Hilt** is Jetpack's recommended DI library (recommended). Manual DI is fine for
  simple apps. Use Hilt when the app has multiple screens with ViewModels, uses
  WorkManager, or scopes ViewModels to navigation back stack entries.
- If the project already uses another DI library (Koin, kotlin-inject, Metro, manual),
  keep it — apply the same principles (constructor injection, scoping, interfaces at
  boundaries). Don't migrate DI frameworks as a side effect of a feature task.

## Scoping

- **Unscoped by default** — a new instance per injection. Correct for stateless types
  (use cases, mappers, most data sources).
- **Scope only when** the type holds mutable data that must be shared, or is expensive to
  create and widely used (strongly recommended): in-memory caches/repositories with a
  cache → `@Singleton`; `OkHttpClient`, `Retrofit`, Room database, DataStore →
  `@Singleton`.
- A binding's scope must match the component it's installed in.

| Hilt component | Injector for | Scope annotation | Lifetime |
|---|---|---|---|
| `SingletonComponent` | `Application` | `@Singleton` | app process |
| `ActivityRetainedComponent` | (survives config change) | `@ActivityRetainedScoped` | first `Activity.onCreate` → last `onDestroy` |
| `ViewModelComponent` | `ViewModel` | `@ViewModelScoped` | ViewModel created → cleared |
| `ActivityComponent` | `Activity` | `@ActivityScoped` | `onCreate` → `onDestroy` |
| `ServiceComponent` | `Service` | `@ServiceScoped` | service lifetime |

Default bindings: `SingletonComponent` → `@ApplicationContext Context`;
`ViewModelComponent` → `SavedStateHandle`.

## Hilt building blocks

```kotlin
@HiltAndroidApp class App : Application()

@AndroidEntryPoint class MainActivity : ComponentActivity()

@HiltViewModel
class TopicViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val topicsRepository: TopicsRepository,
) : ViewModel()

// Interface → implementation: @Binds in an abstract module
@Module
@InstallIn(SingletonComponent::class)
internal abstract class DataModule {
    @Binds
    abstract fun bindsTopicsRepository(impl: OfflineFirstTopicsRepository): TopicsRepository
}

// Third-party / builder-created types: @Provides
@Module
@InstallIn(SingletonComponent::class)
internal object NetworkModule {
    @Provides @Singleton
    fun providesOkHttpClient(): OkHttpClient = OkHttpClient.Builder().build()

    @Provides @Singleton
    fun providesDatabase(@ApplicationContext context: Context): AppDatabase =
        Room.databaseBuilder(context, AppDatabase::class.java, "app-db").build()

    @Provides
    fun providesTopicDao(db: AppDatabase): TopicDao = db.topicDao()
}
```

### Dispatchers and application scope (pattern used by Now in Android)

```kotlin
@Qualifier @Retention(AnnotationRetention.RUNTIME)
annotation class Dispatcher(val dispatcher: AppDispatchers)
enum class AppDispatchers { Default, IO }

@Qualifier @Retention(AnnotationRetention.RUNTIME)
annotation class ApplicationScope

@Module
@InstallIn(SingletonComponent::class)
object CoroutinesModule {
    @Provides @Dispatcher(AppDispatchers.IO)
    fun providesIODispatcher(): CoroutineDispatcher = Dispatchers.IO

    @Provides @Dispatcher(AppDispatchers.Default)
    fun providesDefaultDispatcher(): CoroutineDispatcher = Dispatchers.Default

    @Provides @Singleton @ApplicationScope
    fun providesApplicationScope(
        @Dispatcher(AppDispatchers.Default) dispatcher: CoroutineDispatcher,
    ): CoroutineScope = CoroutineScope(SupervisorJob() + dispatcher)
}
```

### ViewModels in Compose / Navigation 3

- Get screen ViewModels with `hiltViewModel()` (or `viewModel()` without Hilt) in the
  **route/entry** composable only.
- With Navigation 3, scope ViewModels to back-stack entries by adding
  `rememberViewModelStoreNavEntryDecorator()` to `NavDisplay(entryDecorators = …)` after
  `rememberSaveableStateHolderNavEntryDecorator()`; the entry's `ViewModelStore` is
  cleared when the entry is popped.
- Navigation arguments: pass the key into the ViewModel (Hilt assisted injection:
  `@HiltViewModel(assistedFactory = …)` + `hiltViewModel<VM, VM.Factory> { it.create(key) }`)
  or read from `SavedStateHandle`, depending on what the project's navigation setup
  provides.

### WorkManager

`@HiltWorker class SyncWorker @AssistedInject constructor(@Assisted ctx: Context,
@Assisted params: WorkerParameters, private val repo: NewsRepository) : CoroutineWorker(ctx, params)`
plus `HiltWorkerFactory` configured in the `Application`.

### Tests

- Replace bindings with fakes: `@TestInstallIn(components = [SingletonComponent::class],
  replaces = [DataModule::class])` in the test source set, or `@BindValue`.
- Plain unit tests don't need Hilt — construct the class with fakes directly.

## Common mistakes

| Mistake | Fix |
|---|---|
| `val repo = NewsRepository(NewsApi.create())` inside a ViewModel | Constructor-inject the repository |
| Everything annotated `@Singleton` | Scope only shared-mutable-state or expensive types |
| `@Singleton` class holding an `Activity` context | Use `@ApplicationContext`; activity-bound things belong to the UI |
| `object NewsRepository` (Kotlin singleton object with state) | Regular class + DI scope (testable, replaceable) |
| Injecting `Context` into a ViewModel to get strings/system services | Strings → UI; system services → data source behind a repository |
| `@Provides` for your own classes with `@Inject` constructors | Not needed; use `@Inject constructor` (and `@Binds` for interfaces) |
| Service locator calls (`ServiceLocator.get<T>()`) sprinkled in classes in a Hilt project | Constructor injection |
