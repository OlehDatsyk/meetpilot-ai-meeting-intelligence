"""Stand-alone job worker: `python -m app.worker`. Use with EMBEDDED_WORKER=false on the API."""

from __future__ import annotations

import logging
import signal

from .config import get_settings
from .jobs import Worker
from .logging_setup import configure_logging


def main() -> None:
    configure_logging(get_settings().log_level)
    worker = Worker()

    def _stop(*_):
        logging.getLogger("meetpilot.worker").info("Shutdown requested; finishing the current step")
        worker._stop.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    worker.loop()


if __name__ == "__main__":
    main()
