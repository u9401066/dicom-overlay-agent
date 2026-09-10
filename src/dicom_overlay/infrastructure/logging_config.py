"""Structured logging setup — configures structlog with stdlib integration."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import structlog


def setup_bootstrap_logging() -> None:
    """Route pre-config startup logs through silent stdlib logging.

    ``load_config`` logs before the final log path/level is known. A windowed
    PyInstaller process has neither stdout nor stderr, so structlog's default
    print logger is unsafe during that short bootstrap phase.
    """

    structlog.configure(
        processors=[
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.stdlib.render_to_log_kwargs,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    root = logging.getLogger()
    if not root.handlers:
        root.addHandler(logging.NullHandler())


def resolve_log_path(log_file: str | Path, *, base_dir: Path | None = None) -> Path:
    """Resolve relative logs against the application base, never launch cwd."""

    path = Path(log_file)
    if path.is_absolute():
        return path
    anchor = (Path.cwd() if base_dir is None else Path(base_dir)).resolve()
    resolved = (anchor / path).resolve()
    try:
        resolved.relative_to(anchor)
    except ValueError as exc:
        raise ValueError("relative log path must stay inside the application base") from exc
    return resolved


def setup_logging(
    log_level: str = "INFO",
    log_file: str | Path = "agent.log",
    *,
    base_dir: Path | None = None,
) -> None:
    """Configure structlog with optional plain console + file output.

    Uses structlog → stdlib pipeline so all handlers (StreamHandler,
    FileHandler) are managed by stdlib logging while structlog provides
    structured processing.  A windowed PyInstaller process has no stderr, and
    the frozen runtime intentionally omits optional ``colorama``/``rich``.
    Plain rendering keeps startup deterministic in both environments.
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    console_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(
                colors=False,
                exception_formatter=structlog.dev.plain_traceback,
            ),
        ],
    )

    file_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(
                colors=False,
                exception_formatter=structlog.dev.plain_traceback,
            ),
        ],
    )

    resolved_log_file = resolve_log_path(log_file, base_dir=base_dir)
    resolved_log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(resolved_log_file, encoding="utf-8")
    file_handler.setFormatter(file_formatter)

    root = logging.getLogger()
    root.handlers.clear()
    if sys.stderr is not None:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(console_formatter)
        root.addHandler(console_handler)
    root.addHandler(file_handler)
    # Set root to WARNING so third-party libs (PIL, websockets) stay quiet.
    # Only our own logger uses the configured level.
    root.setLevel(logging.WARNING)

    app_logger = logging.getLogger("dicom_overlay")
    app_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
