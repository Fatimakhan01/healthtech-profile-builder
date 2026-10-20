# Database schema, constraints, and indexes

This diagram is derived from `accounts/models.py`, `profiles/models.py`, their initial migrations, and a read-only PostgreSQL inspection performed on 2026-10-19. PostgreSQL 18.4 was reachable through the configured Django connection. The `accounts_user` and `profiles_healthprofile` tables, the email uniqueness indexes, the one-to-one unique index, and the profile listing index were present in that database. Fresh installations must still provision their own PostgreSQL database and apply migrations.

## Entity relationship

```mermaid
erDiagram
    accounts_user ||--o| profiles_healthprofile : "owns (CASCADE on delete)"

    accounts_user {
        bigint id PK
        varchar email UK "normalized lowercase"
        varchar role
        boolean is_active
        datetime date_joined
        varchar password "Django password hash"
        datetime last_login
        boolean is_superuser
    }

    profiles_healthprofile {
        bigint id PK
        bigint user_id FK_UK
        varchar full_name
        varchar age_range
        varchar contact_preference
        varchar wellness_goals
        varchar allergies
        varchar emergency_contact_name
        varchar emergency_contact_relationship
        varchar emergency_contact_phone
        varchar lifestyle_notes
        boolean is_active
        datetime created_at
        datetime updated_at
    }
```

The relationship is one-to-zero-or-one from `accounts_user` to `profiles_healthprofile`: a profile must reference exactly one user, while the model permits a user to have no profile (for example, an administrator). The foreign key is a Django `OneToOneField` with `on_delete=CASCADE`; deleting a user cascades to that user's profile. Standard signup creates its initial profile in the serializer transaction.

The custom user model inherits Django's `AbstractBaseUser` and `PermissionsMixin`; therefore its table also includes the inherited password hash, last-login and superuser fields. Django's `groups` and `user_permissions` many-to-many relations use their usual auxiliary tables. `is_staff` is a Python property derived from the administrator role or superuser status, not a separate user-table column.

Age is represented by the optional `age_range` choices, not a precise date of birth. The profile intentionally does not contain clinical diagnoses. Optional contact and wellness fields use blank strings rather than nullable values.

## Constraints and indexes

| Name / definition | Table and columns | Unique? | Evidence and purpose |
|---|---|---:|---|
| `accounts_user_pkey` | `accounts_user(id)` | Yes | Django primary key. |
| `accounts_user_email_key` | `accounts_user(email)` | Yes | Model field `unique=True`; exact normalized-email uniqueness and Django's username-field requirement. |
| `accounts_user_email_ci_unique` | `accounts_user(lower(email))` | Yes | Migration `accounts.0001_initial`; enforces case-insensitive uniqueness even if a write bypasses application normalization. |
| `profiles_healthprofile_pkey` | `profiles_healthprofile(id)` | Yes | Django primary key. |
| `profiles_healthprofile_user_id_key` | `profiles_healthprofile(user_id)` | Yes | Unique index created by the one-to-one relation; at most one profile per user. |
| `profiles_healthprofile_user_id_45e16cb1_fk_accounts_user_id` | `profiles_healthprofile(user_id)` → `accounts_user(id)` | No | Foreign-key constraint; profile ownership and cascade deletion. |
| `profiles_active_created_idx` | `profiles_healthprofile(is_active, created_at DESC)` | No | Declared in `profiles.0001_initial`; supports admin listing by status and creation recency. |

PostgreSQL catalog inspection confirmed the named unique indexes, foreign key, and profile index in the configured database during the date above. The two auto-generated Django table names shown for the user foreign key and one-to-one index come from that database; Django's migration/model semantics are the durable definition.
