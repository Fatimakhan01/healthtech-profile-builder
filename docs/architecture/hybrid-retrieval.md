# Clinic FAQ hybrid retrieval

`clinic_faq.retrieval.retrieve_policy_chunks()` extends the existing retrieval
service and keeps its result fields (`chunk_id`, source title and filename,
text, and `similarity`) for the provider and citation path. It defaults to
hybrid search; `search_mode="semantic"` provides semantic-only ranking and
`search_mode="keyword"` provides keyword-only ranking without creating a
separate FAQ pipeline.

## Candidate eligibility and metadata filters

Candidates come from the approved-source verification already used by local
embedding generation. Every search mode and every filter requires a document
to be approved, active, and indexed, and a chunk to belong to the document's
current version. Chunks must also match the configured embedding model and text
digest and contain a valid, dimension-compatible stored embedding. Keyword
search does not make missing or stale embeddings eligible.

Optional `filters` narrow the candidate documents using existing metadata:

- `source_filenames`: a non-empty collection of source filenames.
- `document_ids`: a non-empty collection of positive database IDs.

Both filters can be combined. Unknown filters, including category filters, are
rejected; there is no category field in the current schema. No filter can
disable approval, activity, indexing, current-version, source-validation, or
embedding checks.

## Search, fusion, and reranking

The semantic branch creates the query vector with the configured local
Sentence Transformers model, computes cosine similarity against valid stored
vectors, applies `min_similarity`, and keeps its ranked candidate list.

The keyword branch uses PostgreSQL's built-in full-text search (`SearchVector`,
plain `SearchQuery`, and `SearchRank`) on chunk text. On a non-PostgreSQL
backend it falls back to a small in-process BM25 implementation, which keeps
tests and local alternatives dependency-free. Both branches use deterministic
chunk-ID tie-breaking.

Hybrid mode combines the two ranked lists with Reciprocal Rank Fusion:
`sum(1 / (60 + rank))`. It does not add raw cosine and keyword scores. A chunk
found in both lists is included once. The existing `similarity` value remains
the cosine score (or `0.0` for a keyword-only result); additive
`fusion_score` and `retrieval_method` fields report the hybrid ranking signal.

After fusion, ties are broken by exact query phrase, query-token coverage,
semantic cosine score, then chunk ID. This is a deterministic tie-break
reranker using existing signals, not a trained cross-encoder; it cannot judge
passage relevance or query-document entailment beyond those signals.

## Bounds and configuration

`top_k` remains 5 by default and is bounded from 1 through 50.
`candidate_limit` defaults to 500 and is bounded through 2,000; it caps the
candidates considered by either ranker and must be at least `top_k`. Filters
are useful to narrow that candidate pool. The configured local embedding model
is selected by `CLINIC_FAQ_EMBEDDING_MODEL`, as in the existing embedding
workflow. No additional services, model downloads, paid APIs, or dependencies
are introduced.

The hybrid result set can include keyword matches that do not pass the
semantic `min_similarity` threshold. In keyword-only mode no query embedding
is computed. In default hybrid mode the local query embedding remains
necessary, and model errors continue to be surfaced to the existing provider.
The approved policy corpus is expected to be small; if it grows beyond the
candidate cap, use metadata filters or revisit candidate generation rather
than assuming exhaustive search.
