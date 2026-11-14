package com.desolate.elisium.ui.components

import org.junit.Assert.assertEquals
import org.junit.Test

class StateChipTest {
    @Test fun everyStateHasAKind() {
        assertEquals(ChipKind.Active, chipKindOf("downloading"))
        assertEquals(ChipKind.Working, chipKindOf("merging"))
        assertEquals(ChipKind.Working, chipKindOf("probing"))
        assertEquals(ChipKind.Paused, chipKindOf("paused"))
        assertEquals(ChipKind.Done, chipKindOf("done"))
        assertEquals(ChipKind.Failed, chipKindOf("failed"))
        assertEquals(ChipKind.Stopped, chipKindOf("cancelled"))
        assertEquals(ChipKind.Waiting, chipKindOf("queued"))
        assertEquals(ChipKind.Waiting, chipKindOf("something new"))
    }
}
