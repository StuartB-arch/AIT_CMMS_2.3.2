# Skill: Audit Trail & Compliance Logging

## When to Use
- Any system that must prove who changed what and when
- Regulatory compliance (ISO, FAA, SOX, HIPAA, etc.)
- Multi-user systems where accountability matters
- Anywhere "undo" or "dispute resolution" is needed

## Schema

```sql
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Who
    username TEXT NOT NULL,
    user_id INTEGER,
    -- What action
    action TEXT NOT NULL,           -- INSERT / UPDATE / DELETE / LOGIN / EXPORT / APPROVE
    -- On what
    table_name TEXT,
    record_id TEXT,
    -- Before and after
    old_values TEXT,                -- JSON of old field values
    new_values TEXT,                -- JSON of new field values
    -- Context
    notes TEXT,                     -- Human-readable summary
    session_id INTEGER,             -- Link to user_sessions if applicable
    ip_address TEXT,                -- If web app
    -- When
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for fast queries by table+record
CREATE INDEX idx_audit_table_record ON audit_log(table_name, record_id);
-- Index for queries by user
CREATE INDEX idx_audit_username ON audit_log(username);
-- Index for time-range queries
CREATE INDEX idx_audit_created ON audit_log(created_at);
```

## AuditLogger Class

```python
# utils/audit.py
import json
from datetime import datetime
from typing import Any

class AuditLogger:
    def __init__(self, db, session=None):
        self.db = db
        self.session = session  # Optional: current UserSession

    def log(
        self,
        action: str,
        table_name: str = None,
        record_id: Any = None,
        old_values: dict = None,
        new_values: dict = None,
        notes: str = None,
        username: str = None,
    ) -> int:
        username = username or (self.session.username if self.session else 'system')
        user_id = self.session.user_id if self.session else None
        session_id = self.session.session_id if self.session else None

        with self.db.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO audit_log
                    (username, user_id, action, table_name, record_id,
                     old_values, new_values, notes, session_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                username,
                user_id,
                action,
                table_name,
                str(record_id) if record_id is not None else None,
                json.dumps(old_values, default=str) if old_values else None,
                json.dumps(new_values, default=str) if new_values else None,
                notes,
                session_id,
                datetime.now().isoformat(),
            ))
            return cursor.lastrowid

    # Convenience methods
    def log_insert(self, table: str, record_id: Any, new_values: dict, notes: str = None):
        return self.log('INSERT', table, record_id, new_values=new_values, notes=notes)

    def log_update(self, table: str, record_id: Any, old_values: dict, new_values: dict, notes: str = None):
        # Only log fields that actually changed
        changed_old = {k: v for k, v in old_values.items() if new_values.get(k) != v}
        changed_new = {k: new_values[k] for k in changed_old}
        if not changed_old:
            return None  # Nothing changed
        return self.log('UPDATE', table, record_id,
                        old_values=changed_old, new_values=changed_new, notes=notes)

    def log_delete(self, table: str, record_id: Any, old_values: dict, notes: str = None):
        return self.log('DELETE', table, record_id, old_values=old_values, notes=notes)

    def log_login(self, username: str):
        return self.log('LOGIN', notes=f"User {username} logged in", username=username)

    def log_logout(self, username: str):
        return self.log('LOGOUT', notes=f"User {username} logged out", username=username)

    def log_export(self, export_type: str, record_count: int):
        return self.log('EXPORT', notes=f"Exported {record_count} {export_type} records")

    def log_approve(self, table: str, record_id: Any, notes: str = None):
        return self.log('APPROVE', table, record_id, notes=notes)

    # Query methods
    def get_history(self, table: str = None, record_id: Any = None,
                    username: str = None, limit: int = 100) -> list[dict]:
        conditions = []
        params = []

        if table:
            conditions.append("table_name = ?")
            params.append(table)
        if record_id:
            conditions.append("record_id = ?")
            params.append(str(record_id))
        if username:
            conditions.append("username = ?")
            params.append(username)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ''
        rows = self.db.fetchall(
            f"SELECT * FROM audit_log {where} ORDER BY created_at DESC LIMIT ?",
            tuple(params) + (limit,)
        )
        return [dict(r) for r in rows]

    def get_record_history(self, table: str, record_id: Any) -> list[dict]:
        return self.get_history(table=table, record_id=record_id)

    def get_user_activity(self, username: str, days: int = 30) -> list[dict]:
        rows = self.db.fetchall("""
            SELECT * FROM audit_log
            WHERE username = ?
            AND created_at >= datetime('now', ?)
            ORDER BY created_at DESC
        """, (username, f'-{days} days'))
        return [dict(r) for r in rows]
```

