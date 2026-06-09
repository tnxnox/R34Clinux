from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from r34_client.core.download_manager import DownloadManager
from r34_client.core.models import Post
from r34_client.core.settings import AppSettings


class ValidatePathWithinBaseTests(unittest.TestCase):
    """Tests for DownloadManager._validate_path_within_base."""

    def setUp(self) -> None:
        self.db = MagicMock()
        self.dm = DownloadManager(db=self.db)

    def test_rejects_path_outside_base(self) -> None:
        """Path traversal: a path outside the base directory should raise ValueError."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "downloads"
            base.mkdir()
            outside = Path(td) / "elsewhere" / "file.txt"
            outside.parent.mkdir()

            with self.assertRaises(ValueError) as ctx:
                self.dm._validate_path_within_base(outside, base)
            self.assertIn("Path traversal detected", str(ctx.exception))

    def test_accepts_path_inside_base(self) -> None:
        """A path inside the base directory should pass without error."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "downloads"
            base.mkdir()
            inside = base / "sub" / "file.txt"
            inside.parent.mkdir()

            # Should not raise
            self.dm._validate_path_within_base(inside, base)

    def test_rejects_parent_dotdot_traversal(self) -> None:
        """A path using .. to escape base should be rejected."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "downloads"
            base.mkdir()
            # A path that resolves outside
            traversal = base / ".." / "escape.txt"
            traversal.parent.resolve().mkdir(parents=True, exist_ok=True)
            traversal.touch()

            with self.assertRaises(ValueError):
                self.dm._validate_path_within_base(traversal, base)


class SanitizePathSegmentTests(unittest.TestCase):
    """Tests for DownloadManager._sanitize_path_segment."""

    def setUp(self) -> None:
        self.db = MagicMock()
        self.dm = DownloadManager(db=self.db)

    def test_strips_dangerous_chars(self) -> None:
        """Characters like slashes, null bytes, angle brackets are removed."""
        dirty = "a/b\\c<d>e:f|g*h?\""
        clean = self.dm._sanitize_path_segment(dirty)
        self.assertEqual(clean, "abcdefgh")

    def test_allows_alphanumeric_and_safe_chars(self) -> None:
        """Letters, digits, spaces, dots, underscores, and dashes are kept."""
        safe = "Hello World_123.test-file"
        clean = self.dm._sanitize_path_segment(safe)
        self.assertEqual(clean, safe)

    def test_strips_leading_trailing_dot_and_space(self) -> None:
        """Leading/trailing dots and spaces are stripped."""
        dirty = " . myfile . "
        clean = self.dm._sanitize_path_segment(dirty)
        self.assertEqual(clean, "myfile")

    def test_returns_empty_for_all_dangerous(self) -> None:
        """A segment made entirely of dangerous chars returns empty."""
        dirty = "<>:\"/|?*"
        clean = self.dm._sanitize_path_segment(dirty)
        self.assertEqual(clean, "")


class FormatFilenameTests(unittest.TestCase):
    """Tests for DownloadManager.format_filename."""

    def setUp(self) -> None:
        self.db = MagicMock()
        self.dm = DownloadManager(db=self.db)

    def _make_post(
        self,
        post_id: int = 42,
        file_url: str = "https://img.example.com/images/photo123.jpg",
        sample_url: str = "",
        md5: str = "abc123def",
        score: int = 100,
        rating: str = "s",
    ) -> Post:
        return Post.from_payload(
            {
                "id": post_id,
                "file_url": file_url,
                "sample_url": sample_url,
                "preview_url": "https://img.example.com/previews/preview.jpg",
                "tags": "tag1 tag2",
                "rating": rating,
                "score": score,
                "md5": md5,
            }
        )

    def test_extension_from_file_url(self) -> None:
        """Extension is extracted from the file_url."""
        post = self._make_post(file_url="https://img.example.com/img/hello.png")
        name = self.dm.format_filename(post, template="{id}")
        self.assertTrue(name.endswith(".png"))

    def test_extension_from_sample_url_when_use_sample(self) -> None:
        """When use_sample=True, extension comes from sample_url."""
        post = self._make_post(
            file_url="https://img.example.com/img/full.jpg",
            sample_url="https://img.example.com/img/sample.webp",
        )
        name = self.dm.format_filename(post, template="{id}", use_sample=True)
        self.assertTrue(name.endswith(".webp"))

    def test_fallback_extension_when_no_url(self) -> None:
        """When both file_url and sample_url are empty, fallback to .jpg."""
        post = self._make_post(
            file_url="",
            sample_url="",
        )
        # No file_url or sample_url — it falls back to preview_url
        # Which in our _make_post is set
        # So it should get .jpg from preview_url if preview_url has no ext,
        # but preview_url ends with .jpg in our fixture, so it gets .jpg
        name = self.dm.format_filename(post, template="{id}")
        self.assertTrue(name.endswith(".jpg"))

    def test_template_substitution_id(self) -> None:
        """Template {id} is replaced with the post id."""
        post = self._make_post(post_id=77)
        name = self.dm.format_filename(post, template="{id}")
        self.assertEqual(name, "77.jpg")

    def test_template_substitution_md5(self) -> None:
        """Template {md5} is replaced with the post md5."""
        post = self._make_post(md5="deadbeef123")
        name = self.dm.format_filename(post, template="{md5}")
        self.assertEqual(name, "deadbeef123.jpg")

    def test_template_substitution_score(self) -> None:
        """Template {score} is replaced with the post score."""
        post = self._make_post(score=999)
        name = self.dm.format_filename(post, template="{score}")
        self.assertEqual(name, "999.jpg")

    def test_template_substitution_rating(self) -> None:
        """Template {rating} is replaced with the post rating."""
        post = self._make_post(rating="q")
        name = self.dm.format_filename(post, template="{rating}")
        self.assertEqual(name, "q.jpg")

    def test_combined_template(self) -> None:
        """Multiple template placeholders are substituted correctly."""
        post = self._make_post(post_id=5, md5="abc", score=50, rating="e")
        name = self.dm.format_filename(post, template="{id}_{md5}_{score}_{rating}")
        self.assertEqual(name, "5_abc_50_e.jpg")

    def test_sanitized_output(self) -> None:
        """Template output is sanitized — dangerous chars in md5 etc. get stripped."""
        post = self._make_post(md5="a<b>c:d")
        name = self.dm.format_filename(post, template="{md5}")
        self.assertEqual(name, "abcd.jpg")


class CheckDiskSpaceTests(unittest.TestCase):
    """Tests for DownloadManager._check_disk_space."""

    def setUp(self) -> None:
        self.db = MagicMock()
        self.dm = DownloadManager(db=self.db)

    def test_does_not_crash_when_path_does_not_exist(self) -> None:
        """_check_disk_space should log a warning but not crash when parent doesn't exist."""
        # A path with a non-existent parent should not crash
        dest = Path("/tmp/nonexistent_dir_xy12345/downloads/file.jpg")
        try:
            self.dm._check_disk_space(dest, 1024)
        except Exception as e:
            self.fail(f"_check_disk_space raised unexpectedly: {e}")

    def test_raises_on_insufficient_space(self) -> None:
        """_check_disk_space raises RuntimeError when there's not enough free space."""
        with patch("shutil.disk_usage") as mock_du:
            # Create a mock stat result with very little free space
            mock_stat = MagicMock()
            mock_stat.free = 100  # 100 bytes free
            mock_du.return_value = mock_stat

            dest = Path("/tmp/existing_dir/file.jpg")
            dest.parent.mkdir(parents=True, exist_ok=True)

            with self.assertRaises(RuntimeError) as ctx:
                self.dm._check_disk_space(dest, 1024 * 1024)  # 1 MB required
            self.assertIn("Insufficient disk space", str(ctx.exception))

    def test_does_not_raise_when_sufficient_space(self) -> None:
        """_check_disk_space passes silently when there's enough free space."""
        with patch("shutil.disk_usage") as mock_du:
            mock_stat = MagicMock()
            mock_stat.free = 100 * 1024 * 1024  # 100 MB free
            mock_du.return_value = mock_stat

            dest = Path("/tmp/existing_dir/file2.jpg")
            try:
                self.dm._check_disk_space(dest, 1024)  # 1 KB required
            except Exception as e:
                self.fail(f"_check_disk_space raised unexpectedly: {e}")
