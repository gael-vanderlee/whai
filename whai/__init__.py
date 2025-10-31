"""whai - Terminal Assistant

A lightweight, Python-based CLI tool that integrates LLMs directly into your terminal.
"""

# Ensure library users don't get noisy logs without configuring logging
import logging as _logging

_logging.getLogger(__name__).addHandler(_logging.NullHandler())
