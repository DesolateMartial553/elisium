package com.desolate.elisium.ui.settings

import android.annotation.SuppressLint
import android.graphics.Bitmap
import android.graphics.Color as AndroidColor
import android.os.Build
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebStorage
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBars
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.desolate.elisium.R
import com.desolate.elisium.settings.hasInstagramSession
import com.desolate.elisium.settings.loginHostAllowed
import com.desolate.elisium.settings.toNetscape
import java.util.concurrent.atomic.AtomicBoolean
import kotlinx.coroutines.delay

/** Where the sign-in page starts. */
private const val LOGIN_URL = "https://www.instagram.com/accounts/login/"

/** The origin whose cookies are read once the page has loaded. */
private const val COOKIE_ORIGIN = "https://www.instagram.com"

/** How often the cookie store is checked while the screen is shown. */
private const val SESSION_POLL_MS = 1_000L

/** Where the sign-in page is: still loading, shown, or failed with a short reason. */
private sealed interface PageState {
    data object Loading : PageState
    data object Shown : PageState
    data class Failed(val reason: String) : PageState
}

/** Holds the live [WebView] so the poll and the disposal can reach it without a recomposition. */
private class WebViewHolder {
    var view: WebView? = null
}

/**
 * Full-screen sign-in on Instagram's own page. The app never sees the password: it only watches its
 * own cookie store (never the page), and once a `sessionid` cookie appears it writes a Netscape
 * cookies.txt through [onSession], clears the WebView's cookies, storage and cache, and closes.
 *
 * Compile-verified only: a real WebView needs a device, so the parts that can be JVM-tested live in
 * `InstagramSession.kt` (parsing, session detection, file shape, navigation guard).
 */
@SuppressLint("SetJavaScriptEnabled")
@Composable
fun InstagramLoginScreen(
    onSession: (String) -> Unit,
    onClose: () -> Unit,
    modifier: Modifier = Modifier,
) {
    // Exactly one hand-over, even if the page-finished callback and the poll fire together.
    val done = remember { AtomicBoolean(false) }
    val holder = remember { WebViewHolder() }
    val sessionNow = rememberUpdatedState(onSession)
    val closeNow = rememberUpdatedState(onClose)
    var page by remember { mutableStateOf<PageState>(PageState.Loading) }

    // Reads the app's cookie store only: no script is injected and the page is never inspected.
    val check: (WebView) -> Unit = { view ->
        if (!done.get()) {
            val header = CookieManager.getInstance().getCookie(COOKIE_ORIGIN)
            if (header != null && hasInstagramSession(header)) {
                if (done.compareAndSet(false, true)) {
                    sessionNow.value(toNetscape(header, System.currentTimeMillis() / 1000))
                    clearSignIn(view)
                    closeNow.value()
                }
            }
        }
    }

    BackHandler { closeNow.value() }

    LaunchedEffect(Unit) {
        while (!done.get()) {
            delay(SESSION_POLL_MS)
            holder.view?.let(check)
        }
    }

    DisposableEffect(Unit) {
        onDispose {
            holder.view?.let { view ->
                (view.parent as? ViewGroup)?.removeView(view)
                view.stopLoading()
                view.destroy()
            }
            holder.view = null
        }
    }

    Surface(modifier = modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(Modifier.fillMaxSize()) {
            Row(
                modifier = Modifier.fillMaxWidth().windowInsetsPadding(WindowInsets.statusBars)
                    .padding(start = 4.dp, end = 16.dp, top = 4.dp, bottom = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(onClick = { closeNow.value() }) {
                    Icon(
                        Icons.AutoMirrored.Filled.ArrowBack,
                        contentDescription = stringResource(R.string.instagram_login_back),
                    )
                }
                Text(
                    text = stringResource(R.string.instagram_login_title),
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.semantics { heading() },
                )
            }
            Text(
                text = stringResource(R.string.instagram_login_explainer),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp),
            )
            if (page is PageState.Loading) {
                Text(
                    text = stringResource(R.string.instagram_login_loading),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(horizontal = 20.dp, vertical = 2.dp)
                        .semantics { liveRegion = LiveRegionMode.Polite },
                )
            }
            val failed = page as? PageState.Failed
            if (failed != null) {
                Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 8.dp)) {
                    Text(
                        text = stringResource(R.string.instagram_login_load_failed, failed.reason),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.error,
                        modifier = Modifier.semantics { liveRegion = LiveRegionMode.Assertive },
                    )
                    Spacer(Modifier.height(8.dp))
                    Button(onClick = {
                        page = PageState.Loading
                        holder.view?.loadUrl(LOGIN_URL)
                    }) { Text(stringResource(R.string.instagram_login_retry)) }
                }
            }
            val webViewName = stringResource(R.string.instagram_login_webview)
            // No clip() on the WebView: a rounded clip forces an off-screen layer that some devices render blank.
            Box(Modifier.fillMaxWidth().weight(1f).padding(horizontal = 12.dp).navigationBarsPadding()) {
                AndroidView(
                    factory = { context ->
                        WebView(context).apply {
                            // An opaque white page: a transparent WebView over the dark app theme looks like an empty box.
                            setBackgroundColor(AndroidColor.WHITE)
                            contentDescription = webViewName
                            settings.javaScriptEnabled = true
                            settings.domStorageEnabled = true
                            // Instagram shows an empty page to browsers it recognises as embedded.
                            settings.userAgentString = browserLikeUserAgent(settings.userAgentString)
                            CookieManager.getInstance().setAcceptCookie(true)
                            CookieManager.getInstance().setAcceptThirdPartyCookies(this, true)
                            keepPageLight(this)
                            webViewClient = object : WebViewClient() {
                                override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean =
                                    !loginHostAllowed(request.url?.toString())

                                override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
                                    if (page !is PageState.Failed) page = PageState.Loading
                                }

                                override fun onPageFinished(view: WebView, url: String?) {
                                    if (page !is PageState.Failed) page = PageState.Shown
                                    check(view)
                                }

                                override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                                    if (request.isForMainFrame) {
                                        page = PageState.Failed(loginErrorReason(error.errorCode, error.description))
                                    }
                                }

                                override fun onReceivedHttpError(view: WebView, request: WebResourceRequest, errorResponse: WebResourceResponse) {
                                    if (request.isForMainFrame && loginHttpIsFailure(errorResponse.statusCode)) {
                                        page = PageState.Failed(loginHttpReason(errorResponse.statusCode))
                                    }
                                }
                            }
                            holder.view = this
                            loadUrl(LOGIN_URL)
                        }
                    },
                    modifier = Modifier.fillMaxSize(),
                )
            }
            Spacer(Modifier.height(8.dp))
        }
    }
}

/** Drops everything the sign-in page left behind, so the session lives only in the cookies.txt. */
private fun clearSignIn(view: WebView) {
    val cookies = CookieManager.getInstance()
    cookies.removeAllCookies(null)
    cookies.flush()
    WebStorage.getInstance().deleteAllData()
    view.clearCache(true)
    view.stopLoading()
}

/** Keeps Instagram's own page as it is: no forced or algorithmic dark mode on top of it. */
@Suppress("DEPRECATION")
private fun keepPageLight(view: WebView) {
    if (Build.VERSION.SDK_INT >= 33) {
        view.settings.isAlgorithmicDarkeningAllowed = false
    } else if (Build.VERSION.SDK_INT >= 29) {
        view.settings.forceDark = WebSettings.FORCE_DARK_OFF
    }
}
