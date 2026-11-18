"""RAG tests — chunking, ranking, persistence. No model, no network."""

import pytest
from click.testing import CliRunner

from custom.cli import main
from custom.tools import rag


@pytest.fixture()
def corpus(tmp_path, monkeypatch):
    """Two small documents plus an isolated index path."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "engine.md").write_text(
        "Maya uses the Lemonade server for inference.\n\n"
        "The Qwen model runs on the AMD NPU and reaches 50 TOPS.",
        encoding="utf-8",
    )
    (docs / "voice.md").write_text(
        "Voice input uses Vosk models stored inside the project.\n\n"
        "Tamil speech is not supported by official Vosk models.",
        encoding="utf-8",
    )
    monkeypatch.setenv(rag.ENV_RAG_INDEX, str(tmp_path / "rag_index.json"))
    # Tests stay offline/deterministic: no real embedding model unless a test
    # explicitly installs a fake one.
    monkeypatch.setattr(rag, "_default_embedder", lambda: None)
    return docs


class FakeEmbedder:
    """Deterministic 3-dim stand-in: hardware / voice / constant noise."""

    name = "fake:test"
    HARDWARE = {
        "npu", "chip", "hardware", "processor", "silicon", "brain",
        "amd", "qwen", "tops", "laptop", "engine",
    }
    VOICE = {"vosk", "voice", "speech", "microphone", "tamil", "audio"}

    def _vector(self, text: str) -> list[float]:
        words = set(rag.tokenize(text))
        return [
            1.0 if words & self.HARDWARE else 0.0,
            1.0 if words & self.VOICE else 0.0,
            0.05,
        ]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]


@pytest.fixture()
def semantic(corpus, monkeypatch):
    """The same corpus, built and searched with the fake embedder."""
    embedder = FakeEmbedder()
    monkeypatch.setattr(rag, "_default_embedder", lambda: embedder)
    summary = rag.index_files(str(corpus), use_embeddings=True)
    return corpus, summary, embedder


# ── Tokenising & chunking ─────────────────────────────────────────────

def test_tokenize_drops_stopwords_and_punctuation():
    assert rag.tokenize("The NPU, and the CPU!") == ["npu", "cpu"]


def test_tokenize_keeps_tamil_words():
    assert rag.tokenize("vanakkam da") == ["vanakkam", "da"]


def test_chunk_short_text_is_one_chunk():
    assert rag.chunk_text("short note") == ["short note"]


def test_chunk_long_text_splits_with_overlap():
    text = "\n\n".join(f"paragraph {i} " + ("filler " * 60) for i in range(6))
    chunks = rag.chunk_text(text, size=400, overlap=50)
    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)


def test_chunk_empty_text():
    assert rag.chunk_text("") == []


# ── Index & retrieval ─────────────────────────────────────────────────

def test_build_indexes_supported_files(corpus):
    summary = rag.index_files(str(corpus))
    assert summary["files"] == 2
    assert summary["chunks"] >= 2
    assert summary["saved"] is True


def test_search_ranks_the_relevant_document_first(corpus):
    rag.index_files(str(corpus))
    hits = rag.search("npu tops", k=3)
    assert hits
    assert hits[0]["path"] == "engine.md"
    assert hits[0]["score"] > 0


def test_search_unrelated_query_returns_nothing(corpus):
    rag.index_files(str(corpus))
    assert rag.search("quantum blockchain", k=3) == []


def test_index_is_incremental(corpus):
    rag.index_files(str(corpus))
    second = rag.index_files(str(corpus))
    assert second["added"] == 0
    assert second["reused"] == 2


def test_incremental_rebuild_keeps_every_chunk(tmp_path, monkeypatch):
    """Regression: reuse must keep all chunks of an unchanged file, not one."""
    docs = tmp_path / "long"
    docs.mkdir()
    (docs / "long.md").write_text("Paragraph one. " * 200, encoding="utf-8")
    (docs / "small.md").write_text("short note", encoding="utf-8")
    monkeypatch.setenv(rag.ENV_RAG_INDEX, str(tmp_path / "rag_index.json"))
    monkeypatch.setattr(rag, "_default_embedder", lambda: None)

    first = rag.index_files(str(docs))
    assert first["chunks"] > 2
    second = rag.index_files(str(docs))
    assert second["reused"] == 2
    assert second["added"] == 0
    assert second["chunks"] == first["chunks"]
    assert len(rag.RagIndex.load().chunks) == first["chunks"]


def test_changed_file_is_reindexed(corpus):
    rag.index_files(str(corpus))
    target = corpus / "engine.md"
    target.write_text("Completely new content about cooling fans.", encoding="utf-8")
    summary = rag.index_files(str(corpus))
    assert summary["added"] == 1
    assert rag.search("cooling fans")[0]["path"] == "engine.md"


def test_persistence_roundtrip(corpus):
    rag.index_files(str(corpus))
    reloaded = rag.RagIndex.load()
    assert len(reloaded.chunks) >= 2
    assert reloaded.search("vosk")[0]["path"] == "voice.md"


def test_missing_index_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv(rag.ENV_RAG_INDEX, str(tmp_path / "nope.json"))
    index = rag.RagIndex.load()
    assert index.chunks == []
    assert index.search("anything") == []


def test_build_prompt_contains_context_and_question(corpus):
    rag.index_files(str(corpus))
    prompt, used = rag.build_prompt("What runs on the NPU?", k=2)
    assert "Question: What runs on the NPU?" in prompt
    assert "ONLY the context" in prompt
    assert used and used[0]["path"] == "engine.md"


def test_build_prompt_without_index_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv(rag.ENV_RAG_INDEX, str(tmp_path / "nope.json"))
    prompt, used = rag.build_prompt("anything")
    assert prompt == "" and used == []


# ── CLI ───────────────────────────────────────────────────────────────

def test_cli_rag_index_and_search(corpus):
    runner = CliRunner()

    built = runner.invoke(main, ["knowledge", "rag-index", str(corpus)])
    assert built.exit_code == 0, built.output
    assert "chunks:" in built.output

    found = runner.invoke(main, ["knowledge", "rag-search", "npu", "-k", "2"])
    assert found.exit_code == 0, found.output
    assert "engine.md" in found.output


def test_cli_rag_status_without_index(tmp_path, monkeypatch):
    monkeypatch.setenv(rag.ENV_RAG_INDEX, str(tmp_path / "nope.json"))
    result = CliRunner().invoke(main, ["knowledge", "rag-status"])
    assert result.exit_code == 0, result.output
    assert "chunks: 0" in result.output


def test_cli_rag_ask_without_index(tmp_path, monkeypatch):
    monkeypatch.setenv(rag.ENV_RAG_INDEX, str(tmp_path / "nope.json"))
    result = CliRunner().invoke(main, ["knowledge", "rag-ask", "hello"])
    assert result.exit_code == 0, result.output
    assert "Nothing indexed" in result.output


# ── Semantic / hybrid retrieval ───────────────────────────────────────

def test_index_records_vectors_when_embedder_available(semantic):
    _, summary, embedder = semantic
    assert summary["embedder"] == embedder.name
    assert summary["vectors"] == summary["chunks"] > 0
    index = rag.RagIndex.load()
    assert all(len(chunk.get("vector", [])) == 3 for chunk in index.chunks)


def test_semantic_mode_finds_a_paraphrase_bm25_misses(semantic):
    # "silicon brain" shares no words with the documents.
    assert rag.search("silicon brain", mode="bm25") == []

    hits = rag.search("silicon brain", mode="semantic")
    assert hits and hits[0]["path"] == "engine.md"
    assert hits[0]["score"] > 0.5


def test_hybrid_mode_combines_both_retrievers(semantic):
    hits = rag.search("npu voice", k=5, mode="hybrid")
    paths = {hit["path"] for hit in hits}
    assert {"engine.md", "voice.md"} <= paths
    assert all(hit["signals"] for hit in hits)


def test_vectors_survive_save_and_load(semantic):
    _, summary, _ = semantic
    reloaded = rag.RagIndex.load()
    assert reloaded.embedder_name == "fake:test"
    assert reloaded.summary()["vectors"] == summary["chunks"]
    # No embedder object on a fresh load; it is attached on demand.
    assert reloaded.embedder is None
    assert reloaded.search("silicon brain", mode="semantic")[0]["path"] == "engine.md"


def test_incremental_rebuild_fills_missing_vectors(semantic, monkeypatch):
    _, _, embedder = semantic
    # Simulate an index written before embeddings existed.
    index = rag.RagIndex.load()
    for chunk in index.chunks:
        chunk.pop("vector", None)
    index.embedder_name = ""
    index.save()

    monkeypatch.setattr(rag, "_default_embedder", lambda: embedder)
    summary = rag.index_files(str(rag.RagIndex.load().base), use_embeddings=True)
    assert summary["added"] == 0
    assert summary["reused"] == 2
    assert summary["vectors"] == summary["chunks"]


def test_missing_model_falls_back_to_bm25(corpus):
    summary = rag.index_files(str(corpus), use_embeddings=True)
    assert summary["embedder"] is None
    assert summary["vectors"] == 0

    assert rag.search("silicon brain", mode="semantic") == []
    assert rag.search("npu", mode="hybrid")[0]["path"] == "engine.md"
    assert "bm25" in rag.RagIndex.load().summary()["retriever"]


def test_embedding_failure_never_breaks_the_index(corpus, monkeypatch):
    class Broken:
        name = "broken:test"

        def embed(self, texts):
            raise RuntimeError("boom")

    monkeypatch.setattr(rag, "_default_embedder", lambda: Broken())
    summary = rag.index_files(str(corpus))
    assert summary["chunks"] >= 2
    assert summary["vectors"] == 0
    assert rag.search("npu")[0]["path"] == "engine.md"


def test_unknown_mode_is_rejected(semantic):
    with pytest.raises(ValueError):
        rag.search("npu", mode="magic")


def test_cli_no_semantic_skips_vectors(corpus):
    result = CliRunner().invoke(
        main, ["knowledge", "rag-index", str(corpus), "--no-semantic"]
    )
    assert result.exit_code == 0, result.output
    assert "vectors: skipped" in result.output


def test_cli_search_mode_flag(semantic):
    _, _, _ = semantic
    result = CliRunner().invoke(
        main, ["knowledge", "rag-search", "npu", "--mode", "bm25"]
    )
    assert result.exit_code == 0, result.output
    assert "engine.md" in result.output
    assert "[bm25]" in result.output


def test_cli_status_shows_vector_count(semantic):
    result = CliRunner().invoke(main, ["knowledge", "rag-status"])
    assert result.exit_code == 0, result.output
    assert "vectors:" in result.output
    assert "fake" in result.output

