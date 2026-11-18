"""Local RAG — chunking, ranking, retrieval. Offline and dependency-light.

Two retrievers share one index:

  * **BM25** — lexical ranking, pure standard library, always available.
  * **Semantic** — cosine similarity over model2vec vectors (see
    :mod:`custom.tools.embeddings`). Used only when the model is cached inside
    the project. If the package or the model is missing, nothing breaks: the
    index keeps working and search quietly falls back to BM25.

``mode="hybrid"`` fuses both rankings with **reciprocal rank fusion** (RRF).
RRF needs no score normalisation, so a BM25 score of 12 and a cosine of 0.5
combine fairly, and if one retriever returns nothing the other still decides.

Storage is offline only: ``MAYA AI/memory/offline/rag_index.json``
(override with ``MAYA_RAG_INDEX`` for tests).
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol

from ..config import PROJECT_ROOT, load_settings

ENV_RAG_INDEX = "MAYA_RAG_INDEX"
DEFAULT_OFFLINE_MEMORY = "memory/offline"
RAG_INDEX_FILENAME = "rag_index.json"

INDEX_VERSION = 2
CHUNK_CHARS = 600
CHUNK_OVERLAP = 100
BM25_K1 = 1.5
BM25_B = 0.75
RRF_K = 60          # reciprocal rank fusion constant
HYBRID_DEPTH = 20   # how many hits from each retriever feed the fusion

SUPPORTED_SUFFIXES = {".md", ".txt", ".pdf"}


# ── Tokenising ─────────────────────────────────────────────────────────────

_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "has", "have", "he", "her", "his", "i", "in", "is", "it", "its", "me",
    "my", "of", "on", "or", "our", "she", "so", "that", "the", "their",
    "them", "there", "these", "they", "this", "to", "was", "were", "what",
    "when", "where", "which", "who", "will", "with", "you", "your",
}


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens, minus a small English stopword list.

    Tamil words are kept as-is (Unicode ``\\w`` matches them).
    """
    return [w for w in (m.lower() for m in _WORD_RE.findall(text or "")) if w not in STOPWORDS]


# ── Chunking ───────────────────────────────────────────────────────────────

def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks, preferring paragraph boundaries."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for paragraph in paragraphs:
        if len(paragraph) > size:
            flush()
            start = 0
            while start < len(paragraph):
                piece = paragraph[start:start + size]
                chunks.append(piece.strip())
                start += max(1, size - overlap)
            continue
        if len(current) + len(paragraph) + 2 <= size:
            current = f"{current}\n\n{paragraph}" if current else paragraph
        else:
            flush()
            current = paragraph
    flush()

    # Add a little overlap so a sentence split across chunks is still findable.
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for previous, chunk in zip(chunks, chunks[1:]):
            tail = previous[-overlap:]
            overlapped.append(f"{tail}\n{chunk}".strip())
        chunks = overlapped
    return chunks


# ── Text extraction ────────────────────────────────────────────────────────

