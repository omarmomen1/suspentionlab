# Progress

Last visited: 2026-06-09T04:40:00Z

- Explored the `src/suspensionlab/backend/database/models` files and `alembic` configurations.
- Ran `python -m alembic check` and discovered a large amount of type mismatch errors (NUMERIC vs UUID) and some removed indices.
- Analyzed `alembic/versions` and found a conflicting generated migration (`86ce1465fd9f_check2.py`) which I removed.
- Diagnosed the cause of the `NUMERIC` vs `UUID` mismatch: SQLite's type affinity resolves `UUID` created by Alembic to `NUMERIC` in the DB schema, while SQLAlchemy models specify `UUID(as_uuid=True)` which Alembic flags as a change.
- Investigating `alembic/env.py` to see if we can use a custom `compare_type` method or update the Alembic logic to natively support SQLAlchemy 2.0 `Uuid` type to avoid these false positives.
