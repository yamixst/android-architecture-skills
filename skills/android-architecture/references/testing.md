# Testing — detailed rules

Source: developer.android.com/topic/architecture/recommendations (Testing),
…/training/testing/fundamentals, …/fundamentals/test-doubles, …/fundamentals/strategies,
…/kotlin/coroutines/coroutines-best-practices.

## What to test (strongly recommended minimum for any non-trivial app)

- **Unit tests for ViewModels, including their Flows** (UI state over time).
- **Unit tests for data-layer entities**: repositories and data sources.
- **UI navigation tests** — useful as regression tests in CI.
- **Performance tests with Macrobenchmark** (startup, UI rendering).
Plus: use cases (if present), Compose UI tests for screens with state permutations,
screenshot tests for design-system components.

## Test doubles

**Prefer fakes to mocks** (strongly recommended). A fake is a working, lightweight
implementation (in-memory list/`MutableStateFlow`) that lives in the test source set or
a shared `:core:testing` module. Mocks (Mockito/MockK) only when verifying an
interaction is the point of the test. Avoid spies.

Architecture makes this possible: depend on interfaces at layer boundaries
(`NewsRepository` interface + `OfflineFirstNewsRepository` impl + `FakeNewsRepository`
for tests), and inject everything through constructors.

```kotlin
class FakeNewsRepository : NewsRepository {
    private val news = MutableStateFlow<List<NewsResource>>(emptyList())
    fun sendNews(value: List<NewsResource>) { news.value = value }      // test hook

    override fun getNewsResourcesStream(query: NewsQuery): Flow<List<NewsResource>> =
        news.map { list -> list.filter(query::matches) }
    override suspend fun toggleBookmark(newsResourceId: String, bookmarked: Boolean) {
        news.update { list -> list.map { if (it.id == newsResourceId) it.copy(isBookmarked = bookmarked) else it } }
    }
    override suspend fun sync() = true
}
```
Naming: `Fake` prefix (`FakeAuthorsRepository`). Test names describe behavior
(`bookmarkToggled_updatesUiState`).

## ViewModel test template

```kotlin
class NewsViewModelTest {
    @get:Rule val mainDispatcherRule = MainDispatcherRule()

    private val newsRepository = FakeNewsRepository()
    private lateinit var viewModel: NewsViewModel

    @Before fun setUp() { viewModel = NewsViewModel(newsRepository) }

    @Test
    fun uiState_initiallyLoading() = runTest {
        assertEquals(NewsUiState.Loading, viewModel.uiState.value)
    }

    @Test
    fun uiState_whenNewsEmitted_isSuccess() = runTest {
        backgroundScope.launch(UnconfinedTestDispatcher()) { viewModel.uiState.collect() }

        newsRepository.sendNews(sampleNews)

        assertEquals(NewsUiState.Success(sampleNews.map { it.asUiState() }), viewModel.uiState.value)
    }
}
```
- Assert on `StateFlow.value` whenever possible; keep a collector alive in
  `backgroundScope` when the flow uses `WhileSubscribed`.
- Don't test private implementation; test inputs (events, fake emissions) → output
  (UI state).

## Data layer tests

- Repository unit tests with fake data sources (or real DAO over an in-memory Room DB).
- Network data source: MockWebServer/WireMock.
- Room: `Room.inMemoryDatabaseBuilder(...)` in instrumented or Robolectric tests.
- Inject `TestDispatcher` for dispatchers and `TestScope`/`backgroundScope` for external
  scopes.

## UI tests (Compose)

- Test the **stateless screen** composable (`NewsScreen(uiState = …, onX = {})`) with
  `createComposeRule()` — no ViewModel, no DI needed. Each `UiState` variant is a test.
- Navigation/integration tests with Hilt (`@HiltAndroidTest`, `HiltAndroidRule`) and
  `@TestInstallIn` to replace data modules with fakes → hermetic tests.

## Test pyramid

Many small, fast tests (unit, component; run every commit) → fewer feature tests
(pre-merge) → few application / release-candidate tests (post-merge, pre-release).
Choose the lowest layer that gives the needed feedback.