def extract_text(path: Path) -> str:
    """Read a supported file to text (PDF goes through the existing helper)."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from .knowledge import read_pdf

        content = read_pdf(str(path))
        return "" if content.startswith("[") else content
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


# ── Embedder seam ──────────────────────────────────────────────────────────

class Embedder(Protocol):
    """Anything that turns text into a fixed-length float vector."""

    name: str

    def embed(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover - protocol
        ...


def _default_embedder() -> "Embedder | None":
    """Load the project's local embedder, or ``None`` when unavailable.

    Imported lazily so plain BM25 use never pays the model2vec import cost.
    """
    try:
        from .embeddings import load_embedder
    except Exception:  # pragma: no cover - defensive
        return None
    try:
        return load_embedder()
    except Exception:  # pragma: no cover - defensive
        return None


def _cosine(left: list[float], right: list[float]) -> float:
    """Cosine similarity; robust to un-normalised vectors and bad shapes."""
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / (norm_left * norm_right)


# ── Index ──────────────────────────────────────────────────────────────────

def _index_path() -> Path:
    override = os.environ.get(ENV_RAG_INDEX, "").strip()
    if override:
        return Path(override).expanduser()
    try:
        settings = load_settings()
    except Exception:  # pragma: no cover
        settings = {}
    memory = settings.get("memory", {}) if isinstance(settings, dict) else {}
    offline = memory.get("offline", DEFAULT_OFFLINE_MEMORY)
    path = Path(offline)
    if not path.is_absolute():
        path = PROJECT_ROOT / "MAYA AI" / path
    return path / RAG_INDEX_FILENAME


def _signature(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {"mtime": int(stat.st_mtime), "size": stat.st_size}


class RagIndex:
    """Persisted chunk index with BM25 + optional semantic vectors."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self.base = ""
        self.chunks: list[dict[str, Any]] = []
        self.files: dict[str, dict[str, Any]] = {}
        self.embedder: Embedder | None = embedder
        self.embedder_name: str = getattr(embedder, "name", "") if embedder else ""

    # -- embeddings ------------------------------------------------------

    def _attach_embedder(self, embedder: Embedder | None) -> None:
        """Attach an embedder; drop stale vectors if the model changed."""
        if embedder is None:
            return
        name = getattr(embedder, "name", "") or ""
        if self.embedder_name and name and self.embedder_name != name:
            for chunk in self.chunks:
                chunk.pop("vector", None)
        self.embedder = embedder
        self.embedder_name = name or self.embedder_name

    def ensure_embedder(self) -> Embedder | None:
        """Load the local embedder on demand (no download, may be ``None``)."""
        if self.embedder is not None:
            return self.embedder
        embedder = _default_embedder()
        if embedder is None:
            return None
        if self.embedder_name and self.embedder_name != getattr(embedder, "name", ""):
            # Vectors came from a different model — cannot compare them.
            return None
        self.embedder = embedder
        self.embedder_name = getattr(embedder, "name", "") or ""
        return self.embedder

    def _embed_chunks(self, chunks: list[dict[str, Any]]) -> int:
        """Add ``vector`` to chunks in place. Returns how many were embedded."""
        if not chunks or self.embedder is None:
            return 0
        try:
            vectors = self.embedder.embed([chunk["text"] for chunk in chunks])
        except Exception:  # pragma: no cover - never fail an index build
            return 0
        if len(vectors) != len(chunks):
            return 0
        for chunk, vector in zip(chunks, vectors):
            chunk["vector"] = [round(float(value), 6) for value in vector]
        return len(chunks)

    # -- building --------------------------------------------------------

    def add_document(self, path: Path, base: Path) -> int:
        text = extract_text(path)
        if not text.strip():
            return 0
        rel = str(path.relative_to(base)) if path.is_relative_to(base) else path.name
        start = len(self.chunks)
        for position, chunk in enumerate(chunk_text(text)):
            tokens = tokenize(chunk)
            if not tokens:
                continue
            self.chunks.append(
                {
                    "path": rel,
                    "position": position,
                    "text": chunk,
                    "tf": dict(Counter(tokens)),
                    "length": len(tokens),
                }
            )
        self._embed_chunks(self.chunks[start:])
        return 1

    def build(self, folder: str, reset: bool = False, use_embeddings: bool = True) -> dict[str, Any]:
        """Index every supported file under ``folder`` (incremental by default)."""
        folder_path = Path(folder).expanduser()
        if not folder_path.is_dir():
            return {"error": f"Folder not found: {folder}"}
        folder_path = folder_path.resolve()

        if use_embeddings:
            self._attach_embedder(self.ensure_embedder())

        previous = [] if reset else list(self.chunks)
        previous_files = {} if reset else dict(self.files)
        # Reusing chunks is only valid when the folder is the same as before.
        if self.base and Path(self.base) != folder_path:
            previous, previous_files = [], {}

        self.base = str(folder_path)
        self.chunks = []
        self.files = {}
        added = skipped = 0

        for path in sorted(folder_path.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            rel = str(path.relative_to(folder_path))
            signature = _signature(path)
            self.files[rel] = signature

            if previous_files.get(rel) == signature:
                reuse = [c for c in previous if c["path"] == rel]
                self.chunks.extend(reuse)
                skipped += 1
                continue
            added += self.add_document(path, folder_path)

        # Reused chunks may predate vectors (old index) — fill only the gaps.
        embedded = 0
        if self.embedder is not None:
            missing = [chunk for chunk in self.chunks if not chunk.get("vector")]
            embedded = self._embed_chunks(missing)

        return {
            "base": self.base,
            "files": len(self.files),
            "added": added,
            "reused": skipped,
            "chunks": len(self.chunks),
            "vectors": sum(1 for c in self.chunks if c.get("vector")),
            "embedded": embedded,
            "embedder": self.embedder_name or None,
        }

    # -- persistence -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        vectors = [len(c["vector"]) for c in self.chunks if c.get("vector")]
        return {
            "version": INDEX_VERSION,
            "built_at": datetime.now(timezone.utc).isoformat(),
            "base": self.base,
            "files": self.files,
            "chunks": self.chunks,
            "embedder": self.embedder_name or None,
            "dim": vectors[0] if vectors else 0,
        }

    def save(self, path: Path | None = None) -> bool:
        target = path or _index_path()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, target)
            return True
        except OSError:
            return False

    @classmethod
    def load(cls, path: Path | None = None) -> "RagIndex":
        target = path or _index_path()
        index = cls()
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return index
        # Version 1 = BM25 only; it still loads and simply has no vectors.
        if data.get("version") not in (1, INDEX_VERSION):
            return index
        index.base = data.get("base", "")
        index.files = data.get("files", {})
        index.chunks = data.get("chunks", [])
        index.embedder_name = data.get("embedder") or ""
        return index

    # -- retrieval -------------------------------------------------------

    def _idf(self) -> dict[str, float]:
        total = len(self.chunks)
        df: Counter[str] = Counter()
        for chunk in self.chunks:
            df.update(chunk["tf"].keys())
        return {
            term: math.log(1 + (total - count + 0.5) / (count + 0.5))
            for term, count in df.items()
        }

    def _bm25_hits(self, query: str) -> list[dict[str, Any]]:
        """Full BM25 ranking (unsliced), best first."""
        terms = tokenize(query)
        if not terms or not self.chunks:
            return []

        idf = self._idf()
        avgdl = sum(c["length"] for c in self.chunks) / max(1, len(self.chunks))
        results = []

        for chunk in self.chunks:
            tf = chunk["tf"]
            length = chunk["length"] or 1
            score = 0.0
            for term in terms:
                freq = tf.get(term)
                if not freq:
                    continue
                denominator = freq + BM25_K1 * (1 - BM25_B + BM25_B * length / avgdl)
                score += idf.get(term, 0.0) * (freq * (BM25_K1 + 1)) / denominator
            if score > 0:
                results.append(
                    {
                        "path": chunk["path"],
                        "position": chunk.get("position", 0),
                        "score": round(score, 4),
                        "text": chunk["text"],
                    }
                )

        results.sort(key=lambda item: item["score"], reverse=True)
        return results

    def _semantic_hits(self, query: str) -> list[dict[str, Any]]:
        """Full cosine ranking (unsliced), best first. Empty if unavailable."""
        if not query.strip() or not self.chunks:
            return []
        if not any(chunk.get("vector") for chunk in self.chunks):
            return []
        if self.ensure_embedder() is None:
            return []
        try:
            vectors = self.embedder.embed([query])  # type: ignore[union-attr]
        except Exception:  # pragma: no cover - never fail a search
            return []
        if not vectors:
            return []
        query_vector = vectors[0]

        results = []
        for chunk in self.chunks:
            vector = chunk.get("vector")
            if not vector:
                continue
            score = _cosine(query_vector, vector)
            results.append(
                {
                    "path": chunk["path"],
                    "position": chunk.get("position", 0),
                    "score": round(score, 4),
                    "text": chunk["text"],
                }
            )
        results.sort(key=lambda item: item["score"], reverse=True)
        return results

    @staticmethod
    def _fuse(rankings: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
        """Reciprocal rank fusion — ``score = Σ 1 / (RRF_K + rank)``."""
        fused: dict[tuple[str, int], dict[str, Any]] = {}
        for name, hits in rankings.items():
            for rank, hit in enumerate(hits[:HYBRID_DEPTH], start=1):
                key = (hit["path"], hit["position"])
                entry = fused.setdefault(
                    key,
                    {
                        "path": hit["path"],
                        "position": hit["position"],
                        "text": hit["text"],
                        "score": 0.0,
                        "signals": {},
                    },
                )
                entry["score"] += 1.0 / (RRF_K + rank)
                entry["signals"][name] = hit["score"]
        results = list(fused.values())
        for entry in results:
            entry["score"] = round(entry["score"], 6)
        results.sort(key=lambda item: item["score"], reverse=True)
        return results

    def search(
        self,
        query: str,
        k: int = 5,
        min_score: float = 0.0,
        mode: str = "hybrid",
    ) -> list[dict[str, Any]]:
        """Rank chunks against ``query``.

        ``mode``:
          * ``hybrid``   — RRF of BM25 + semantic (falls back to BM25)
          * ``bm25``     — lexical only
          * ``semantic`` — cosine only (empty when no model/vectors)
        """
        mode = (mode or "hybrid").strip().lower()
        if mode not in {"hybrid", "bm25", "semantic"}:
            raise ValueError(f"Unknown search mode: {mode}")

        if not self.chunks:
            return []

        if mode == "bm25":
            results = self._bm25_hits(query)
        elif mode == "semantic":
            results = self._semantic_hits(query)
        else:
            lexical = self._bm25_hits(query)
            semantic = self._semantic_hits(query)
            if lexical and semantic:
                results = self._fuse({"bm25": lexical, "semantic": semantic})
            else:
                # Only one retriever produced anything — use it directly and
                # keep its raw score, which is more informative than RRF.
                results = lexical or semantic

        if min_score > 0:
            results = [hit for hit in results if hit["score"] > min_score]
        return results[: max(1, k)]

    def answer_prompt(
        self,
        query: str,
        k: int = 4,
        max_chars: int = 3500,
        mode: str = "hybrid",
    ) -> tuple[str, list[dict[str, Any]]]:
        """Build a grounded prompt from the best chunks (for the local LLM)."""
        hits = self.search(query, k=k, mode=mode)
        if not hits:
            return "", []
        context_parts, used = [], []
        budget = max_chars
        for hit in hits:
            snippet = hit["text"]
            if len(snippet) > budget:
                snippet = snippet[:budget]
            context_parts.append(f"[{hit['path']}]\n{snippet}")
            used.append(hit)
            budget -= len(snippet)
            if budget <= 0:
                break
        context = "\n\n---\n\n".join(context_parts)
        prompt = (
            "Answer the question using ONLY the context below. "
            "Copy names and numbers exactly as written; never add brands, "
            "products or facts that are not in the context. "
            "If the answer is not in the context, say you don't know.\n\n"
            f"Context:\n{context}\n\nQuestion: {query}\nAnswer:"
        )
        return prompt, used

    # -- status ----------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        vectors = sum(1 for chunk in self.chunks if chunk.get("vector"))
        if self.embedder_name:
            retriever = "hybrid (bm25 + " + self.embedder_name.split("/")[-1] + ")"
        elif vectors:
            retriever = "bm25 + stored vectors"
        else:
            retriever = "bm25 (lexical)"
        return {
            "base": self.base,
            "files": len(self.files),
            "chunks": len(self.chunks),
            "vectors": vectors,
            "dim": len(next((c["vector"] for c in self.chunks if c.get("vector")), []) or []),
            "embedder": self.embedder_name or "bm25 (lexical)",
            "retriever": retriever,
            "index_path": str(_index_path()),
        }


def index_files(
    folder: str,
    reset: bool = False,
    use_embeddings: bool = True,
    embedder: Embedder | None = None,
) -> dict[str, Any]:
    """Build + save an index in one call (incremental unless ``reset``)."""
    index = RagIndex() if reset else RagIndex.load()
    if embedder is not None:
        index.embedder = embedder
        index.embedder_name = getattr(embedder, "name", "") or index.embedder_name
    summary = index.build(folder, reset=reset, use_embeddings=use_embeddings)
    if "error" in summary:
        return summary
    summary["saved"] = index.save()
    return summary


def search(query: str, k: int = 5, mode: str = "hybrid") -> list[dict[str, Any]]:
    return RagIndex.load().search(query, k=k, mode=mode)


def build_prompt(query: str, k: int = 4, mode: str = "hybrid") -> tuple[str, list[dict[str, Any]]]:
    return RagIndex.load().answer_prompt(query, k=k, mode=mode)


def iter_supported(folder: str) -> Iterable[Path]:
    root = Path(folder)
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            yield path
