# Domain layer (use cases) — detailed rules

Source: developer.android.com/topic/architecture/domain-layer, …/recommendations.

## When to add it

The domain layer is **optional**. Add it only when it pays for itself:
- Business logic is **reused by several ViewModels** (formatting with user preferences,
  "is the user allowed to X", combining news + authors).
- A ViewModel's business logic is **complex** and should be split out (combining
  several repositories, non-trivial transformation).
- Other consumers (services, `Application`, Wear/TV UI) need the same logic.

Google's priority: *Recommended in big apps*. Don't create a use case that only forwards
a single repository call — that's ceremony without value. If the UI ends up going
through use cases almost exclusively, it's fine to make that the rule for the
codebase; otherwise allow ViewModels to call repositories directly.

## Rules for use cases

- **One use case = one action/functionality.**
- **No mutable state.** Use cases are stateless; mutable data belongs in the UI or data
  layer. Because they hold no state, create a new instance per injection (unscoped in
  Hilt — don't annotate with `@Singleton`).
- **Lifecycle:** none of their own; scoped to whoever uses them.
- **Dependencies:** repositories and other use cases (multiple levels are normal).
  Never data sources, never UI types, never `Context`.
- **Main-safe.** If the use case does heavy work (e.g. mapping a list of unknown size),
  it moves it to an injected dispatcher. But first ask whether the heavy work belongs
  in the data layer instead (where it can be cached and reused).
- **API:** a single `operator fun invoke(...)` — `suspend` for one-shot results,
  returning `Flow` for streams. Overloads allowed.
- Use cases communicate the same way repositories do: `suspend` + `Flow`.
- Test with fake repositories.

## Naming

*verb in present tense* + *noun/what (optional)* + `UseCase`:
`FormatDateUseCase`, `LogOutUserUseCase`, `GetLatestNewsWithAuthorsUseCase`,
`MakeLoginRequestUseCase`, `GetFollowableTopicsUseCase`.

## Template

```kotlin
class GetLatestNewsWithAuthorsUseCase @Inject constructor(
    private val newsRepository: NewsRepository,
    private val authorsRepository: AuthorsRepository,
    @Dispatcher(Default) private val defaultDispatcher: CoroutineDispatcher,
) {
    suspend operator fun invoke(): List<ArticleWithAuthor> = withContext(defaultDispatcher) {
        newsRepository.fetchLatestNews().map { article ->
            ArticleWithAuthor(article, authorsRepository.getAuthor(article.authorId))
        }
    }
}

// Stream-combining use case
class GetUserNewsResourcesUseCase @Inject constructor(
    private val newsRepository: NewsRepository,
    private val userDataRepository: UserDataRepository,
) {
    operator fun invoke(query: NewsQuery): Flow<List<UserNewsResource>> =
        combine(
            newsRepository.getNewsResourcesStream(query),
            userDataRepository.userData,
        ) { news, userData -> news.mapToUserNewsResources(userData) }
}

// Usage in a ViewModel
@HiltViewModel
class ForYouViewModel @Inject constructor(
    getUserNewsResources: GetUserNewsResourcesUseCase,
) : ViewModel() {
    val feedState: StateFlow<NewsFeedUiState> =
        getUserNewsResources(NewsQuery())
            .map(NewsFeedUiState::Success)
            .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), NewsFeedUiState.Loading)
}
```

## Placement

- Single-module app: `domain` package.
- Multi-module app: a `:core:domain` module (pure Kotlin/JVM where possible) depending on
  data modules; feature modules depend on it.

## Common mistakes

| Mistake | Fix |
|---|---|
| Use case per repository method that just forwards the call | Call the repository from the ViewModel; add use cases when logic is reused or complex |
| Use case holding a `MutableStateFlow`/cache | Move state to repository (data layer) or ViewModel |
| `@Singleton` use case | Leave unscoped |
| Use case taking `Context` to read resources | Expose ids/enums; resolve strings in UI. If a system service is needed, wrap it in a data source behind a repository |
| Use case depends on a DAO/API | Depend on a repository |
| Business rule duplicated in two ViewModels | Extract to a use case (or into the repository if it's about data consistency) |
