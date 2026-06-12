from __future__ import annotations

import argparse
import logging
import os
import sys
import uvicorn

_log = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="R34 API Server Sidecar")
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the API server on (default: 8000)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host address to bind to (default: 127.0.0.1)"
    )
    parsed, _ = parser.parse_known_args(sys.argv[1:])

    _LOG_LEVEL = os.environ.get("R34_LOG_LEVEL", "INFO").upper()
    console_level = getattr(logging, _LOG_LEVEL, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    uvicorn.run("r34_client.server.app:app", host=parsed.host, port=parsed.port, log_level=_LOG_LEVEL.lower())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
