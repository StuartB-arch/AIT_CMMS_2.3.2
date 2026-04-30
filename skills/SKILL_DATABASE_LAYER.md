# Skill: SQLite Database Layer with Connection Pooling

## When to Use This Skill
- Python desktop or CLI applications
- Single-machine or small LAN deployment (up to ~10 concurrent users)
- No DBA or server required
- Need ACID transactions, foreign keys, full SQL

## Complete Database Layer Implementation

### connection.py — Thread-Safe Connection Pool

```python
# database/connection.py
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

DB_PATH = Path(__file__).parent.parent / "app.db"


class DatabasePool:
    """Thread-local SQLite connection pool (singleton)."""
    _instance: 'DatabasePool | None' = None
    _lock = threading.Lock()

    def __init__(self, db_path: Path = DB_PATH):
        self._db_path = db_path
        self._local = threading.local()

    @classmethod
    def get_instance(cls, db_path: Path = DB_PATH) -> 'DatabasePool':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(db_path)
        return cls._instance

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")     # Concurrent reads while writing
        conn.execute("PRAGMA foreign_keys=ON")       # Enforce FK constraints
        conn.execute("PRAGMA synchronous=NORMAL")    # Balance safety vs speed
        conn.execute("PRAGMA cache_size=-64000")     # 64 MB page cache
        conn.execute("PRAGMA temp_store=MEMORY")     # Temp tables in memory
        return conn

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = self._open()
        return self._local.conn

    @contextmanager
    def get_cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Cursor, None, None]:
        """Explicit transaction — use for multi-statement operations."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("BEGIN")
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self.get_cursor() as cursor:
            cursor.execute(sql, params)
            return cursor

    def fetchone(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self.get_cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self.get_cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall()

    def close_all(self):
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
```

### schema.py — Schema Management with Migrations

```python
# database/schema.py
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 3

MIGRATIONS = {
    1: [
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT,
            role TEXT DEFAULT 'User',
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            action TEXT,
            table_name TEXT,
            record_id TEXT,
            old_values TEXT,
            new_values TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    ],
    2: [
        "ALTER TABLE users ADD COLUMN email TEXT",
        "ALTER TABLE users ADD COLUMN notes TEXT",
    ],
    3: [
        """
        CREATE TABLE IF NOT EXISTS user_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),
            username TEXT,
            login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP,
            logout_time TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
        """,
    ],
}


def get_current_version(db) -> int:
    try:
        row = db.fetchone("SELECT MAX(version) as v FROM schema_version")
        return row['v'] or 0
    except sqlite3.OperationalError:
        return 0


def migrate(db):
    current = get_current_version(db)
    for version in sorted(MIGRATIONS.keys()):
        if version > current:
            with db.transaction() as cursor:
                for sql in MIGRATIONS[version]:
                    cursor.execute(sql)
                cursor.execute(
                    "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                    (version,)
                )
            print(f"Applied migration {version}")
```

### repository.py — Repository Pattern

