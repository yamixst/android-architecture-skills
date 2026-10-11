# Templates — a complete feature slice

A minimal but complete, guideline-compliant vertical slice ("bookmarkable articles").
Copy the shape, not the names. Adapt to the project's existing conventions (package
layout, result types, DI framework, navigation library) — consistency with the codebase
beats template purity.

Layout (single module; in multi-module apps each block maps to a module, see
modularization.md):
```
model/Article.kt                       external model (pure Kotlin)
data/network/ArticleNetworkDataSource.kt  + NetworkArticle (DTO, internal)
data/local/ArticleDao.kt               + ArticleEntity (internal)
data/repository/ArticlesRepository.kt  interface + OfflineFirstArticlesRepository
data/di/DataModule.kt                  Hilt bindings
domain/GetBookmarkedArticlesUseCase.kt (only if reused/complex)
ui/articles/ArticlesUiState.kt
ui/articles/ArticlesViewModel.kt
ui/articles/ArticlesScreen.kt          Route (stateful) + Screen (stateless)
ui/articles/ArticlesNavigation.kt      nav key + entry
test/.../FakeArticlesRepository.kt, ArticlesViewModelTest.kt
```

## Model and data layer

```kotlin
// model/Article.kt — immutable external model
data class Article(
    val id: String,
    val title: String,
    val summary: String,
    val publishedAt: Instant,
    val isBookmarked: Boolean,
)

// data/network/NetworkArticle.kt
@Serializable
internal data class NetworkArticle(
    val id: String,
    val title: String,
    val summary: String,
    @SerialName("published_at") val publishedAt: Instant,
    val comments: List<NetworkComment> = emptyList(),   // app doesn't need these
)
internal fun NetworkArticle.asEntity() = ArticleEntity(id, title, summary, publishedAt, isBookmarked = false)

// data/local/ArticleEntity.kt + ArticleDao.kt
@Entity(tableName = "articles")
internal data class ArticleEntity(
    @PrimaryKey val id: String,
    val title: String,
    val summary: String,
    val publishedAt: Instant,
    @ColumnInfo(name = "is_bookmarked") val isBookmarked: Boolean,
)
internal fun ArticleEntity.asExternalModel() = Article(id, title, summary, publishedAt, isBookmarked)

@Dao
internal interface ArticleDao {
    @Query("SELECT * FROM articles ORDER BY publishedAt DESC")
    fun observeArticles(): Flow<List<ArticleEntity>>

    @Query("UPDATE articles SET is_bookmarked = :bookmarked WHERE id = :id")
    suspend fun setBookmarked(id: String, bookmarked: Boolean)

    @Upsert
    suspend fun upsertArticles(articles: List<ArticleEntity>)
}

// data/network/ArticleNetworkDataSource.kt — one source, main-safe
internal class ArticleNetworkDataSource @Inject constructor(
    private val api: ArticlesApi,              // Retrofit suspend API: already main-safe
) {
    suspend fun getArticles(): List<NetworkArticle> = api.getArticles()
}

// data/repository/ArticlesRepository.kt — the public entry point
interface ArticlesRepository {
    fun getArticlesStream(): Flow<List<Article>>
    suspend fun setBookmarked(articleId: String, bookmarked: Boolean)
    suspend fun sync(): Boolean
}

internal class OfflineFirstArticlesRepository @Inject constructor(
    private val articleDao: ArticleDao,                     // source of truth
    private val network: ArticleNetworkDataSource,
) : ArticlesRepository {

    override fun getArticlesStream(): Flow<List<Article>> =
        articleDao.observeArticles().map { entities -> entities.map(ArticleEntity::asExternalModel) }

    override suspend fun setBookmarked(articleId: String, bookmarked: Boolean) =
        articleDao.setBookmarked(articleId, bookmarked)      // lazy write: local first

    override suspend fun sync(): Boolean = try {
        articleDao.upsertArticles(network.getArticles().map(NetworkArticle::asEntity))
        true
    } catch (e: CancellationException) {
        throw e
    } catch (e: IOException) {
        false
    }
}

// data/di/DataModule.kt
@Module
@InstallIn(SingletonComponent::class)
internal abstract class DataModule {
    @Binds
    abstract fun bindsArticlesRepository(impl: OfflineFirstArticlesRepository): ArticlesRepository
}
```
(Upsert of network data must preserve local-only fields such as `isBookmarked` in a real
app — e.g. keep bookmarks in a separate table or DataStore and combine streams.)

