package com.example.news

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import kotlinx.coroutines.runBlocking

class MainActivity : ComponentActivity() {
    private lateinit var viewModel: NewsViewModel

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val api = RetrofitFactory.create<NewsApi>()
        val dao = AppDatabase.get(this).articleDao()
        viewModel = ViewModelProvider(this, object : ViewModelProvider.Factory {
            override fun <T : ViewModel> create(modelClass: Class<T>): T =
                NewsViewModel(application, api, dao) as T
        })[NewsViewModel::class.java]
        setContent {
            NewsScreen(viewModel = viewModel, onOpenArticle = { article ->
                startActivity(ArticleActivity.intent(this, article))
            })
        }
    }

    override fun onResume() {
        super.onResume()
        runBlocking { viewModel.loadNews() }
    }
}
