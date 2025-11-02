"""Entry point for running whai as a module."""

import logging

from whai.logging_setup import configure_logging

if __name__ == "__main__":
    # Configure logging BEFORE importing heavy modules to get early debug output
    configure_logging()
    logging.getLogger(__name__).debug("whai module entry starting up")

    # Import CLI app only after logging is configured to observe import-time delays
    from whai.cli.main import app

    app()
