"""Colored, timing-friendly logging setup (ported from bike_dash).

`setup_logging()` installs a single stderr handler whose formatter colorizes the
level and logger name (only when attached to a TTY — files/CI stay clean). The
`timed()` helper wraps a block of work and emits a "… done in 123ms" line, used
to time external API calls and internal agent steps.
"""

from __future__ import annotations

import contextlib
import logging
import sys
import time
from typing import Iterator


# --- ANSI palette --------------------------------------------------------- #
class _C:
    RESET = "\033[0m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    GRAY = "\033[90m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    BOLD_RED = "\033[1;31m"


_LEVEL_COLOR = {
    logging.DEBUG: _C.CYAN,
    logging.INFO: _C.GREEN,
    logging.WARNING: _C.YELLOW,
    logging.ERROR: _C.RED,
    logging.CRITICAL: _C.BOLD_RED,
}


class ColorFormatter(logging.Formatter):
    """Formats `HH:MM:SS.mmm LEVEL [logger] message` with optional ANSI color."""

    def __init__(self, *, color: bool) -> None:
        super().__init__(datefmt="%H:%M:%S")
        self.color = color

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, self.datefmt)
        ts = f"{ts}.{int(record.msecs):03d}"
        level = record.levelname
        name = record.name
        msg = record.getMessage()
        if record.exc_info:
            msg = f"{msg}\n{self.formatException(record.exc_info)}"

        if not self.color:
            return f"{ts} {level:<8} [{name}] {msg}"

        lc = _LEVEL_COLOR.get(record.levelno, "")
        return (
            f"{_C.GRAY}{ts}{_C.RESET} "
            f"{lc}{level:<8}{_C.RESET} "
            f"{_C.MAGENTA}[{name}]{_C.RESET} {msg}"
        )


def setup_logging(level: str = "INFO") -> None:
    """Install the color handler on the root logger (idempotent)."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Replace any pre-existing handlers (e.g. uvicorn/basicConfig) so our format
    # is the one in effect.
    for h in list(root.handlers):
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stderr)
    use_color = sys.stderr.isatty()
    handler.setFormatter(ColorFormatter(color=use_color))
    root.addHandler(handler)

    # Quiet noisy libraries; we add our own request/timing lines.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _ms(seconds: float) -> str:
    return f"{seconds * 1000:.0f}ms"


@contextlib.contextmanager
def timed(logger: logging.Logger, what: str, *, level: int = logging.INFO) -> Iterator[None]:
    """Log `what` start and `… done in Xms` (or `… FAILED in Xms`) around a block."""
    start = time.perf_counter()
    logger.log(level, "%s …", what)
    try:
        yield
    except Exception:
        logger.error("%s FAILED in %s", what, _ms(time.perf_counter() - start))
        raise
    else:
        logger.log(level, "%s done in %s", what, _ms(time.perf_counter() - start))
