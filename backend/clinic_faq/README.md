# Clinic FAQ policy ingestion

`policies/approved/` is the only accepted source directory. It contains small,
fictional examples and is not a real clinic's policy set. The ingestion code
accepts direct regular files with `.md` or `.txt` extensions only; it does not
search the repository, follow symbolic links, read uploads, or access profile
records. Markdown links are reduced to their visible labels and are never
fetched.

The curated examples are `appointment-scheduling.md`, `cancellations.md`,
`late-arrivals.md`, and `reminders.md`. Each is explicitly labeled synthetic;
none represents a real clinic policy.

Run the explicit command from `backend/` after applying migrations:

```powershell
..\.venv-integration\Scripts\python.exe manage.py migrate clinic_faq
..\.venv-integration\Scripts\python.exe manage.py ingest_clinic_policies
```

Chunk size and overlap are configurable in characters:

```powershell
..\.venv-integration\Scripts\python.exe manage.py ingest_clinic_policies --chunk-size 1000 --overlap 150
```

Chunking prefers paragraph boundaries and then whitespace boundaries while
keeping each chunk within the configured maximum. The overlap is a target and
is moved to a word boundary where practical. Source filenames, document titles,
SHA-256 digests, ingestion timestamps, chunk indexes, and extracted text are
stored in `PolicyDocument` and `PolicyChunk`, along with the chunk settings
used. Ingestion is transactional per document: unchanged source bytes and
settings are skipped, while changed bytes or chunk settings replace that
document's chunks atomically.

This stage only extracts and persists approved text. It does not create
embeddings, retrieve chunks, or use these documents in FAQ answers.

## Embedding generation

Embeddings are generated locally with Sentence Transformers and the default
`sentence-transformers/all-MiniLM-L6-v2` model (384 dimensions). Install the
backend requirements from `backend/`:

```powershell
..\.venv-integration\Scripts\python.exe -m pip install -r requirements.txt
```

`CLINIC_FAQ_EMBEDDING_MODEL` can select another Sentence Transformers model;
it defaults to `sentence-transformers/all-MiniLM-L6-v2`. Embedding generation
does not require an API key and makes no paid API requests. The first explicit
run may download model weights to the local Hugging Face cache and therefore
requires network access.

After policy ingestion and the embedding-field migration, run the explicit
management command:

```powershell
..\.venv-integration\Scripts\python.exe manage.py migrate clinic_faq
..\.venv-integration\Scripts\python.exe manage.py embed_clinic_policies
```

The command runs bounded local inference batches of at most 64 chunks. Before
encoding, each stored chunk is matched against the source file's current
SHA-256 and the deterministic chunks from the approved source directory;
stale source records, unsupported sources, and altered database text are not
encoded. It stores JSON vectors, the configured model identifier, and a
SHA-256 of the exact chunk text. A chunk is skipped only if all three match
and its existing vector is non-empty, finite, and has the expected dimension.
Malformed model output or local inference errors do not mark failed chunks as
embedded. Already completed earlier batches remain valid and are skipped on
the next run.

Use `--batch-size` to choose an inference batch size from 1 to 64. Query
vectors can be produced locally with `clinic_faq.embeddings.embed_query()`
using the same configured model. No embedding is generated at app startup or
during tests, and no user question is persisted or sent to an external
embedding service. Only verified approved policy text is encoded and stored
in PostgreSQL JSON fields. This stage covers persistence only; retrieval and
FAQ answer generation are described below.

## Semantic retrieval

`clinic_faq.retrieval.retrieve_policy_chunks(query, top_k=5,
min_similarity=0.2)` performs read-only cosine-similarity search over current
chunks from `policies/approved/`. It uses the configured local model to embed
the query, and only considers chunks whose source still matches the approved
file, chunk text hash, and configured embedding model. Malformed, stale, or
dimension-incompatible vectors are ignored. Results contain the chunk ID,
source title and filename, text, and similarity score.

