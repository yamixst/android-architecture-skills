package com.example.auth

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

sealed interface LoginEvent {
    data object NavigateToHome : LoginEvent
    data class ShowSnackbar(val message: String) : LoginEvent
}

@HiltViewModel
class LoginViewModel @Inject constructor(
    @ApplicationContext private val context: Context,
    private val authRepository: AuthRepository,
) : ViewModel() {

    val email = MutableStateFlow("")
    val password = MutableStateFlow("")
    val isLoading = MutableStateFlow(false)

    private val _events = Channel<LoginEvent>(Channel.BUFFERED)
    val events = _events.receiveAsFlow()

    fun onLoginClick() {
        viewModelScope.launch {
            isLoading.value = true
            try {
                authRepository.login(email.value, password.value)
                _events.send(LoginEvent.NavigateToHome)
            } catch (e: Exception) {
                _events.send(LoginEvent.ShowSnackbar(context.getString(R.string.login_failed)))
            } finally {
                isLoading.value = false
            }
        }
    }
}
