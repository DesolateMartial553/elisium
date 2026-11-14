package com.desolate.elisium

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.runtime.getValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.desolate.elisium.ui.ElisiumShell
import com.desolate.elisium.ui.ElisiumViewModel
import com.desolate.elisium.ui.theme.ElisiumTheme

class MainActivity : ComponentActivity() {
    private val vm: ElisiumViewModel by viewModels { ElisiumViewModel.Factory(application as ElisiumApp) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val app = application as ElisiumApp
        setContent {
            ElisiumTheme {
                val state by app.engine.collectAsStateWithLifecycle()
                ElisiumShell(vm, state)
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

    /**
     * Share-sheet intake: `ACTION_SEND` + `text/plain` -> links go to the queue with the saved settings.
     * The confirmation line arrives as a Snackbar (a live region), like links added in the app.
     */
    private fun handleShare(intent: Intent?) {
        if (intent?.action != Intent.ACTION_SEND || intent.type != "text/plain") return
        vm.queue.addFromText(intent.getCharSequenceExtra(Intent.EXTRA_TEXT)?.toString())
    }
}
