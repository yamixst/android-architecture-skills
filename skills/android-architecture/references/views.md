# Views / Fragments projects — what changes

Source: developer.android.com/topic/architecture/views/recommendations-views and the
"(Views)" variants of the UI-layer pages.

The architecture (layers, UDF, SSOT, repositories, ViewModels exposing `StateFlow`) is
**identical**. Only the UI-side APIs differ. For new apps and new screens Google
recommends Compose; in an existing Views codebase follow the project's toolkit and
these rules. Interop (Compose inside a Fragment via `ComposeView`) is a valid migration
path, screen by screen.

| Concern | Compose | Views / Fragments |
|---|---|---|
| Collect UI state | `collectAsStateWithLifecycle()` | `viewLifecycleOwner.lifecycleScope.launch { viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) { viewModel.uiState.collect { render(it) } } }` |
| Lifecycle work | `LifecycleStartEffect` / `LifecycleResumeEffect` | `DefaultLifecycleObserver` added to `viewLifecycleOwner.lifecycle`; `repeatOnLifecycle` for async work. **Don't override `onResume`/`onStart` etc. for this work** |
| Screen-level state holder | ViewModel per destination | ViewModel per Activity/Fragment/nav graph; never in custom Views or adapters |
| Get ViewModel | `hiltViewModel()` / `viewModel()` | `by viewModels()`, `by activityViewModels()`, `by hiltNavGraphViewModels(R.id.graph)` |
| Single activity + navigation | Navigation 3 | Navigation component with Fragments (recommended) |
| UI element state | `remember`/`rememberSaveable`, plain state holders | View state + `onSaveInstanceState`, plain classes owned by the Fragment |
| Bindings | — | View Binding (preferred over `findViewById`/synthetics); avoid putting logic in Data Binding expressions |

Fragment template:
```kotlin
@AndroidEntryPoint
class NewsFragment : Fragment(R.layout.fragment_news) {
    private val viewModel: NewsViewModel by viewModels()
    private var _binding: FragmentNewsBinding? = null
    private val binding get() = _binding!!

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        _binding = FragmentNewsBinding.bind(view)
        val adapter = NewsAdapter(onBookmarkClick = viewModel::toggleBookmark) // lambda, not the VM
        binding.list.adapter = adapter

        viewLifecycleOwner.lifecycleScope.launch {
            viewLifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
                viewModel.uiState.collect { state ->
                    binding.progress.isVisible = state.isLoading
                    adapter.submitList(state.items)
                    state.userMessage?.let { msg ->
                        Snackbar.make(view, msg.resolve(requireContext()), Snackbar.LENGTH_SHORT).show()
                        viewModel.userMessageShown(msg.id)
                    }
                }
            }
        }
    }

    override fun onDestroyView() { _binding = null; super.onDestroyView() }
}
```

Views-specific red flags:
- `lifecycleScope.launch { flow.collect {} }` / `launchWhenStarted` without
  `repeatOnLifecycle` → collection continues in background or is deprecated.
- Using the Fragment's `lifecycleScope`/`this` instead of `viewLifecycleOwner` for UI
  collection → leaks/crashes after `onDestroyView`.
- Passing the ViewModel into a `RecyclerView.Adapter` or custom View.
- Holding `binding`/View references in the ViewModel.
- `LiveData` + `SingleLiveEvent` for navigation/toasts → model as UI state.
- Business logic in `onClick` listeners → call a ViewModel function.
- `AndroidViewModel` to get resources → resolve in the Fragment.
