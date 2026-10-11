package com.example.news

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import retrofit2.http.GET

data class ArticleDto(
    val id: String,
    val title: String,
    val body: String,
    val authorJson: String,
    var isBookmarked: Boolean = false,
)

data class ArticleEntity(val id: String, val title: String, val body: String, val bookmarked: Boolean)

fun ArticleDto.toEntity() = ArticleEntity(id, title, body, isBookmarked)

interface NewsApi {
    @GET("news/latest")
    fun getLatestNews(): List<ArticleDto>
}

@Dao
interface ArticleDao {
    @Insert
    fun insertAll(items: List<ArticleEntity>)

    @Query("UPDATE articles SET bookmarked = :bookmarked WHERE id = :id")
    fun setBookmarked(id: String, bookmarked: Boolean)
}

object NewsRepository {
    var cache: List<ArticleDto> = emptyList()
}
