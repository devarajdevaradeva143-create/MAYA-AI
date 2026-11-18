"""Maya AI — custom code package.

All Maya code lives in `custom/` per AGENTS.md.
OpenJarvis (`JARVIS/OpenJarvis`) is read-only.
"""

from typing import Any

__version__ = "0.1.0"

__all__ = ["main", "__version__"]


def __getattr__(name: str) -> Any:
    """Import the CLI lazily (PEP 562).

    Importing `.cli` eagerly here makes `python -m custom.cli` find the
    module already in sys.modules before execution, which raises
    `RuntimeWarning: 'custom.cli' found in sys.modules ...`. Keeping the
    import lazy keeps `from custom import main` working without the warning.
    """
    if name == "main":
        from .cli import main

        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
