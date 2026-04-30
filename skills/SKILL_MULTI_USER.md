# Skill: Multi-User Desktop Application Patterns

## When to Use
- Multiple people need to use the same application and database simultaneously
- Shared SQLite file on a network share (up to ~10 users)
- Need to track who is logged in and what they're doing
- Need to detect/handle conflicting edits

## Session Management

### Schema

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    role TEXT DEFAULT 'User',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP
);

CREATE TABLE user_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER REFERENCES users(id),
    username TEXT,
    hostname TEXT,           -- Computer name — helps track who is where
    login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_activity TIMESTAMP,
    logout_time TIMESTAMP,
    is_active INTEGER DEFAULT 1
);

CREATE INDEX idx_sessions_active ON user_sessions(is_active);
CREATE INDEX idx_sessions_user ON user_sessions(user_id);
```

### Session Manager

```python
# utils/session_manager.py
import socket
from datetime import datetime, timedelta
from threading import Timer

SESSION_TIMEOUT_MINUTES = 60  # Auto-logout after inactivity

class SessionManager:
    def __init__(self, db):
        self.db = db
        self._current_session_id = None
        self._activity_timer = None

    def create_session(self, user_id: int, username: str) -> int:
        hostname = socket.gethostname()
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO user_sessions
                    (user_id, username, hostname, login_time, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (user_id, username, hostname,
                  datetime.now().isoformat(), datetime.now().isoformat()))
            self._current_session_id = cursor.lastrowid

        self._start_activity_timer()
        return self._current_session_id

    def record_activity(self):
        """Call this on any user action to keep session alive."""
        if self._current_session_id:
            self.db.execute(
                "UPDATE user_sessions SET last_activity = ? WHERE id = ?",
                (datetime.now().isoformat(), self._current_session_id)
            )
            self._reset_activity_timer()

    def end_session(self):
        if self._current_session_id:
            self.db.execute("""
                UPDATE user_sessions
                SET logout_time = ?, is_active = 0
                WHERE id = ?
            """, (datetime.now().isoformat(), self._current_session_id))
        self._cancel_activity_timer()
        self._current_session_id = None

    def get_active_sessions(self) -> list[dict]:
        """Returns all currently active sessions — useful for Manager view."""
        rows = self.db.fetchall("""
            SELECT s.*, u.full_name, u.role
            FROM user_sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.is_active = 1
            ORDER BY s.login_time DESC
        """)
        return [dict(r) for r in rows]

    def force_logout_user(self, session_id: int):
        """Manager action: force another user's session to close."""
        self.db.execute("""
            UPDATE user_sessions
            SET logout_time = ?, is_active = 0
            WHERE id = ?
        """, (datetime.now().isoformat(), session_id))

    def cleanup_stale_sessions(self, timeout_minutes: int = 120):
        """Mark sessions as inactive if no activity for timeout_minutes."""
        cutoff = (datetime.now() - timedelta(minutes=timeout_minutes)).isoformat()
        self.db.execute("""
            UPDATE user_sessions
            SET is_active = 0, logout_time = ?
            WHERE is_active = 1
            AND last_activity < ?
            AND logout_time IS NULL
        """, (datetime.now().isoformat(), cutoff))

    def _start_activity_timer(self):
        self._activity_timer = Timer(
            SESSION_TIMEOUT_MINUTES * 60,
            self._on_timeout
        )
        self._activity_timer.daemon = True
        self._activity_timer.start()

    def _reset_activity_timer(self):
        self._cancel_activity_timer()
        self._start_activity_timer()

    def _cancel_activity_timer(self):
        if self._activity_timer:
            self._activity_timer.cancel()
            self._activity_timer = None

    def _on_timeout(self):
        # Called from background thread — use root.after() to touch UI
        self.end_session()
        # Signal UI to show login screen (use callback or event)
```

## Optimistic Concurrency Control

Prevents two users from overwriting each other's changes.

### Schema Pattern

```sql
-- Add version column to any table that needs concurrency protection
ALTER TABLE equipment ADD COLUMN version INTEGER DEFAULT 1;
```

### Implementation

```python
class OptimisticLock:
    def __init__(self, db):
        self.db = db

    def update(
        self,
        table: str,
        key_col: str,
        key_value,
        data: dict,
        expected_version: int
    ) -> bool:
        """
        Returns True if update succeeded.
        Returns False if record was modified by another user (version mismatch).
        """
        data['version'] = expected_version + 1
        data['updated_at'] = datetime.now().isoformat()

        set_clause = ', '.join([f"{k} = ?" for k in data.keys()])
        params = list(data.values()) + [key_value, expected_version]

        with self.db.get_cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET {set_clause} "
                f"WHERE {key_col} = ? AND version = ?",
                params
            )
            return cursor.rowcount > 0

    def get_with_version(self, table: str, key_col: str, key_value) -> dict | None:
        row = self.db.fetchone(
            f"SELECT *, version FROM {table} WHERE {key_col} = ?",
            (key_value,)
        )
        return dict(row) if row else None


