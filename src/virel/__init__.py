"""Virel — professional interfaces, written in Python.

Phase 0 architecture-validation prototype (see SPEC.md).
"""

from . import ui
from .expr import VirelCompileError

__version__ = "0.1.0a0"
__all__ = ["ui", "VirelCompileError", "__version__"]
