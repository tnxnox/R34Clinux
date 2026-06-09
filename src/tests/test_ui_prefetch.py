from __future__ import annotations

import tempfile
import unittest
import time
from pathlib import Path
from r34_client.ui.helpers.prefetch import ImageCache


class ImageCacheDiskTests(unittest.TestCase):
    def test_memory_and_disk_cache_flow(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            # Initialize with custom cache dir and limits
            cache = ImageCache(max_size=2, max_disk_size_bytes=1000)
            cache.cache_dir = Path(td)
            
            # Put 1st item
            cache.put(1, b"one")
            
            # Since put runs writing in a background thread, we wait a tiny bit for it to write
            time.sleep(0.1)
            
            # Get should retrieve from memory/disk
            self.assertEqual(cache.get(1), b"one")
            
            # Put 2nd and 3rd items. Memory limit is 2.
            # So 1st item should be evicted from memory but remain on disk.
            cache.put(2, b"two")
            time.sleep(0.02)
            cache.put(3, b"three")
            
            time.sleep(0.1)
            
            # Disk count is 3
            self.assertEqual(cache.size, 3)
            
            # Get 1 should read from disk and bring it back to memory
            self.assertEqual(cache.get(1), b"one")
            
            # Verify contains method works for both memory and disk
            self.assertTrue(cache.contains(1))
            self.assertTrue(cache.contains(2))
            
            # Remove from cache
            cache.remove(2)
            self.assertFalse(cache.contains(2))
            
            # Invalidate clears all
            cache.invalidate()
            self.assertEqual(cache.size, 0)
            self.assertFalse(cache.contains(1))
            self.assertFalse(cache.contains(3))

    def test_disk_lru_eviction(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            # Set disk limit to 10 bytes
            cache = ImageCache(max_size=5, max_disk_size_bytes=10)
            cache.cache_dir = Path(td)
            
            # Put items: each is 4 bytes
            cache.put(1, b"1234")
            time.sleep(0.05)
            cache.put(2, b"5678")
            time.sleep(0.05)
            # Total size on disk is now 8 bytes.
            
            # Put a 3rd item (4 bytes). Total would be 12 bytes (> 10 bytes).
            # This should trigger eviction of the oldest (item 1).
            cache.put(3, b"9abc")
            time.sleep(0.1)
            
            self.assertFalse((cache.cache_dir / "1").exists())
            self.assertTrue((cache.cache_dir / "2").exists())
            self.assertTrue((cache.cache_dir / "3").exists())