# Usage in UI:
class EquipmentEditDialog:
    def __init__(self, parent, db, asset_id):
        self.lock = OptimisticLock(db)
        # Load record AND capture version
        self.record = self.lock.get_with_version('equipment', 'asset_id', asset_id)
        self.original_version = self.record['version']
        # ... build form with self.record values

    def save(self):
        new_data = self._get_form_data()
        success = self.lock.update(
            'equipment', 'asset_id', self.record['asset_id'],
            new_data, self.original_version
        )
        if not success:
            # Someone else changed it while this dialog was open
            messagebox.showerror(
                "Save Failed",
                "This record was modified by another user while you were editing.\n"
                "Please close and re-open the record to see the latest version."
            )
            return
        self.destroy()
```

## Conflict Resolution UI

```python
def show_conflict_dialog(parent, field_conflicts: list[dict]) -> str:
    """
    field_conflicts = [
        {'field': 'location', 'yours': 'Bay 3', 'theirs': 'Bay 4'},
        ...
    ]
    Returns: 'yours' | 'theirs' | 'cancel'
    """
    dialog = tk.Toplevel(parent)
    dialog.title("Edit Conflict Detected")
    dialog.grab_set()

    result = tk.StringVar(value='cancel')

    ttk.Label(dialog, text=(
        "Another user modified this record while you were editing.\n"
        "Choose which version to keep:"
    ), wraplength=400).pack(pady=10, padx=20)

    for conflict in field_conflicts:
        frame = ttk.LabelFrame(dialog, text=conflict['field'])
        frame.pack(fill='x', padx=20, pady=4)
        ttk.Label(frame, text=f"Your version: {conflict['yours']}",
                  foreground='blue').pack(anchor='w', padx=10)
        ttk.Label(frame, text=f"Other version: {conflict['theirs']}",
                  foreground='red').pack(anchor='w', padx=10)

    btn_frame = ttk.Frame(dialog)
    btn_frame.pack(pady=15)
    ttk.Button(btn_frame, text="Keep Mine",
               command=lambda: (result.set('yours'), dialog.destroy())).pack(side='left', padx=5)
    ttk.Button(btn_frame, text="Use Theirs",
               command=lambda: (result.set('theirs'), dialog.destroy())).pack(side='left', padx=5)
    ttk.Button(btn_frame, text="Cancel",
               command=lambda: dialog.destroy()).pack(side='left', padx=5)

    dialog.wait_window()
    return result.get()
```

## SQLite WAL Mode for Concurrent Access

```python
# Enable WAL on every connection — critical for multi-user SQLite
conn.execute("PRAGMA journal_mode=WAL")

# Set a busy timeout so writers wait instead of immediately failing
conn.execute("PRAGMA busy_timeout=5000")   # 5 seconds

# With WAL mode:
# - Multiple readers can read simultaneously while one writer writes
# - Without WAL: readers block during writes
```

## Who Is Online Widget (Manager View)

```python
class ActiveUsersWidget(ttk.Frame):
    def __init__(self, parent, session_manager, refresh_interval_ms=30000):
        super().__init__(parent)
        self.sm = session_manager
        self.refresh_interval = refresh_interval_ms
        self._build()
        self.refresh()

    def _build(self):
        header = ttk.Frame(self)
        header.pack(fill='x')
        ttk.Label(header, text="Active Users", font=('Helvetica', 10, 'bold')).pack(side='left')
        ttk.Button(header, text="Refresh", command=self.refresh).pack(side='right')

        cols = ('User', 'Full Name', 'Role', 'Computer', 'Logged In', 'Last Active')
        self.tree = ttk.Treeview(self, columns=cols, show='headings', height=6)
        for col in cols:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120)
        self.tree.pack(fill='both', expand=True)

        ttk.Button(self, text="Force Logout Selected",
                   command=self._force_logout).pack(pady=5)

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for s in self.sm.get_active_sessions():
            self.tree.insert('', 'end', iid=str(s['id']), values=(
                s['username'], s.get('full_name', ''), s.get('role', ''),
                s.get('hostname', ''), s['login_time'][:16],
                s['last_activity'][:16] if s.get('last_activity') else ''
            ))
        # Auto-refresh
        self.after(self.refresh_interval, self.refresh)

    def _force_logout(self):
        selected = self.tree.selection()
        if not selected:
            return
        session_id = int(selected[0])
        if messagebox.askyesno("Confirm", "Force logout this user?"):
            self.sm.force_logout_user(session_id)
            self.refresh()
```

## Checklist for Multi-User Desktop App

- [ ] Thread-local DB connections (each thread owns its connection)
- [ ] WAL journal mode enabled on every connection
- [ ] `busy_timeout` set (don't fail immediately on lock)
- [ ] Session records in DB with login/logout times
- [ ] `version` column on tables that need conflict detection
- [ ] Optimistic lock on all save operations
- [ ] Conflict UI when version mismatch detected
- [ ] Activity timer resets on every user action
- [ ] Stale session cleanup job runs periodically
- [ ] Manager can see who is online and force-logout
