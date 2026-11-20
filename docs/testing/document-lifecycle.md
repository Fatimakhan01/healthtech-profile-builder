# Document lifecycle manual verification

Run these commands from `backend/` in the configured local development
environment. They use the existing local Sentence Transformers model; no
Ollama service or paid embedding API is needed.

## Migrate and inspect

```powershell
..\.venv-integration\Scripts\python.exe manage.py migrate clinic_faq
..\.venv-integration\Scripts\python.exe manage.py ingest_clinic_policies
..\.venv-integration\Scripts\python.exe manage.py shell -c "from clinic_faq.models import PolicyDocument; [print(d.source_filename, d.version, d.content_sha256, d.is_approved, d.is_active, d.indexing_status, d.chunks.count()) for d in PolicyDocument.objects.order_by('source_filename')]"
```

The migration reports `0003` applied (or no migrations to apply). Ingestion
reports created/unchanged/updated counts and `deactivated=0` when there are no
removed sources. Each present source should be approved and active, have version
`1` on first ingestion, and be `pending` until embedding succeeds.

## Embed and confirm idempotence

```powershell
..\.venv-integration\Scripts\python.exe manage.py embed_clinic_policies
..\.venv-integration\Scripts\python.exe manage.py shell -c "from clinic_faq.models import PolicyDocument; [print(d.source_filename, d.version, d.indexing_status, d.chunks.count()) for d in PolicyDocument.objects.order_by('source_filename')]"
..\.venv-integration\Scripts\python.exe manage.py ingest_clinic_policies
```

After embedding, each fully embedded current document should be `indexed`.
Re-ingestion without changes should report all present files as unchanged, leave
versions and chunk counts stable, and report no deactivations.

## Verify update and removal behavior

Use a local development copy of an approved policy file, not a production or
shared policy directory. Back up the file before editing. Append a harmless
synthetic sentence, save it, and run:

```powershell
..\.venv-integration\Scripts\python.exe manage.py ingest_clinic_policies
..\.venv-integration\Scripts\python.exe manage.py shell -c "from clinic_faq.models import PolicyDocument; [print(d.source_filename, d.version, d.indexing_status, d.chunks.count()) for d in PolicyDocument.objects.order_by('source_filename')]"
```

The changed source should report as updated, its version should increase by
exactly one, its current chunks should contain the changed text, and its status
should be pending. Older chunk rows and their embeddings should be gone. Run
`embed_clinic_policies` again; the document should become indexed.

To check removal, move that same test file outside the approved directory (do
not rename it to another extension inside the directory), then run:

```powershell
..\.venv-integration\Scripts\python.exe manage.py ingest_clinic_policies
..\.venv-integration\Scripts\python.exe manage.py shell -c "from clinic_faq.models import PolicyDocument; [print(d.source_filename, d.version, d.is_active, d.indexing_status, d.chunks.count()) for d in PolicyDocument.objects.order_by('source_filename')]"
```

The removed source should report `deactivated=1`; its row and version/hash
metadata remain, `is_active` is false, its status is inactive, and its chunk
count is zero. Restore the file and ingest again: the row should become active,
have chunks, and retain its version if the content is unchanged (otherwise the
content change increments the version).

## Automated checks

Run the focused tests and Django checks from `backend/`:

```powershell
..\.venv-integration\Scripts\python.exe manage.py test clinic_faq.tests_ingestion clinic_faq.tests_embeddings clinic_faq.tests_retrieval
..\.venv-integration\Scripts\python.exe manage.py check
..\.venv-integration\Scripts\python.exe manage.py makemigrations --check --dry-run
```

The focused tests use temporary approved directories and mock local embeddings;
they require no live embedding-model download or Ollama instance.
