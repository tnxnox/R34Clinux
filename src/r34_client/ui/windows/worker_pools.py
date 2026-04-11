from __future__ import annotations

import os

from PySide6.QtCore import QThreadPool


def build_worker_pools() -> dict[str, QThreadPool]:
    cpu_count = max(1, os.cpu_count() or 1)
    pools: dict[str, QThreadPool] = {
        "general": QThreadPool.globalInstance(),
        "search": QThreadPool(),
        "preview": QThreadPool(),
        "sync": QThreadPool(),
        "mutation": QThreadPool(),
        "autocomplete": QThreadPool(),
        "download": QThreadPool(),
    }
    pools["general"].setMaxThreadCount(max(8, min(24, cpu_count * 3)))
    pools["search"].setMaxThreadCount(max(2, min(6, cpu_count)))
    pools["preview"].setMaxThreadCount(max(2, min(8, cpu_count * 2)))
    pools["sync"].setMaxThreadCount(max(1, min(4, cpu_count)))
    pools["mutation"].setMaxThreadCount(1)
    pools["autocomplete"].setMaxThreadCount(max(1, min(3, cpu_count)))
    pools["download"].setMaxThreadCount(max(2, min(6, cpu_count)))
    return pools