## UI layer

```kotlin
// ui/articles/ArticlesUiState.kt
sealed interface ArticlesUiState {
    data object Loading : ArticlesUiState
    data class Success(
        val articles: List<ArticleItemUiState>,
        val isRefreshing: Boolean = false,
        val userMessage: UserMessage? = null,
    ) : ArticlesUiState
}
data class ArticleItemUiState(val id: String, val title: String, val summary: String, val isBookmarked: Boolean)
enum class UserMessage { RefreshFailed }                 // UI resolves to a string

// ui/articles/ArticlesViewModel.kt
@HiltViewModel
class ArticlesViewModel @Inject constructor(
    private val articlesRepository: ArticlesRepository,
) : ViewModel() {

    private val isRefreshing = MutableStateFlow(false)
    private val userMessage = MutableStateFlow<UserMessage?>(null)

    val uiState: StateFlow<ArticlesUiState> = combine(
        articlesRepository.getArticlesStream(),
        isRefreshing,
        userMessage,
    ) { articles, refreshing, message ->
        ArticlesUiState.Success(
            articles = articles.map { ArticleItemUiState(it.id, it.title, it.summary, it.isBookmarked) },
            isRefreshing = refreshing,
            userMessage = message,
        )
    }.stateIn(
        scope = viewModelScope,
        started = SharingStarted.WhileSubscribed(5_000),
        initialValue = ArticlesUiState.Loading,
    )

    fun toggleBookmark(articleId: String, bookmarked: Boolean) {
        viewModelScope.launch { articlesRepository.setBookmarked(articleId, bookmarked) }
    }

    fun refresh() {
        viewModelScope.launch {
            isRefreshing.value = true
            if (!articlesRepository.sync()) userMessage.value = UserMessage.RefreshFailed
            isRefreshing.value = false
        }
    }

    fun userMessageShown() { userMessage.value = null }
}

// ui/articles/ArticlesScreen.kt
@Composable
fun ArticlesRoute(
    onArticleClick: (articleId: String) -> Unit,          // navigation hoisted to caller
    modifier: Modifier = Modifier,
    viewModel: ArticlesViewModel = hiltViewModel(),
) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    ArticlesScreen(
        uiState = uiState,
        onArticleClick = onArticleClick,
        onBookmarkChange = viewModel::toggleBookmark,
        onRefresh = viewModel::refresh,
        onUserMessageShown = viewModel::userMessageShown,
        modifier = modifier,
    )
}

@Composable
internal fun ArticlesScreen(
    uiState: ArticlesUiState,
    onArticleClick: (String) -> Unit,
    onBookmarkChange: (String, Boolean) -> Unit,
    onRefresh: () -> Unit,
    onUserMessageShown: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val snackbarHostState = remember { SnackbarHostState() }
    Scaffold(modifier = modifier, snackbarHost = { SnackbarHost(snackbarHostState) }) { padding ->
        when (uiState) {
            ArticlesUiState.Loading -> Box(Modifier.fillMaxSize().padding(padding)) {
                CircularProgressIndicator(Modifier.align(Alignment.Center))
            }
            is ArticlesUiState.Success -> {
                PullToRefreshBox(isRefreshing = uiState.isRefreshing, onRefresh = onRefresh, modifier = Modifier.padding(padding)) {
                    LazyColumn {
                        items(uiState.articles, key = { it.id }) { item ->
                            ArticleRow(                       // gets data + lambdas, never the ViewModel
                                item = item,
                                onClick = dropUnlessResumed { onArticleClick(item.id) },
                                onBookmarkChange = { onBookmarkChange(item.id, it) },
                            )
                        }
                    }
                }
                uiState.userMessage?.let { message ->
                    val text = when (message) { UserMessage.RefreshFailed -> stringResource(R.string.refresh_failed) }
                    LaunchedEffect(message) {
                        snackbarHostState.showSnackbar(text)
                        onUserMessageShown()                  // consuming the message updates state
                    }
                }
            }
        }
    }
}
```

