# Hybrid retrieval manual verification

Run commands from `backend/` after migrations, approved-policy ingestion, and
local embedding generation. The examples below use the existing local
Sentence Transformers model and PostgreSQL full-text search. They do not start
the 20-question retrieval evaluation or call Ollama.

## Prepare and inspect the index

```powershell
..\.venv-integration\Scripts\python.exe manage.py migrate clinic_faq
..\.venv-integration\Scripts\python.exe manage.py ingest_clinic_policies
..\.venv-integration\Scripts\python.exe manage.py embed_clinic_policies
..\.venv-integration\Scripts\python.exe manage.py shell -c "from clinic_faq.models import PolicyDocument; [print(d.pk, d.source_filename, d.is_approved, d.is_active, d.version, d.indexing_status, d.chunks.count()) for d in PolicyDocument.objects.order_by('source_filename')]"
```

Only approved, active documents at `indexing_status='indexed'` with current
chunks should be eligible. Each eligible chunk must have a valid embedding,
configured model name, and matching text digest.

## Compare the search modes

```powershell
..\.venv-integration\Scripts\python.exe manage.py shell -c "from clinic_faq.retrieval import retrieve_policy_chunks; q='How do I cancel an appointment?'; [print({'id': r.chunk_id, 'source': r.source_filename, 'method': r.retrieval_method, 'similarity': round(r.similarity, 4), 'fusion': round(r.fusion_score, 6), 'text': r.text}) for r in retrieve_policy_chunks(q, top_k=5)]"
..\.venv-integration\Scripts\python.exe manage.py shell -c "from clinic_faq.retrieval import retrieve_policy_chunks; [print({'id': r.chunk_id, 'source': r.source_filename, 'similarity': round(r.similarity, 4)}) for r in retrieve_policy_chunks('How do I cancel an appointment?', search_mode='semantic', top_k=5)]"
..\.venv-integration\Scripts\python.exe manage.py shell -c "from clinic_faq.retrieval import retrieve_policy_chunks; [print({'id': r.chunk_id, 'source': r.source_filename, 'method': r.retrieval_method, 'text': r.text}) for r in retrieve_policy_chunks('cancel appointment', search_mode='keyword', top_k=5)]"
```

Hybrid results are bounded to five by default and carry `semantic`,
`keyword`, or `hybrid` method metadata. The `similarity` value remains cosine
similarity; a keyword-only result has similarity `0.0`. Keyword mode does not
compute a query embedding. Actual result counts depend on the approved corpus
and query.

## Narrow by existing metadata and verify limits

```powershell
..\.venv-integration\Scripts\python.exe manage.py shell -c "from clinic_faq.models import PolicyDocument; from clinic_faq.retrieval import retrieve_policy_chunks; source=PolicyDocument.objects.filter(is_approved=True, is_active=True, indexing_status='indexed').first(); print([(r.chunk_id, r.source_filename) for r in retrieve_policy_chunks('appointment', filters={'source_filenames': [source.source_filename]})] if source else [])"
..\.venv-integration\Scripts\python.exe manage.py shell -c "from clinic_faq.models import PolicyDocument; from clinic_faq.retrieval import retrieve_policy_chunks; source=PolicyDocument.objects.filter(is_approved=True, is_active=True, indexing_status='indexed').first(); print([(r.chunk_id, r.source_filename) for r in retrieve_policy_chunks('appointment', filters={'document_ids': [source.pk]})] if source else [])"
```

Each filtered result should belong to the selected source. Invalid/unknown
filters and limits outside `top_k=1..50` or `candidate_limit=top_k..2000`
raise `ValueError`; the mandatory document/version/embedding checks still
apply.

## Automated retrieval and compatibility tests

```powershell
..\.venv-integration\Scripts\python.exe manage.py test clinic_faq.tests_retrieval clinic_faq.tests
```

These tests mock expensive local inference and provider HTTP calls. They cover
keyword-only and semantic-only matches, RRF ordering/deduplication,
deterministic tie reranking, metadata narrowing, ineligible chunks, malformed
filters, bounds, and the unchanged FAQ citation response contract. The test
suite does not invoke `evaluate_clinic_faq`.

For the labeled retrieval-only semantic/hybrid and in-memory chunk-size
evaluation, see [retrieval-evaluation.md](./retrieval-evaluation.md). It is
separate from the Ollama answer evaluation and does not generate answers.
