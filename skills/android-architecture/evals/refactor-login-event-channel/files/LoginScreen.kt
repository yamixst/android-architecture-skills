package com.example.auth

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.hilt.navigation.compose.hiltViewModel

@Composable
fun LoginScreen(
    snackbarHostState: SnackbarHostState,
    onLoggedIn: () -> Unit,
    viewModel: LoginViewModel = hiltViewModel(),
) {
    val email by viewModel.email.collectAsState()
    val password by viewModel.password.collectAsState()
    val isLoading by viewModel.isLoading.collectAsState()

    LaunchedEffect(Unit) {
        viewModel.events.collect { event ->
            when (event) {
                LoginEvent.NavigateToHome -> onLoggedIn()
                is LoginEvent.ShowSnackbar -> snackbarHostState.showSnackbar(event.message)
            }
        }
    }

    Column {
        OutlinedTextField(value = email, onValueChange = { viewModel.email.value = it }, label = { Text("Email") })
        OutlinedTextField(value = password, onValueChange = { viewModel.password.value = it }, label = { Text("Password") })
        if (isLoading) CircularProgressIndicator()
        Button(onClick = viewModel::onLoginClick, enabled = !isLoading) { Text("Log in") }
    }
}
