package com.devaraj.maya

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import com.devaraj.maya.data.prefs.ThemeMode
import com.devaraj.maya.ui.MayaViewModel
import com.devaraj.maya.ui.main.MayaMainScreen
import com.devaraj.maya.ui.onboarding.OnboardingScreen
import com.devaraj.maya.ui.theme.MayaTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val app = application as MayaApp
            val viewModel: MayaViewModel = viewModel(
                factory = MayaViewModel.Factory(app.container.settingsStore),
            )
            val settings by viewModel.settings.collectAsStateWithLifecycle()

            val current = settings
            if (current == null) {
                // DataStore is still loading: keep the brand background, no flash.
                MayaTheme {
                    Surface(
                        modifier = Modifier.fillMaxSize(),
                        color = MaterialTheme.colorScheme.background,
                    ) {
                        Box(modifier = Modifier.fillMaxSize())
                    }
                }
                return@setContent
            }

            val darkTheme = when (current.theme) {
                ThemeMode.DARK -> true
                ThemeMode.LIGHT -> false
                ThemeMode.SYSTEM -> isSystemInDarkTheme()
            }

            MayaTheme(darkTheme = darkTheme) {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    if (current.onboardingDone) {
                        MayaMainScreen(
                            themeMode = current.theme,
                            onThemeChange = viewModel::setTheme,
                        )
                    } else {
                        OnboardingScreen(onFinish = viewModel::completeOnboarding)
                    }
                }
            }
        }
    }
}
