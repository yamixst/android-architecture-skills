package com.example.news

import androidx.compose.foundation.clickable
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel

@Composable
fun NewsScreen(viewModel: NewsViewModel, onOpenArticle: (ArticleDto) -> Unit) {
    val articles by viewModel.articles.collectAsState()
    val loading by viewModel.isLoading.collectAsState()

    LaunchedEffect(Unit) {
        viewModel.loadNews()
        viewModel.events.collect { event ->
            when (event) {
                is NewsEvent.OpenArticle -> onOpenArticle(event.article)
            }
        }
    }

    if (loading) CircularProgressIndicator()
    LazyColumn {
        items(articles) { article ->
            ArticleRow(article = article, viewModel = viewModel)
        }
    }
}

@Composable
fun ArticleRow(article: ArticleDto, viewModel: NewsViewModel) {
    Text(
        text = article.title + if (article.isBookmarked) " ★" else "",
        modifier = Modifier.clickable { viewModel.onArticleClicked(article) },
    )
    Checkbox(
        checked = article.isBookmarked,
        onCheckedChange = { checked ->
            article.isBookmarked = checked
            if (checked) viewModel.bookmark(article)
        },
    )
}
