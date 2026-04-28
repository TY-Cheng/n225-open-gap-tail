"""Cache/data-lake helpers re-exported from :mod:`n225_open_gap_tail.paper`.

This module is a structural compatibility surface for the paper package split.
Implementation remains in the package root until the next no-logic-change
extraction pass.
"""

from . import (
    cleanup_transient_unavailable_markers,
)

__all__ = ["cleanup_transient_unavailable_markers"]
