# Modularization — detailed rules

Source: developer.android.com/topic/modularization, …/modularization/patterns.

## Should this project be modularized?

- **Required** if you need reusability across apps/flavors/form factors, strict
  visibility control, or Play Feature Delivery.
- **Worth considering** for scalability, ownership, encapsulation, testability and
  build time.
- **Skip / postpone** for small codebases that won't grow — overhead outweighs gains.
  A single module with `ui`/`data`/`domain` packages is a valid layered architecture.

Pitfalls:
- **Too fine-grained** — every module adds build config and boilerplate.
- **Too coarse-grained** — a "module" that is a monolith again (e.g. one huge `:data`).
- **Too complex** — modularizing a small project.

Guiding principle: **low coupling** (modules know nothing about each other's inner
workings) and **high cohesion** (a module is one functional domain; don't mix books and
payments).

## Module types (by layer *and* feature)

```
:app                  entry point; root navigation; DI wiring of implementations; per form factor (:app, :wear, :tv)
:feature:<name>:api  navigation keys of the feature (tiny, public)
:feature:<name>:impl screen(s): composables + ViewModels + entry builder. Depends on data/domain/core + other features' :api
:core:data            (or :data:<domain>) repositories (public API), data sources + models (internal)
:core:domain          use cases (optional)
:core:database        Room DB, DAOs, entities
:core:network         HTTP client, network data source, DTOs
:core:datastore       DataStore + serializers
:core:model           pure Kotlin external models shared everywhere
:core:ui / :core:designsystem   shared composables, theme
:core:common          dispatchers, qualifiers, small utils
:core:testing         fakes, test rules, test data shared by tests
```

Rules per type:
- **Data module**: encapsulates all data + business logic of one domain; **public API =
  repository** (interface + model); data sources, DTOs, entities are `internal`.
- **Feature module**: UI + ViewModel for a screen or closely related flow (sign-up,
  checkout, each bottom-nav tab). **Depends on data (or domain) modules.** With
  Navigation 3, split each feature into `:feature:x:api` (navigation keys only) and
  `:feature:x:impl` (entries, screens, ViewModels). An `impl` may depend on another
  feature's `api` (to navigate to its key) but **never on another feature's `impl`**.
- **App module**: depends on features, owns root navigation, provides implementations
  through DI and build variants.
- **Common/core modules**: UI kit, analytics, network client, utilities — no specific
  layer.
- **Test modules**: shared fakes, test data, integration tests, separate build config.

## Module-to-module communication

- Features must not depend on each other (cycles, coupling). A **mediator** — usually
  the app module that owns navigation — connects them.
- **Pass IDs, not objects**, between features (navigation keys/arguments). The target
  ViewModel reads the ID (from its navigation key / `SavedStateHandle`) and loads the
  object from the shared data module. This keeps coupling low and preserves SSOT.
- Navigation 3 modularization: keys in the feature's `api` module; content in `impl`
  as an **entry builder** — an extension `fun EntryProviderScope<NavKey>.featureXEntryBuilder()`.
  The app module calls the builders inside `NavDisplay(entryProvider = entryProvider { … })`,
  directly or via a Hilt `@IntoSet` multibinding of `EntryProviderScope<NavKey>.() -> Unit`
  (installed in `ActivityRetainedComponent`). If entries need to navigate, inject a
  navigator/back-stack owner into the builder instead of referencing other features.
- Deep links: each feature defines matchers for its own destinations; collect them with
  a DI multibinding.

```kotlin
// :feature:checkout — public API
@Serializable data class CheckoutKey(val bookId: String) : NavKey

// :feature:checkout — internal
@HiltViewModel(assistedFactory = CheckoutViewModel.Factory::class)
internal class CheckoutViewModel @AssistedInject constructor(
    @Assisted private val key: CheckoutKey,
    bookRepository: BookRepository,
) : ViewModel() {
    val uiState: StateFlow<CheckoutUiState> = bookRepository.getBookStream(key.bookId)
        .map(CheckoutUiState::Ready)
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), CheckoutUiState.Loading)

    @AssistedFactory interface Factory { fun create(key: CheckoutKey): CheckoutViewModel }
}
```
(Equivalent with `SavedStateHandle` when the navigation library puts arguments there.)

## Dependency inversion

Separate **API (abstraction) modules** — interfaces + models — from **implementation
modules**. High-level modules depend only on the API; the app module picks the
implementation per build variant/test:

```kotlin
// :app build.gradle.kts
releaseImplementation(project(":database:impl:firestore"))
debugImplementation(project(":database:impl:room"))
androidTestImplementation(project(":database:impl:fake"))
```

Benefits: interchangeability, decoupling from technology, testability, faster builds
(implementation changes don't recompile dependants). Do it when there are diverse
implementations, multiple apps/platforms, independent teams, or a large codebase —
not by default for everything.

## Best practices

- **Consistent configuration:** version catalog (`libs.versions.toml`) for all
  dependencies; **convention plugins** (`build-logic`) for shared Gradle setup.
- **Expose as little as possible:** `internal`/`private` for everything except the
  module's API. Prefer `implementation` over `api` in Gradle dependencies (`api` leaks
  transitive dependencies and slows builds).
- **Prefer pure Kotlin/JVM modules** (no Android resources/manifest) where possible —
  e.g. `:core:model`, `:core:domain`; Android library modules cost more.
- Avoid cycles; if two modules need each other, extract an API module or mediate via
  `:app`.
- DI: each module contributes its own Hilt `@Module`s; bindings of interface →
  implementation live next to the implementation (or in `:app` when variant-specific).

## Review checklist

- [ ] No feature `impl` → other feature `impl` dependency (depending on another feature's `api`/keys is fine).
- [ ] Data modules expose repositories (interfaces/classes) + models only; data sources,
      DAOs, DTOs, entities are `internal`.
- [ ] Navigation between features passes IDs.
- [ ] `api(...)` only where a type is actually part of the module's public signature.
- [ ] Shared versions via catalog; shared config via convention plugins.
- [ ] Module granularity matches project size.
