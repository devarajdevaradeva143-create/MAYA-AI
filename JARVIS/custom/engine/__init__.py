"""Maya AI engine bridge package.

Connects to the local inference engine (Lemonade via OpenAI-compatible HTTP,
or OpenJarvis CLI subprocess). All settings come from
MAYA AI/config/settings.yaml (``engine`` section) — never hardcoded.
"""

from .bridge import EngineBridge, EngineError

__all__ = ["EngineBridge", "EngineError"]
