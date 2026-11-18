"""Local text embeddings (model2vec / potion) — offline after first fetch.

Why model2vec
-------------
It is a *static* embedding model: token vectors are looked up and averaged with
numpy. No ONNX runtime, no torch, no GPU — which is the only thing that fits
this laptop's current setup. Model files are cached **inside the project**
(``MAYA AI/Model/hf``) so nothing depends on a user-level cache.

Honest notes:
  * default model is ``potion-base-32M`` (512-dim, ~130 MB); the first run
    downloads it from Hugging Face, afterwards it is fully offline
  * the model name comes from ``settings.yaml`` → ``knowledge.embedding_model``;
    ``MAYA_EMBED_MODEL`` overrides it for one run
  * if the package or the cached model is missing, ``available()`` says so and
    the RAG layer falls back to BM25 silently
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..config import PROJECT_ROOT

DEFAULT_MODEL_NAME = "minishlab/potion-base-32M"
DEFAULT_MODEL_DIM = 512
DEFAULT_HF_HOME = PROJECT_ROOT / "MAYA AI" / "Model" / "hf"

_model: Any = None
_model_name: str = ""
_model_failed = False


def hf_home() -> Path:
    """Project-local Hugging Face cache so model files stay inside Maya."""
    env = os.environ.get("HF_HOME", "").strip()
    return Path(env).expanduser() if env else DEFAULT_HF_HOME


def _prepare_env() -> None:
    os.environ.setdefault("HF_HOME", str(DEFAULT_HF_HOME))
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


def model_name() -> str:
    """Resolve the embedding model: env override → settings.yaml → default."""
    env = os.environ.get("MAYA_EMBED_MODEL", "").strip()
    if env:
        return env
    try:
        from ..config import load_settings

        settings = load_settings()
        knowledge = settings.get("knowledge", {}) if isinstance(settings, dict) else {}
        configured = knowledge.get("embedding_model") if isinstance(knowledge, dict) else None
        if configured:
            return str(configured)
    except Exception:  # pragma: no cover - config must never crash embeddings
        pass
    return DEFAULT_MODEL_NAME


def package_installed() -> bool:
    try:
        import model2vec  # noqa: F401

        return True
    except ImportError:
        return False


def model_cached(name: str | None = None) -> bool:
    """Check the project-local HF cache for this model (no download)."""
    cache = hf_home() / "hub"
    folder = "models--" + (name or model_name()).replace("/", "--")
    path = cache / folder
    if not path.is_dir():
        return False
    # A snapshot with an actual weights file means it is usable.
    for candidate in path.rglob("model.safetensors"):
        if candidate.is_file() and candidate.stat().st_size > 0:
            return True
    return False


def model_dim(name: str | None = None) -> int:
    """Best-effort vector size from the cached ``config.json`` (no load)."""
    folder = hf_home() / "hub" / ("models--" + (name or model_name()).replace("/", "--"))
    try:
        for candidate in folder.rglob("config.json"):
            data = json.loads(candidate.read_text(encoding="utf-8"))
            for key in ("hidden_dim", "hidden_size", "dim"):
                value = data.get(key)
                if isinstance(value, int) and value > 0:
                    return value
    except Exception:  # pragma: no cover - corrupt cache is not fatal
        pass
    return DEFAULT_MODEL_DIM


def available() -> dict[str, Any]:
    """Honest availability report — never triggers a download."""
    installed = package_installed()
    name = model_name()
    return {
        "package": installed,
        "model": name,
        "model_cached": installed and model_cached(name),
        "dim": model_dim(name),
        "hf_home": str(hf_home()),
    }


def get_model(name: str | None = None):
    """Load the static model once per process."""
    global _model, _model_name, _model_failed
    requested = name or model_name()
    if _model is not None and _model_name == requested:
        return _model
    if _model_failed and _model_name == requested:
        return None

    _prepare_env()
    try:
        from model2vec import StaticModel

        _model = StaticModel.from_pretrained(requested)
        _model_name = requested
    except Exception:
        _model_failed = True
        _model_name = requested
        return None
    return _model


def embed(texts: list[str]) -> list[list[float]]:
    """Normalised embeddings (unit length, so dot product == cosine)."""
    model = get_model()
    if model is None:
        return []
    import numpy as np

    vectors = model.encode(list(texts))
    if not len(vectors):
        return []
    matrix = np.asarray(vectors, dtype="float32")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).tolist()


class Model2VecEmbedder:
    """Adapter that satisfies :class:`custom.tools.rag.Embedder`."""

    @property
    def name(self) -> str:
        return f"model2vec:{model_name()}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return embed(texts)


def load_embedder():
    """Return an embedder only when it can work fully offline."""
    if not available()["model_cached"]:
        return None
    return Model2VecEmbedder()
