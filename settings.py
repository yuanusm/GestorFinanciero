"""Backward-compatible settings module.

The project historically used ``config.py``. New code and documentation can import
from ``settings.py`` while older modules keep working through the same dataclass.
"""

from config import Settings, load_settings

__all__ = ["Settings", "load_settings"]
