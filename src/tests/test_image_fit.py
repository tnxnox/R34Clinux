from __future__ import annotations

import unittest

from r34_client.ui.helpers.image_fit import FitMode, compute_base_render_size


class ImageFitTests(unittest.TestCase):
    def test_original_mode_uses_source_size(self) -> None:
        size = compute_base_render_size(
            source_width=1920,
            source_height=1080,
            viewport_width=800,
            viewport_height=600,
            is_long_strip=False,
            fit_mode=FitMode.ORIGINAL,
        )
        self.assertEqual(size, (1920, 1080))

    def test_fit_width_mode_matches_viewport_width(self) -> None:
        width, height = compute_base_render_size(
            source_width=1000,
            source_height=500,
            viewport_width=700,
            viewport_height=300,
            is_long_strip=False,
            fit_mode=FitMode.FIT_WIDTH,
        )
        self.assertEqual(width, 700)
        self.assertEqual(height, 350)

    def test_fit_height_mode_matches_viewport_height(self) -> None:
        width, height = compute_base_render_size(
            source_width=1000,
            source_height=500,
            viewport_width=700,
            viewport_height=300,
            is_long_strip=False,
            fit_mode=FitMode.FIT_HEIGHT,
        )
        self.assertEqual(height, 300)
        self.assertEqual(width, 600)

    def test_smart_mode_for_long_strip_prefers_width(self) -> None:
        width, _ = compute_base_render_size(
            source_width=1000,
            source_height=4000,
            viewport_width=900,
            viewport_height=600,
            is_long_strip=True,
            fit_mode=FitMode.SMART,
        )
        self.assertEqual(width, 900)


if __name__ == "__main__":
    unittest.main()
