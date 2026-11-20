# Clinic FAQ retrieval evaluation

- Generated: `2026-11-14T20:11:22.447756+00:00`
- Questions: 20
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- Top-K: 5
- Indexed sources: 4

## Semantic-only versus hybrid

| Method | Recall@1 | Recall@3 | Recall@5 | HitRate@1 | HitRate@3 | HitRate@5 | MRR | Source precision@5 | Source recall@5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| semantic | 0.950 | 1.000 | 1.000 | 0.950 | 1.000 | 1.000 | 0.975 | 0.258 | 1.000 |
| hybrid | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.258 | 1.000 |

Hybrid minus semantic; positive values favor hybrid:

| Metric | Semantic | Hybrid | Difference |
|---|---:|---:|---:|
| reciprocal_rank | 0.975 | 1.000 | +0.025 |
| recall_at_1 | 0.950 | 1.000 | +0.050 |
| hitrate_at_1 | 0.950 | 1.000 | +0.050 |
| source_precision_at_1 | 0.950 | 1.000 | +0.050 |
| source_recall_at_1 | 0.950 | 1.000 | +0.050 |
| recall_at_3 | 1.000 | 1.000 | +0.000 |
| hitrate_at_3 | 1.000 | 1.000 | +0.000 |
| source_precision_at_3 | 0.333 | 0.333 | +0.000 |
| source_recall_at_3 | 1.000 | 1.000 | +0.000 |
| recall_at_5 | 1.000 | 1.000 | +0.000 |
| hitrate_at_5 | 1.000 | 1.000 | +0.000 |
| source_precision_at_5 | 0.258 | 0.258 | +0.000 |
| source_recall_at_5 | 1.000 | 1.000 | +0.000 |

Per-question metric outcomes (hybrid improved / regressed / unchanged):

- reciprocal_rank: 1 / 0 / 19
- recall_at_1: 1 / 0 / 19
- hitrate_at_1: 1 / 0 / 19
- source_precision_at_1: 1 / 0 / 19
- source_recall_at_1: 1 / 0 / 19
- recall_at_3: 0 / 0 / 20
- hitrate_at_3: 0 / 0 / 20
- source_precision_at_3: 0 / 0 / 20
- source_recall_at_3: 0 / 0 / 20
- recall_at_5: 0 / 0 / 20
- hitrate_at_5: 0 / 0 / 20
- source_precision_at_5: 0 / 0 / 20
- source_recall_at_5: 0 / 0 / 20

## Per-question retrieval results

