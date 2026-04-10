from __future__ import annotations

from enum import Enum


class FitMode(str, Enum):
    SMART = "smart"
    FIT_WIDTH = "fit_width"
    FIT_HEIGHT = "fit_height"
    ORIGINAL = "original"


def compute_base_render_size(
    *,
    source_width: int,
    source_height: int,
    viewport_width: int,
    viewport_height: int,
    is_long_strip: bool,
    fit_mode: FitMode,
) -> tuple[int, int]:
    if source_width <= 0 or source_height <= 0:
        return (1, 1)

    vw = max(1, int(viewport_width))
    vh = max(1, int(viewport_height))

    if fit_mode == FitMode.ORIGINAL:
        return (source_width, source_height)

    if fit_mode == FitMode.FIT_WIDTH:
        width = vw
        height = max(1, round((source_height * width) / source_width))
        return (width, height)

    if fit_mode == FitMode.FIT_HEIGHT:
        height = vh
        width = max(1, round((source_width * height) / source_height))
        return (width, height)

    # SMART mode: keep the existing behavior for long strips while fitting regular images.
    if is_long_strip:
        width = vw
        height = max(1, round((source_height * width) / source_width))
        return (width, height)

    fit_ratio = min(vw / source_width, vh / source_height)
    width = max(1, round(source_width * fit_ratio))
    height = max(1, round(source_height * fit_ratio))
    return (width, height)
