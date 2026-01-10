"""Structured logging with trace ID support."""

import logging

import structlog


def get_logger(name: str) -> structlog.BoundLogger:
    """Get structured logger instance.

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured structlog logger

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("memory_retrieve_start", trace_id="abc123", query="test")
    """
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),  # type: ignore
    )
    return structlog.get_logger(name)


# Standard fields for logging
# - trace_id: Full operation chain
# - session_id: Current session
# - user_id: User identifier
# - component: Module name
# - duration_ms: Operation latency