| ID | Expected sources | Semantic sources@5 | Hybrid sources@5 |
|---|---|---|---|
| appointment-request-methods | appointment-scheduling.md | appointment-scheduling.md, late-arrivals.md, cancellations.md, reminders.md | appointment-scheduling.md, cancellations.md, late-arrivals.md, reminders.md |
| appointment-requested-time-confirmation | appointment-scheduling.md | appointment-scheduling.md, late-arrivals.md, reminders.md, cancellations.md | appointment-scheduling.md, cancellations.md, late-arrivals.md, reminders.md |
| appointment-confirmation-details | appointment-scheduling.md | appointment-scheduling.md, reminders.md, cancellations.md, late-arrivals.md | appointment-scheduling.md, reminders.md, cancellations.md, late-arrivals.md |
| appointment-incorrect-confirmation | appointment-scheduling.md | appointment-scheduling.md, cancellations.md, reminders.md, late-arrivals.md | appointment-scheduling.md, cancellations.md, reminders.md, late-arrivals.md |
| appointment-online-request | appointment-scheduling.md | appointment-scheduling.md, cancellations.md, reminders.md, late-arrivals.md | appointment-scheduling.md, cancellations.md, reminders.md, late-arrivals.md |
| cancellation-contact | cancellations.md | cancellations.md, appointment-scheduling.md, reminders.md, late-arrivals.md | cancellations.md, appointment-scheduling.md, reminders.md, late-arrivals.md |
| online-booking-change-request | cancellations.md | cancellations.md, appointment-scheduling.md, reminders.md, late-arrivals.md | cancellations.md, appointment-scheduling.md, reminders.md, late-arrivals.md |
| cancellation-recording-confirmation | cancellations.md | cancellations.md, appointment-scheduling.md, reminders.md | cancellations.md, appointment-scheduling.md, reminders.md |
| change-completion | cancellations.md | appointment-scheduling.md, cancellations.md, late-arrivals.md, reminders.md | cancellations.md, appointment-scheduling.md, late-arrivals.md, reminders.md |
| cancellation-wait-for-confirmation | cancellations.md | cancellations.md, appointment-scheduling.md, reminders.md, late-arrivals.md | cancellations.md, appointment-scheduling.md, reminders.md, late-arrivals.md |
| late-arrival-contact | late-arrivals.md | late-arrivals.md, appointment-scheduling.md, reminders.md | late-arrivals.md, appointment-scheduling.md, reminders.md |
| late-arrival-contact-timing | late-arrivals.md | late-arrivals.md, appointment-scheduling.md, reminders.md, cancellations.md | late-arrivals.md, appointment-scheduling.md, reminders.md, cancellations.md |
| late-arrival-staff-guidance | late-arrivals.md | late-arrivals.md, appointment-scheduling.md, cancellations.md, reminders.md | late-arrivals.md, appointment-scheduling.md, cancellations.md, reminders.md |
| late-arrival-rescheduling | late-arrivals.md | late-arrivals.md, appointment-scheduling.md, cancellations.md, reminders.md | late-arrivals.md, appointment-scheduling.md, cancellations.md, reminders.md |
| late-arrival-availability | late-arrivals.md | late-arrivals.md, appointment-scheduling.md, reminders.md, cancellations.md | late-arrivals.md, appointment-scheduling.md, reminders.md, cancellations.md |
| reminder-contact-method | reminders.md | reminders.md, appointment-scheduling.md, cancellations.md, late-arrivals.md | reminders.md, appointment-scheduling.md, cancellations.md, late-arrivals.md |
| reminder-selected-channel | reminders.md | reminders.md, appointment-scheduling.md, late-arrivals.md, cancellations.md | reminders.md, appointment-scheduling.md, late-arrivals.md, cancellations.md |
| reminder-not-substitute | reminders.md | reminders.md, cancellations.md, appointment-scheduling.md, late-arrivals.md | reminders.md, cancellations.md, appointment-scheduling.md, late-arrivals.md |
| missing-reminder-actions | reminders.md | reminders.md, appointment-scheduling.md, cancellations.md, late-arrivals.md | reminders.md, appointment-scheduling.md, cancellations.md, late-arrivals.md |
| missing-reminder-confirm-details | reminders.md | reminders.md, appointment-scheduling.md, cancellations.md, late-arrivals.md | reminders.md, appointment-scheduling.md, cancellations.md, late-arrivals.md |

## Chunk-size comparison

Alternate chunks were embedded and ranked in memory; no document or chunk rows were changed.

| Configuration | Size / overlap (characters) | Chunks | Mode | Recall@1 | Recall@3 | Recall@5 | MRR | Precision@5 | Recall@5 |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| smaller | 750 / 112 | 4 | semantic | 0.950 | 1.000 | 1.000 | 0.975 | 0.258 | 1.000 |
| smaller | 750 / 112 | 4 | hybrid | 0.850 | 1.000 | 1.000 | 0.917 | 0.250 | 1.000 |
| current_default | 1000 / 150 | 4 | semantic | 0.950 | 1.000 | 1.000 | 0.975 | 0.258 | 1.000 |
| current_default | 1000 / 150 | 4 | hybrid | 0.850 | 1.000 | 1.000 | 0.917 | 0.250 | 1.000 |
| larger | 1500 / 225 | 4 | semantic | 0.950 | 1.000 | 1.000 | 0.975 | 0.258 | 1.000 |
| larger | 1500 / 225 | 4 | hybrid | 0.850 | 1.000 | 1.000 | 0.917 | 0.250 | 1.000 |

Observed chunk-size effect: all three settings produced the same 4 chunks (4 source chunks); there was no measured chunk-count or ranking change between sizes for this short corpus.

Observed in-memory keyword/hybrid trade-off at the current chunk size: Recall@1 0.850 versus semantic 0.950; MRR 0.917 versus 0.975. These alternate-chunk keyword trials use in-process BM25, not PostgreSQL SearchRank.
