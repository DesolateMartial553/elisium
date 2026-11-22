package com.desolate.elisium.storage

import org.junit.Assert.assertEquals
import org.junit.Test

class OwnerFolderTest {
    @Test fun noOwnerKeepsTheFlatFolder() {
        assertEquals("Download/Elisium/", relativePathFor(null))
        assertEquals("Download/Elisium/", relativePathFor(""))
        assertEquals("Download/Elisium/", relativePathFor("   "))
        assertEquals("Download/Elisium/", relativePathFor(".."))
        assertEquals("Elisium", folderPathFor(null))
    }

    @Test fun anOwnerGetsOneSubfolder() {
        assertEquals("Download/Elisium/dancer/", relativePathFor("dancer"))
        assertEquals("Download/Elisium/Some Owner/", relativePathFor("  Some Owner  "))
        assertEquals("Elisium/dancer", folderPathFor("dancer"))
    }

    @Test fun anOwnerNameCanNeverClimbOutOrAddALevel() {
        assertEquals("Download/Elisium/a_b/", relativePathFor("a/b"))
        assertEquals("Download/Elisium/_etc/", relativePathFor("../etc"))
        for (name in listOf("../etc", "..\\x", "/abs", "a/../b")) {
            val path = relativePathFor(name)
            assertEquals(name, 3, path.trimEnd('/').split('/').size) // Download / Elisium / <one name>
            assertEquals(name, false, path.trimEnd('/').split('/').any { it == ".." || it == "." })
        }
    }
}
