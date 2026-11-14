package com.desolate.elisium

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.desolate.elisium.service.extractUrls
import com.desolate.elisium.ui.theme.ElisiumTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private var shareMessage by mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as ElisiumApp
        setContent {
            ElisiumTheme {
                val state by app.engine.collectAsStateWithLifecycle()
                HomeScreen(state, shareMessage)
            }
        }
        // A recreated activity (rotation) must not queue the same share twice.
        if (savedInstanceState == null) handleShare(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleShare(intent)
    }

    /** Share-sheet intake: `ACTION_SEND` + `text/plain` -> links go to the queue with the default preset. */
    private fun handleShare(intent: Intent?) {
        if (intent?.action != Intent.ACTION_SEND || intent.type != "text/plain") return
        val urls = extractUrls(intent.getCharSequenceExtra(Intent.EXTRA_TEXT)?.toString())
        val app = application as ElisiumApp
        app.scope.launch { shareMessage = app.addLinks(urls) }
    }
}

@Composable
fun HomeScreen(state: EngineState, shareMessage: String? = null) {
    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(
            modifier = Modifier.padding(24.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(
                text = stringResource(R.string.app_name),
                style = MaterialTheme.typography.headlineLarge,
                color = MaterialTheme.colorScheme.onBackground,
            )
            val status = when (state) {
                EngineState.Starting -> stringResource(R.string.engine_starting)
                is EngineState.Ready -> stringResource(R.string.engine_ready, state.ytDlpVersion)
                is EngineState.Failed -> stringResource(R.string.engine_failed, state.message)
            }
            Text(
                text = status,
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onBackground,
                modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
            )
            if (shareMessage != null) {
                Text(
                    text = shareMessage,
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onBackground,
                    modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite },
                )
            }
        }
    }
}
