# Retrieval evaluation verification

Run from `backend/` with the four approved policy files present, all four
documents ingested and indexed, and the configured Sentence Transformers model
already available in the local cache. The evaluation sets Hugging Face and
Transformers offline flags; it will fail rather than download missing model
weights. It does not call Ollama or an LLM.

## Run and inspect the reproducible evaluation

```powershell
..\.venv-integration\Scripts\python.exe manage.py evaluate_clinic_retrieval
```

Expected output confirms 20 questions and prints semantic/hybrid MRR plus the
JSON and chunk report locations. The command writes:

- `clinic_faq/reports/retrieval_evaluation.json`
- `clinic_faq/reports/retrieval_evaluation.md`
- `clinic_faq/reports/chunk_size_comparison.json`

The JSON should contain both `semantic` and `hybrid` method sections, 20
question records per method, aggregate Recall/HitRate/source precision/source
recall at K=1, 3, 5 and MRR, measured hybrid-minus-semantic differences, source
hashes and document versions. The chunk report should contain smaller/default/
larger character-based configurations at 750/112, 1,000/150 and 1,500/225,
with per-source chunk counts, metrics for both methods, and `in-memory only`
storage context. Metric values depend on the installed local model and
approved corpus; there is no expected score threshold.

To select alternate output paths or the question dataset:

```powershell
..\.venv-integration\Scripts\python.exe manage.py evaluate_clinic_retrieval --questions clinic_faq\evaluation\retrieval_questions.json --output-json clinic_faq\reports\retrieval_evaluation.json --output-markdown clinic_faq\reports\retrieval_evaluation.md --chunk-output clinic_faq\reports\chunk_size_comparison.json
```

Do not pass a modified dataset as a baseline without validating its expected
sources and evidence against the approved policy files.

## Run focused tests and regression checks

```powershell
..\.venv-integration\Scripts\python.exe manage.py test clinic_faq.tests_retrieval_evaluation clinic_faq.tests_retrieval clinic_faq.tests
..\.venv-integration\Scripts\python.exe manage.py check
..\.venv-integration\Scripts\python.exe manage.py makemigrations --check --dry-run
```

Unit tests use deterministic fixtures and mocked embeddings; they do not
download/load the local model or run the evaluation command. The chunk-size
test asserts that existing database document and chunk records are unchanged.
