package com.example.news

import android.app.Application
import android.content.Context
import android.widget.Toast
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.GlobalScope
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class NewsViewModel(
    application: Application,
    private val newsApi: NewsApi,
    private val articleDao: ArticleDao,
) : AndroidViewModel(application) {

    val articles = MutableStateFlow<List<ArticleDto>>(emptyList())
    val isLoading = MutableStateFlow(false)
    val error = MutableStateFlow<String?>(null)

    private val _events = Channel<NewsEvent>()
    val events = _events.receiveAsFlow()

    private val context: Context get() = getApplication()

    fun loadNews() {
        viewModelScope.launch {
            isLoading.value = true
            try {
                val result = withContext(Dispatchers.IO) { newsApi.getLatestNews() }
                articles.value = result
                withContext(Dispatchers.IO) { articleDao.insertAll(result.map { it.toEntity() }) }
            } catch (e: Exception) {
                error.value = context.getString(R.string.error_loading_news)
            }
            isLoading.value = false
        }
    }

    fun onArticleClicked(article: ArticleDto) {
        viewModelScope.launch { _events.send(NewsEvent.OpenArticle(article)) }
    }

    fun bookmark(article: ArticleDto) {
        GlobalScope.launch {
            articleDao.setBookmarked(article.id, true)
        }
        Toast.makeText(context, "Bookmarked", Toast.LENGTH_SHORT).show()
    }
}

sealed class NewsEvent {
    data class OpenArticle(val article: ArticleDto) : NewsEvent()
}
