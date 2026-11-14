package com.desolate.elisium.ui

import com.desolate.elisium.engine.ErrorInfo
import com.desolate.elisium.engine.QueueItem
import com.desolate.elisium.service.WAITING_FOR_WIFI
import com.desolate.elisium.ui.downloads.Banner
import com.desolate.elisium.ui.downloads.CancelPrompt
import com.desolate.elisium.ui.downloads.QueueGateway
import com.desolate.elisium.ui.downloads.QueueViewModel
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class FakeGateway : QueueGateway {
    override val items = MutableStateFlow<List<QueueItem>>(emptyList())
    override val holdReason = MutableStateFlow<String?>(null)
    override val serviceError = MutableStateFlow<String?>(null)
    val calls = ArrayList<String>()
    val added = ArrayList<List<String>>()

    override suspend fun addLinks(urls: List<String>): String {
        added.add(urls)
        return if (urls.isEmpty()) "No links found in the shared text" else "Added ${urls.size} links"
    }

    override fun pause(id: Int) { calls.add("pause $id") }
    override fun resume(id: Int) { calls.add("resume $id") }
    override fun retry(id: Int) { calls.add("retry $id") }
    override fun cancel(id: Int) { calls.add("cancel $id") }
    override fun pauseAll() { calls.add("pauseAll") }
    override fun cancelAll() { calls.add("cancelAll") }
}

@OptIn(ExperimentalCoroutinesApi::class)
class QueueViewModelTest {
    @Test fun rowsFollowTheQueue() = runTest(UnconfinedTestDispatcher()) {
        val gw = FakeGateway()
        val vm = QueueViewModel(gw, backgroundScope)
        assertTrue(vm.rows.value.isEmpty())
        assertFalse(vm.hasUnfinished.value)
        gw.items.value = listOf(queueItem(1, "downloading", title = "A", percent = 10.0), queueItem(2, "done"))
        assertEquals(listOf("A", "https://example.com/v/2"), vm.rows.value.map { it.title })
        assertTrue(vm.hasUnfinished.value)
        gw.items.value = listOf(queueItem(2, "done"))
        assertFalse(vm.hasUnfinished.value)
    }

    @Test fun bannerFollowsHoldAndServiceError() = runTest(UnconfinedTestDispatcher()) {
        val gw = FakeGateway()
        val vm = QueueViewModel(gw, backgroundScope)
        assertNull(vm.banner.value)
        gw.holdReason.value = WAITING_FOR_WIFI
        assertEquals(Banner.WaitingForWifi, vm.banner.value)
        gw.serviceError.value = "boom"
        assertEquals(Banner.ServiceProblem("boom"), vm.banner.value)
        gw.serviceError.value = null
        gw.holdReason.value = null
        assertNull(vm.banner.value)
    }

    @Test fun pastedTextWithSeveralLinksQueuesAllAndConfirms() = runTest(UnconfinedTestDispatcher()) {
        val gw = FakeGateway()
        val vm = QueueViewModel(gw, backgroundScope)
        val sawAdd = ArrayList<Int>()
        val job = launch { vm.linksAdded.collect { sawAdd.add(it) } }
        val ok = vm.addFromText("Watch https://a.example/1 and also (https://b.example/2).")
        assertTrue(ok)
        assertEquals(listOf(listOf("https://a.example/1", "https://b.example/2")), gw.added)
        assertEquals("Added 2 links", vm.messages.first())
        assertEquals(listOf(2), sawAdd)
        job.cancel()
    }

    @Test fun textWithoutLinksKeepsTheFieldAndSaysSo() = runTest(UnconfinedTestDispatcher()) {
        val gw = FakeGateway()
        val vm = QueueViewModel(gw, backgroundScope)
        assertFalse(vm.addFromText("just words"))
        assertEquals("No links found in the shared text", vm.messages.first())
    }

    @Test fun simpleActionsGoStraightToTheQueue() = runTest(UnconfinedTestDispatcher()) {
        val gw = FakeGateway()
        val vm = QueueViewModel(gw, backgroundScope)
        vm.pause(1); vm.resume(2); vm.retry(3); vm.pauseAll()
        assertEquals(listOf("pause 1", "resume 2", "retry 3", "pauseAll"), gw.calls)
    }

    @Test fun cancelAsksOnlyForActiveItems() = runTest(UnconfinedTestDispatcher()) {
        val gw = FakeGateway()
        val vm = QueueViewModel(gw, backgroundScope)
        gw.items.value = listOf(queueItem(1, "queued"), queueItem(2, "paused"), queueItem(3, "downloading", title = "Big one"))
        vm.requestCancel(1)
        vm.requestCancel(2)
        assertEquals(listOf("cancel 1", "cancel 2"), gw.calls)
        assertNull(vm.cancelPrompt.value)

        vm.requestCancel(3)
        assertEquals(CancelPrompt.One(3, "Big one"), vm.cancelPrompt.value)
        assertEquals(2, gw.calls.size)
        vm.dismissCancel()
        assertNull(vm.cancelPrompt.value)
        assertEquals(2, gw.calls.size)

        vm.requestCancel(3)
        vm.confirmCancel()
        assertEquals("cancel 3", gw.calls.last())
        assertNull(vm.cancelPrompt.value)
    }

    @Test fun cancelAllConfirmsAndIgnoresAnEmptyList() = runTest(UnconfinedTestDispatcher()) {
        val gw = FakeGateway()
        val vm = QueueViewModel(gw, backgroundScope)
        vm.requestCancelAll()
        assertNull(vm.cancelPrompt.value)
        gw.items.value = listOf(queueItem(1, "queued"))
        vm.requestCancelAll()
        assertEquals(CancelPrompt.All, vm.cancelPrompt.value)
        vm.confirmCancel()
        assertEquals(listOf("cancelAll"), gw.calls)
    }

    @Test fun unknownRowCancelDoesNothing() = runTest(UnconfinedTestDispatcher()) {
        val gw = FakeGateway()
        val vm = QueueViewModel(gw, backgroundScope)
        vm.requestCancel(99)
        assertTrue(gw.calls.isEmpty())
        assertNull(vm.cancelPrompt.value)
    }

    @Test fun announcementTracksStateChanges() = runTest(UnconfinedTestDispatcher()) {
        val gw = FakeGateway()
        val vm = QueueViewModel(gw, backgroundScope)
        gw.items.value = listOf(queueItem(1, "downloading", title = "A", percent = 5.0))
        assertEquals("", vm.announcement.value)
        gw.items.value = listOf(queueItem(1, "downloading", title = "A", percent = 30.0))
        assertEquals("A, 25 percent", vm.announcement.value)
        gw.items.value = listOf(queueItem(1, "failed", title = "A", error = ErrorInfo("Network problem.", "f", "network")))
        assertEquals("A: failed. Network problem.", vm.announcement.value)
    }
}
