"""Entry point for running terma as a module."""

import logging

from terma.logging_setup import configure_logging

if __name__ == "__main__":
    # Configure logging BEFORE importing heavy modules to get early debug output
    configure_logging()
    logging.getLogger(__name__).debug("terma module entry starting up")

    # Import CLI app only after logging is configured to observe import-time delays
    from terma.main import app

    app()
