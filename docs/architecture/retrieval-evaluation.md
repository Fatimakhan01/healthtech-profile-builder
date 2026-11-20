# Clinic FAQ retrieval evaluation

The retrieval evaluator measures retrieval only; it does not call Ollama or any
LLM. Its checked-in dataset, `backend/clinic_faq/evaluation/retrieval_questions.json`,
contains 20 answerable questions with stable IDs, expected source filenames,
and evidence excerpts validated against the current approved policy text.

## Comparisons and reproducibility

`manage.py evaluate_clinic_retrieval` runs semantic-only and the existing
hybrid mode against the same indexed approved corpus, labeled question set,
configured local embedding model, `top_k=5`, and minimum semantic similarity
of `0.2`. Both per-question result lists and aggregates are saved in
`backend/clinic_faq/reports/retrieval_evaluation.json`; a readable summary is
written to `retrieval_evaluation.md`. The JSON records UTC evaluation time,
method, K, model, source hashes, current document versions and chunk settings.

Source-based labels are deliberate: the dataset identifies relevant policy
files but does not label individual chunk spans. For each question, Recall@K
is the fraction of expected source filenames present among citations returned
by the first K retrieved chunks. HitRate@K is one if at least one expected
filename appears in those results, otherwise zero. Source precision@K is the
fraction of distinct filenames among the first K chunks that are expected;
source recall@K is the fraction of expected filenames retrieved. Duplicate
filenames are counted once for source precision/recall. MRR is the reciprocal
rank of the first relevant distinct source in the returned list, or zero when
none is retrieved. Aggregate values are macro-averages over the 20 questions,
including zeros for questions with no relevant result.

The report includes hybrid-minus-semantic deltas and, for each metric, counts
of questions improved, regressed, or unchanged. It reports measured results
only; higher retrieval scores do not establish that hybrid is better for every
question or deployment.

## Chunk-size comparison

The chunker uses characters. With defaults of 1,000 characters and 150
overlap, the evaluator compares:

| Configuration | Chunk size | Overlap |
|---|---:|---:|
| Smaller | 750 | 112 |
| Current default | 1,000 | 150 |
| Larger | 1,500 | 225 |

It reads the same four approved files, invokes the production
`ingestion.chunk_text()` implementation, embeds the resulting texts with the
configured local Sentence Transformers model, and reuses the production
semantic ranking, RRF fusion, and deterministic reranking helpers. Alternative
chunks and embeddings exist only as in-memory objects. No document/chunk rows
or ingestion settings are written or changed.

PostgreSQL full-text search operates on persisted chunks, so alternative
in-memory chunk sets use the retrieval service's dependency-free BM25 fallback
for their keyword branch. The semantic branch and fusion logic are shared.
This keeps experiments isolated but means chunk-size keyword results are not
an exact PostgreSQL `SearchRank` reproduction.

The output `backend/clinic_faq/reports/chunk_size_comparison.json` records per
configuration/method metrics and per-question results, total/per-source chunk
counts, content hashes, embedding model, timestamp, and the in-memory isolation
context. Short policies may fit into one chunk at every tested size, in which
case the measured chunk-size difference is correctly reported as negligible.

These are retrieval metrics, not answer-quality metrics. They do not measure
whether a generated answer is supported by retrieved text, whether citations
are used correctly, whether a model abstains appropriately, or whether a
passage entails a claim. Those properties require separate answer-level
evaluation and review.
