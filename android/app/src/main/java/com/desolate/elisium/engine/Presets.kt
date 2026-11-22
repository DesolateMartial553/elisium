package com.desolate.elisium.engine

/** One format preset (port of `presets.py`). */
data class Preset(
    val id: String,
    val label: String,
    val formatSelector: String,
    val extraArgs: List<String> = emptyList(),
)

object Presets {
    const val DEFAULT_ID = "best"

    private val list = listOf(
        Preset("best", "Best quality", "bestvideo*+bestaudio/best"),
        Preset("1080p", "1080p", "bestvideo*[height<=1080]+bestaudio/best[height<=1080]"),
        Preset("720p", "720p", "bestvideo*[height<=720]+bestaudio/best[height<=720]"),
        Preset("audio-mp3", "Audio only (MP3)", "bestaudio/best", listOf("-x", "--audio-format", "mp3")),
        Preset("audio-m4a", "Audio only (M4A)", "bestaudio[ext=m4a]/bestaudio/best", listOf("-x", "--audio-format", "m4a")),
        Preset("audio-opus", "Audio only (Opus)", "bestaudio[acodec=opus]/bestaudio/best", listOf("-x", "--audio-format", "opus")),
        Preset("audio-flac", "Audio only (FLAC)", "bestaudio/best", listOf("-x", "--audio-format", "flac")),
        Preset("smallest", "Smallest file", "wv*+wa/w"),
    )

    /** Presets in display order, keyed by id. */
    val PRESETS: Map<String, Preset> = list.associateBy { it.id }

    /** The preset for [id], falling back to `best` if unknown. */
    fun get(id: String?): Preset = if (id != null && id.isNotEmpty() && id in PRESETS) PRESETS.getValue(id) else PRESETS.getValue(DEFAULT_ID)
}