## Automatic Audit via Decorator

```python
# Decorator pattern for automatic before/after capture
import functools

def audited(table: str, id_field: str = 'id'):
    """Decorator that automatically logs UPDATE operations."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, record_id, data: dict, *args, **kwargs):
            # Capture before state
            old = self.get_by_id(record_id)

            result = func(self, record_id, data, *args, **kwargs)

            # Capture after state
            new = self.get_by_id(record_id)
            if old and new:
                self.audit.log_update(table, record_id, dict(old), dict(new))
            return result
        return wrapper
    return decorator

# Usage:
class EquipmentService:
    def __init__(self, db, audit: AuditLogger):
        self.db = db
        self.audit = audit

    @audited('equipment', 'asset_id')
    def update_equipment(self, asset_id: str, data: dict) -> bool:
        # audit happens automatically
        return self.repo.update(asset_id, data)
```

## Audit Trail UI Widget

```python
# ui/widgets/audit_history_widget.py
import tkinter as tk
from tkinter import ttk
import json
from datetime import datetime

class AuditHistoryWidget(ttk.Frame):
    """Embeddable audit history viewer for any record."""

    def __init__(self, parent, audit_logger, table: str, record_id):
        super().__init__(parent)
        self.audit = audit_logger
        self.table = table
        self.record_id = record_id
        self._build()
        self.refresh()

    def _build(self):
        # Header
        header = ttk.Frame(self)
        header.pack(fill='x', pady=4)
        ttk.Label(header, text="Change History", font=('Helvetica', 10, 'bold')).pack(side='left')
        ttk.Button(header, text="Refresh", command=self.refresh).pack(side='right')

        # Tree
        cols = ('Date/Time', 'User', 'Action', 'Changes')
        self.tree = ttk.Treeview(self, columns=cols, show='headings', height=8)
        self.tree.heading('Date/Time', text='Date/Time')
        self.tree.heading('User', text='User')
        self.tree.heading('Action', text='Action')
        self.tree.heading('Changes', text='Changes')
        self.tree.column('Date/Time', width=140)
        self.tree.column('User', width=100)
        self.tree.column('Action', width=70)
        self.tree.column('Changes', width=400)

        sb = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        records = self.audit.get_record_history(self.table, self.record_id)
        for r in records:
            ts = r.get('created_at', '')
            try:
                ts = datetime.fromisoformat(ts).strftime('%Y-%m-%d %H:%M')
            except Exception:
                pass

            # Summarize changes
            changes = ''
            if r.get('old_values') and r.get('new_values'):
                try:
                    old = json.loads(r['old_values'])
                    new = json.loads(r['new_values'])
                    parts = [f"{k}: {old.get(k)} → {new.get(k)}" for k in new]
                    changes = ' | '.join(parts[:3])  # Show first 3 changes
                    if len(parts) > 3:
                        changes += f' (+{len(parts)-3} more)'
                except Exception:
                    changes = r.get('notes', '')

            self.tree.insert('', 'end', values=(
                ts, r.get('username', ''), r.get('action', ''), changes
            ))
```

## What to Audit

| Action Type | When to Log |
|-------------|------------|
| `INSERT` | New record created |
| `UPDATE` | Any field changed |
| `DELETE` | Record deleted |
| `LOGIN` | User authenticated |
| `LOGOUT` | User session ended |
| `FAILED_LOGIN` | Bad password attempt |
| `EXPORT` | Data exported to CSV/PDF |
| `IMPORT` | Data imported from CSV |
| `APPROVE` | Manager approval of action |
| `BACKUP` | Database backup created |
| `RESTORE` | Database restored |
| `PASSWORD_CHANGE` | Password changed |
| `ROLE_CHANGE` | User role changed |
| `STATUS_CHANGE` | Equipment status changed |

## Compliance Query Examples

```sql
-- All changes to a specific piece of equipment
SELECT * FROM audit_log
WHERE table_name = 'equipment' AND record_id = 'EQ-001'
ORDER BY created_at DESC;

-- All actions by a specific user in the last 30 days
SELECT * FROM audit_log
WHERE username = 'jsmith'
AND created_at >= datetime('now', '-30 days')
ORDER BY created_at DESC;

-- All equipment status changes
SELECT * FROM audit_log
WHERE action = 'STATUS_CHANGE'
ORDER BY created_at DESC;

-- All deletions (for security investigation)
SELECT * FROM audit_log
WHERE action = 'DELETE'
ORDER BY created_at DESC;

-- Login activity summary
SELECT username, COUNT(*) as login_count, MAX(created_at) as last_login
FROM audit_log
WHERE action = 'LOGIN'
GROUP BY username
ORDER BY last_login DESC;
```
