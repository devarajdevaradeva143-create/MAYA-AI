# Maya AI — Knowledge & RAG

> Local document search + grounded answers. No cloud required.

## What runs today

```
file (.md / .txt / .pdf)
  -> text extraction
  -> overlapping chunks (600 chars, 100 overlap, paragraph-aware)
  -> two signals per chunk:
       BM25 term statistics      (pure standard library)
       model2vec embedding       (512-dim, cached in the project)
  -> persisted index: MAYA AI/memory/offline/rag_index.json
  -> query -> hybrid ranking (reciprocal rank fusion)
  -> local model answer + cited sources
```

| Piece | Implementation | Notes |
|---|---|---|
| Chunking | `custom/tools/rag.py` → `chunk_text` | 600 chars, 100-char overlap |
| Lexical ranking | BM25 (k1=1.5, b=0.75) | always available, no dependencies |
| Semantic ranking | `custom/tools/embeddings.py` | cosine over model2vec vectors |
| Fusion | reciprocal rank fusion (k=60, depth 20) | no score normalisation needed |
| Storage | JSON at `memory/offline/rag_index.json` | atomic write, offline only |
| Incremental | mtime + size signature | unchanged files are reused |
| Answering | `knowledge rag-ask` | local Lemonade model, cites sources |

## Embedding model

| Item | Value |
|---|---|
| Default | `minishlab/potion-base-32M` (512-dim, ~130 MB) |
| Cache | `MAYA AI/Model/hf` — inside the project, not the user profile |
| Download | once, on first `rag-index`; afterwards fully offline |
| Change | `settings.yaml` → `knowledge.embedding_model`, or `MAYA_EMBED_MODEL` for one run |
| Missing | **not an error** — the index and search fall back to BM25 |

`potion-base-32M` was chosen after measuring: it separates related/unrelated
text much better than `potion-base-8M` on this corpus. It is English-focused;
for Tamil-heavy queries try `minishlab/potion-multilingual-128M` (much bigger
download, ~512 MB).

## Commands

```powershell
python -m custom.cli knowledge rag-index "..\docs"
python -m custom.cli knowledge rag-index "..\docs" --reset       # rebuild all
python -m custom.cli knowledge rag-index "..\docs" --no-semantic # BM25 only

python -m custom.cli knowledge rag-search "which chip powers the model" -k 5
python -m custom.cli knowledge rag-search "..." --mode bm25      # lexical only
python -m custom.cli knowledge rag-search "..." --mode semantic  # meaning only

python -m custom.cli knowledge rag-status
python -m custom.cli knowledge rag-ask "How much AI compute does the machine have?" -k 4
```

### Modes

| Mode | What it does | When to use |
|---|---|---|
| `hybrid` (default) | fuses BM25 + semantic with RRF | normal use |
| `bm25` | exact word overlap only | names, IDs, code, error messages |
| `semantic` | cosine similarity only | paraphrases, different wording |

In `hybrid` mode the score is a fused rank score (`1/(60+rank)` sums), so
values look small (0.03) — that is expected. `rag-search` also prints the raw
`bm25` and `cos` signals per hit. `--mode bm25` shows normal BM25 scores.

If the embedding model is missing, `hybrid` silently behaves like `bm25` and
`semantic` returns no hits; nothing crashes.

## Why hybrid, not semantic only

- BM25 is exact and unbeatable for rare words (`qwen3.5-2b-FLM`, `VOICE.md`).
- Embeddings catch paraphrases BM25 misses ("silicon brain" → NPU section).
- Fusing by rank avoids comparing incompatible score scales.

Controlled proof (three notes: engine / voice / cloud) — zero shared keywords,
correct document:

| Query | BM25 | Semantic |
|---|---|---|
| "What powers the neural processing unit?" | no hits | engine note (0.21) |
| "Can it understand spoken Indian languages?" | no hits | voice note (0.32) |
| "Does anything leave the laptop without asking?" | cloud note | cloud note (0.35) |

That is exactly the gap the semantic signal fills. On the project's own docs,
hybrid keeps the right source (e.g. `ENGINE-SETUP.md#0`) in the top results
while BM25 alone returns unrelated files.

## Storage & size

- Index path: `MAYA AI/memory/offline/rag_index.json`
- Each chunk stores its text, term frequencies **and** 512 floats.
- Rough size: ~4–5 KB per chunk. 70 chunks ≈ 300 KB. A 5,000-chunk corpus is
  ~25 MB — still fine, but rebuild time grows (one embedding pass per changed
  file, incremental afterwards).
- The index is offline data. `maya-cloud` never attaches it automatically.

## Limits (do not overpromise)

- Static embeddings are weaker than transformer embedders; **Tamil paraphrase
  quality is limited** with the default English model.
- PDF extraction depends on `pypdf`; scanned/image PDFs yield no text.
- The answer model is a small NPU model — grounded but terse, and it can still
  hallucinate a brand; the prompt tells it to copy names exactly.
- No reranking, no query expansion, no cross-encoder.
- Chunk size is tuned for docs; huge tables may split awkwardly.

## Tuning

| Knob | Where | Default |
|---|---|---|
| Chunk size / overlap | `rag.py` → `CHUNK_CHARS`, `CHUNK_OVERLAP` | 600 / 100 |
| Embedding model | `settings.yaml` → `knowledge.embedding_model` | potion-base-32M |
| Fusion constant | `rag.py` → `RRF_K`, `HYBRID_DEPTH` | 60, 20 |
| BM25 | `rag.py` → `BM25_K1`, `BM25_B` | 1.5, 0.75 |

Smaller chunks sharpen semantic matching (less topic dilution) but multiply
the chunk count. 600 chars measured best on this corpus; 900 diluted the
semantic signal.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Nothing indexed` | run `knowledge rag-index <folder>` first |
| `vectors: 0` | `model2vec` not installed or model not cached — `uv pip install -e ".[semantic]"`, then re-index |
| `semantic` returns nothing | index has no vectors — re-run `rag-index` (incremental fills them) |
| hybrid scores look tiny | expected — they are RRF rank scores, not BM25 |
| wrong/irrelevant chunks | index a focused folder; try `--mode bm25` to compare |
| `chunks: 0` after indexing | files are not `.md/.txt/.pdf`, or PDFs are scans |
| index feels stale | re-run the index (incremental) or add `--reset` |

## Privacy

- Index, chunks and vectors stay in `MAYA AI/memory/offline/`.
- Nothing is uploaded; `rag-ask` uses the local engine only.
- The embedding model runs locally (numpy only, no network at query time).
- Cloud answers are a separate command (`maya-cloud`) and never include this
  index unless you explicitly attach a file.