## Navigation (Navigation 3)

```kotlin
@Serializable data object ArticlesKey : NavKey
@Serializable data class ArticleDetailKey(val articleId: String) : NavKey   // pass the ID, not the Article

fun EntryProviderScope<NavKey>.articlesEntries(navigator: Navigator) {
    entry<ArticlesKey> {
        ArticlesRoute(onArticleClick = { id -> navigator.navigate(ArticleDetailKey(id)) })
    }
}

// App-level host
NavDisplay(
    backStack = backStack,
    onBack = { backStack.removeLastOrNull() },
    entryDecorators = listOf(
        rememberSaveableStateHolderNavEntryDecorator(),
        rememberViewModelStoreNavEntryDecorator(),           // ViewModel per back-stack entry
    ),
    entryProvider = entryProvider { articlesEntries(navigator) /* , other features */ },
)
```
(`Navigator` is an app-defined class wrapping the back stack. Use whatever navigation
abstraction the project already has.)

## Background sync

```kotlin
@HiltWorker
class SyncWorker @AssistedInject constructor(
    @Assisted appContext: Context,
    @Assisted params: WorkerParameters,
    private val articlesRepository: ArticlesRepository,
) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result =
        if (articlesRepository.sync()) Result.success() else Result.retry()
}
// Enqueue once at startup as unique work with ExistingWorkPolicy.KEEP and
// Constraints(requiredNetworkType = NetworkType.CONNECTED) — from an App Startup
// Initializer or the Application, not from a screen.
```

## Tests

```kotlin
class FakeArticlesRepository : ArticlesRepository {
    private val articles = MutableStateFlow<List<Article>>(emptyList())
    var syncResult = true
    fun emit(value: List<Article>) { articles.value = value }

    override fun getArticlesStream(): Flow<List<Article>> = articles
    override suspend fun setBookmarked(articleId: String, bookmarked: Boolean) =
        articles.update { list -> list.map { if (it.id == articleId) it.copy(isBookmarked = bookmarked) else it } }
    override suspend fun sync() = syncResult
}

class ArticlesViewModelTest {
    @get:Rule val mainDispatcherRule = MainDispatcherRule()
    private val repository = FakeArticlesRepository()
    private val viewModel = ArticlesViewModel(repository)

    @Test
    fun stateIsInitiallyLoading() = runTest {
        assertEquals(ArticlesUiState.Loading, viewModel.uiState.value)
    }

    @Test
    fun toggleBookmark_updatesState() = runTest {
        backgroundScope.launch(UnconfinedTestDispatcher()) { viewModel.uiState.collect() }
        repository.emit(listOf(sampleArticle.copy(isBookmarked = false)))

        viewModel.toggleBookmark(sampleArticle.id, true)

        val state = viewModel.uiState.value as ArticlesUiState.Success
        assertTrue(state.articles.single().isBookmarked)
    }

    @Test
    fun refreshFailure_showsMessage_thenClears() = runTest {
        backgroundScope.launch(UnconfinedTestDispatcher()) { viewModel.uiState.collect() }
        repository.syncResult = false

        viewModel.refresh()
        assertEquals(UserMessage.RefreshFailed, (viewModel.uiState.value as ArticlesUiState.Success).userMessage)

        viewModel.userMessageShown()
        assertNull((viewModel.uiState.value as ArticlesUiState.Success).userMessage)
    }
}
```
