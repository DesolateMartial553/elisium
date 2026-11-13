package com.desolate.elisium

import android.app.Application
import com.yausername.aria2c.Aria2c
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** State of the bundled download engine (yt-dlp + ffmpeg + aria2c). */
sealed interface EngineState {
    data object Starting : EngineState
    data class Ready(val ytDlpVersion: String) : EngineState
    data class Failed(val message: String) : EngineState
}

class ElisiumApp : Application() {

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val _engine = MutableStateFlow<EngineState>(EngineState.Starting)
    val engine: StateFlow<EngineState> = _engine.asStateFlow()

    override fun onCreate() {
        super.onCreate()
        scope.launch {
            _engine.value = try {
                YoutubeDL.getInstance().init(this@ElisiumApp)
                FFmpeg.getInstance().init(this@ElisiumApp)
                Aria2c.getInstance().init(this@ElisiumApp)
                val version = YoutubeDL.version(this@ElisiumApp) ?: "unknown"
                EngineState.Ready(version)
            } catch (e: Exception) {
                EngineState.Failed(e.message ?: e.javaClass.simpleName)
            }
        }
    }
}