```python
# database/repository.py
import json
from datetime import datetime
from typing import Any

class BaseRepository:
    def __init__(self, db, table: str, pk: str = 'id'):
        self.db = db
        self.table = table
        self.pk = pk

    def get_by_id(self, id_value) -> dict | None:
        row = self.db.fetchone(
            f"SELECT * FROM {self.table} WHERE {self.pk} = ?",
            (id_value,)
        )
        return dict(row) if row else None

    def get_all(self, where: str = '', params: tuple = ()) -> list[dict]:
        sql = f"SELECT * FROM {self.table}"
        if where:
            sql += f" WHERE {where}"
        return [dict(r) for r in self.db.fetchall(sql, params)]

    def search(self, columns: list[str], query: str) -> list[dict]:
        conditions = ' OR '.join([f"{col} LIKE ?" for col in columns])
        params = tuple(f"%{query}%" for _ in columns)
        return [dict(r) for r in self.db.fetchall(
            f"SELECT * FROM {self.table} WHERE {conditions}", params
        )]

    def insert(self, data: dict) -> int:
        data['created_at'] = datetime.now().isoformat()
        cols = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        with self.db.get_cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {self.table} ({cols}) VALUES ({placeholders})",
                tuple(data.values())
            )
            return cursor.lastrowid

    def update(self, id_value, data: dict) -> bool:
        data['updated_at'] = datetime.now().isoformat()
        set_clause = ', '.join([f"{k} = ?" for k in data.keys()])
        params = tuple(data.values()) + (id_value,)
        with self.db.get_cursor() as cursor:
            cursor.execute(
                f"UPDATE {self.table} SET {set_clause} WHERE {self.pk} = ?",
                params
            )
            return cursor.rowcount > 0

    def delete(self, id_value) -> bool:
        with self.db.get_cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {self.table} WHERE {self.pk} = ?",
                (id_value,)
            )
            return cursor.rowcount > 0

    def count(self, where: str = '', params: tuple = ()) -> int:
        sql = f"SELECT COUNT(*) FROM {self.table}"
        if where:
            sql += f" WHERE {where}"
        row = self.db.fetchone(sql, params)
        return row[0]


# Domain-specific example:
class EquipmentRepository(BaseRepository):
    def __init__(self, db):
        super().__init__(db, 'equipment', 'asset_id')

    def get_active(self) -> list[dict]:
        return self.get_all(where="status = 'Active'")

    def get_due_for_pm(self, pm_type: str) -> list[dict]:
        col = f"next_pm_{pm_type.lower()}"
        return self.get_all(
            where=f"status = 'Active' AND {col} IS NOT NULL AND {col} <= date('now')"
        )

    def update_pm_dates(self, asset_id: str, pm_type: str, completed_date: str, next_date: str):
        self.update(asset_id, {
            f"last_pm_{pm_type.lower()}": completed_date,
            f"next_pm_{pm_type.lower()}": next_date,
        })
```

## Useful SQLite Pragmas Reference

| Pragma | Value | Effect |
|--------|-------|--------|
| `journal_mode` | `WAL` | Readers don't block writers. Best for concurrent access. |
| `foreign_keys` | `ON` | Enforce referential integrity. Off by default! |
| `synchronous` | `NORMAL` | Safe + fast. `FULL` is safer but slower. |
| `cache_size` | `-64000` | 64 MB page cache (negative = kilobytes) |
| `temp_store` | `MEMORY` | Temp tables in RAM, not disk |
| `busy_timeout` | `5000` | Wait 5s before "database is locked" error |

## SQLite Type Affinity (vs PostgreSQL)

| PostgreSQL Type | SQLite Equivalent | Notes |
|----------------|-------------------|-------|
| `SERIAL` | `INTEGER PRIMARY KEY AUTOINCREMENT` | |
| `BOOLEAN` | `INTEGER` (0/1) | No native bool |
| `BYTEA` | `BLOB` | Binary data |
| `JSONB` | `TEXT` | Store as JSON string |
| `TIMESTAMP` | `TEXT` (ISO 8601) | `datetime('now')` works |
| `DATE` | `TEXT` (YYYY-MM-DD) | |
| `DECIMAL(x,y)` | `REAL` | |

## Performance Tips

1. **Indexes on every FK and frequent WHERE column:**
   ```sql
   CREATE INDEX IF NOT EXISTS idx_equipment_status ON equipment(status);
   CREATE INDEX IF NOT EXISTS idx_pm_asset ON pm_completions(asset_id);
   ```

2. **Use `INSERT OR IGNORE` for upserts (SQLite style):**
   ```sql
   INSERT OR IGNORE INTO equipment (asset_id, name) VALUES (?, ?)
   -- or
   INSERT INTO equipment (asset_id, name) VALUES (?, ?)
   ON CONFLICT(asset_id) DO UPDATE SET name = excluded.name
   ```

3. **Batch inserts with `executemany`:**
   ```python
   with db.transaction() as cursor:
       cursor.executemany(
           "INSERT INTO equipment (asset_id, name) VALUES (?, ?)",
           [(row['id'], row['name']) for row in csv_data]
       )
   ```

4. **EXPLAIN QUERY PLAN to debug slow queries:**
   ```sql
   EXPLAIN QUERY PLAN SELECT * FROM equipment WHERE status = 'Active';
   ```