For manual verification after ingesting and embedding the approved policies,
run from `backend/`:

```powershell
..\.venv-integration\Scripts\python.exe manage.py shell -c "from clinic_faq.retrieval import retrieve_policy_chunks; [print({'chunk_id': r.chunk_id, 'source': r.source_filename, 'similarity': round(r.similarity, 4), 'text': r.text}) for r in retrieve_policy_chunks('How do I cancel an appointment?', top_k=3, min_similarity=0.2)]"
```

## Local FAQ answer generation

The authenticated FAQ endpoint retrieves relevant approved passages and sends
only those passages plus the general FAQ question to the local Ollama HTTP API.
The configured base URL must be loopback (`localhost` or a loopback IP), so
this integration cannot target a cloud LLM. Ollama must be running locally and
the configured chat model must be pulled. The `.env.example` contains the
recommended values:

```text
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_CHAT_MODEL=qwen2.5:1.5b-instruct
OLLAMA_TIMEOUT_SECONDS=120
OLLAMA_NUM_CTX=2048
OLLAMA_TEMPERATURE=0.1
OLLAMA_MAX_OUTPUT_TOKENS=256
```

Retrieved passages and the question are treated as untrusted data by the
system prompt. With no relevant passages, the endpoint abstains without calling
Ollama. Grounded responses include server-generated citations with each source
title and filename. Model output is validated against the JSON response
contract. No patient/profile records, uploads, or other application data are
passed to Ollama.

Start Ollama, then pull the configured model:

```powershell
ollama pull qwen2.5:1.5b-instruct
```

The endpoint remains `POST /api/v1/clinic-faq/ask/`; it requires existing
standard-user authentication and is limited to 10 requests per hour.

## Local FAQ evaluation

Run the explicit evaluation from `backend/` after ingesting and embedding the
four approved synthetic policy documents, with Ollama running and the
configured model available:

```powershell
..\.venv-integration\Scripts\python.exe manage.py evaluate_clinic_faq
```

This runs 12 curated general policy questions (answerable and intentionally
unanswerable) against two Ollama-only configurations:

- **A — current:** production prompt, `top_k=5`, minimum similarity `0.20`.
- **B — improved:** stricter evidence-per-factual-statement and abstention
  prompt, `top_k=3`, minimum similarity `0.35`.

The command writes `clinic_faq/reports/ollama_evaluation.json`. Each result
records the question, configuration, model answer, abstention flag, citations,
retrieved chunks and similarity scores, plus checks for citation correctness,
phrase-based relevance to retrieved text, curated unsupported-claim phrases,
and expected abstention. The unsupported-claim and relevance checks are
transparent lexical heuristics, not human or semantic fact verification;
inspect the recorded passages and answers before drawing conclusions. The
report also summarizes pass/fail counts by configuration. Use `--output
<path>` to select a different JSON destination. The evaluation reads only the
approved fictional policy corpus and does not access user or patient records.

The checked-in evaluation report currently records **0/12 passed** for
configuration A and **4/12 passed** for configuration B. These are the saved
run's outcomes, not a guarantee of results on a later Ollama run. The report's
citation, relevance, and unsupported-claim checks include lexical heuristics;
review the per-question answers, citations, retrieved passages, and failures
before drawing conclusions.

## Verification

From `backend/`, after configuring PostgreSQL and the local environment, run
the FAQ unit and integration tests and standard Django checks:

```powershell
..\.venv-integration\Scripts\python.exe manage.py test clinic_faq
..\.venv-integration\Scripts\python.exe manage.py check
..\.venv-integration\Scripts\python.exe manage.py makemigrations --check --dry-run
```

The automated FAQ tests mock the Ollama provider and embedding model; they do
not require a running Ollama service or make paid/external LLM calls. The
explicit `evaluate_clinic_faq` management command is a separate manual
evaluation and requires the local model, approved policies, embeddings, and
Ollama service described above.
