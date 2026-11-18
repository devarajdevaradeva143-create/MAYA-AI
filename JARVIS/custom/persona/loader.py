r"""Maya AI persona loader.

Loads persona .md files from MAYA AI\persona\ as system prompts for Maya.
All Maya code lives in custom\ (OpenJarvis is read-only).
"""

from pathlib import Path

# custom/persona/loader.py -> MAYA AI PROJECT\MAYA AI\persona\
# matches AGENTS.md rule: config/persona from ..\..\..\MAYA AI\
PERSONA_DIR = Path(__file__).resolve().parents[3] / "MAYA AI" / "persona"

# Mapping of persona name -> filename
PERSONA_FILES = {
    "girlfriend": "girlfriend.md",
    "english_teacher": "english-teacher.md",
}


def list_personas() -> list[str]:
    """Return list of available persona names."""
    return list(PERSONA_FILES.keys())


def load_persona(name: str) -> str:
    """Load a persona .md file and return its full content as a string.

    Args:
        name: Persona name ("girlfriend" or "english_teacher").

    Returns:
        Full file content as string (system prompt for Maya),
        or empty string if the persona/file is not found.
    """
    filename = PERSONA_FILES.get(name)
    if filename is None:
        print(f"[persona] Warning: unknown persona '{name}'")
        return ""

    persona_path = PERSONA_DIR / filename
    if not persona_path.is_file():
        print(f"[persona] Warning: persona file not found: {persona_path}")
        return ""

    try:
        return persona_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[persona] Warning: failed to read '{persona_path}': {exc}")
        return ""
