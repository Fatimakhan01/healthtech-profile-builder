# Clinic FAQ document lifecycle

`PolicyDocument` remains the single record for each approved source filename.
It stores the current content SHA-256, chunk settings, current `version`,
approval/activity flags, and `indexing_status`. New records start at version 1.
A changed source hash increments the version and appends the superseded version's
title, hash, and timestamp to `version_history`; historical source text and
embeddings are not retained. Changing chunk settings rebuilds the index without
claiming that the source content itself changed.

Each `PolicyChunk` is stamped with `document_version`. Ingestion extracts and
chunks before writing, then saves the document and replaces its chunks within
one database transaction. A failure rolls back both the document metadata and
chunk changes. Identical source bytes and chunk settings are idempotent and do
not produce a new version or chunks. Re-activating an unchanged source reuses
its version but rebuilds chunks that were removed at deactivation.

Files in `clinic_faq/policies/approved/` are the approval boundary. A successful
ingestion marks those documents approved and active, with indexing pending
until local embedding completes. Removing a source and running ingestion
deactivates its row and deletes its chunks, while retaining document metadata
and version history. Re-adding that filename reactivates and indexes it.

The local embedding command processes only active, approved documents whose
source hash and stored chunks match the approved files. It marks a document
pending before re-embedding and marks it indexed only when every current chunk
has a valid embedding for the configured model. Retrieval independently
requires an approved, active, indexed document and a chunk stamped with its
current version; it also checks the approved source, text hash, model, vector,
and dimensions. Thus stale embeddings and removed documents cannot be returned.
The migration keeps previously ingested rows approved and active, but they
remain pending until the embedding command verifies their current vectors.
