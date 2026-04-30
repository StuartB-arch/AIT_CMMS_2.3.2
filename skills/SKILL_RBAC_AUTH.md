# Skill: Role-Based Access Control (RBAC) + Authentication

## Pattern Overview

Users have a single role. Each role has a set of permissions. The UI and API both check permissions before allowing actions.

```
User → Role → Permissions → Allowed Actions
```

## Authentication Implementation

### Password Hashing (Secure)

```python
# utils/auth.py
import hashlib
import secrets
import hmac

# Option 1: SHA256 + salt (minimal, acceptable for low-risk desktop apps)
def hash_password_sha256(password: str) -> str:
    salt = secrets.token_hex(32)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{hashed}"

def verify_password_sha256(password: str, stored: str) -> bool:
    salt, hashed = stored.split(':', 1)
    expected = hashlib.sha256((salt + password).encode()).hexdigest()
    return hmac.compare_digest(expected, hashed)

# Option 2: bcrypt (recommended for production)
# pip install bcrypt
import bcrypt

def hash_password_bcrypt(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

def verify_password_bcrypt(password: str, stored: str) -> bool:
    return bcrypt.checkpw(password.encode(), stored.encode())
```

### Login Function

```python
from datetime import datetime

def login(username: str, password: str, db) -> dict | None:
    """Returns user dict if authenticated, None if not."""
    row = db.fetchone(
        "SELECT * FROM users WHERE username = ? AND is_active = 1",
        (username,)
    )
    if not row:
        return None

    if not verify_password_sha256(password, row['password_hash']):
        # Log failed attempt
        log_audit(None, 'LOGIN_FAILED', 'users', username, notes=f"Failed login for {username}")
        return None

    # Update last login
    db.execute(
        "UPDATE users SET last_login = ? WHERE id = ?",
        (datetime.now().isoformat(), row['id'])
    )

    # Create session
    with db.get_cursor() as cursor:
        cursor.execute(
            "INSERT INTO user_sessions (user_id, username, login_time, is_active) VALUES (?,?,?,1)",
            (row['id'], row['username'], datetime.now().isoformat())
        )
        session_id = cursor.lastrowid

    user = dict(row)
    user['session_id'] = session_id
    log_audit(username, 'LOGIN', 'users', str(row['id']))
    return user
```

## RBAC Schema

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    role TEXT NOT NULL DEFAULT 'Viewer',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP,
    failed_login_count INTEGER DEFAULT 0,
    locked_until TIMESTAMP
);
```

## Permission Registry

```python
# utils/permissions.py

ROLE_PERMISSIONS: dict[str, set[str]] = {
    'Admin': {
        'user.create', 'user.read', 'user.update', 'user.delete',
        'role.assign',
        'equipment.create', 'equipment.read', 'equipment.update', 'equipment.delete',
        'pm.schedule', 'pm.complete', 'pm.approve',
        'wo.create', 'wo.read', 'wo.update', 'wo.close', 'wo.delete',
        'inventory.create', 'inventory.read', 'inventory.update', 'inventory.delete',
        'inventory.adjust',
        'report.view', 'report.export',
        'backup.create', 'backup.restore',
        'config.edit',
    },
    'Manager': {
        'user.read',
        'equipment.create', 'equipment.read', 'equipment.update',
        'pm.schedule', 'pm.complete', 'pm.approve',
        'wo.create', 'wo.read', 'wo.update', 'wo.close',
        'inventory.read', 'inventory.adjust',
        'report.view', 'report.export',
        'backup.create',
    },
    'Technician': {
        'equipment.read',
        'pm.complete',
        'wo.create', 'wo.read', 'wo.update',
        'inventory.read',
        'report.view',
    },
    'Viewer': {
        'equipment.read',
        'pm.complete',   # Record their own completions
        'wo.read',
        'inventory.read',
    },
    'Parts Coordinator': {
        'equipment.read',
        'inventory.create', 'inventory.read', 'inventory.update', 'inventory.adjust',
        'wo.read',
        'report.view', 'report.export',
    },
}


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def require_permission(role: str, permission: str):
    """Raise if role lacks permission. Use as a guard."""
    if not has_permission(role, permission):
        raise PermissionError(f"Role '{role}' does not have permission '{permission}'")
```

## Session Context

```python
# utils/session.py
from dataclasses import dataclass

@dataclass
class UserSession:
    user_id: int
    username: str
    full_name: str
    role: str
    session_id: int

    def can(self, permission: str) -> bool:
        from utils.permissions import has_permission
        return has_permission(self.role, permission)

    def require(self, permission: str):
        from utils.permissions import require_permission
        require_permission(self.role, permission)

    def is_manager_or_above(self) -> bool:
        return self.role in ('Admin', 'Manager')

# Global session (desktop app — one user at a time)
_current_session: UserSession | None = None

def get_session() -> UserSession:
    if _current_session is None:
        raise RuntimeError("No active session")
    return _current_session

def set_session(session: UserSession):
    global _current_session
    _current_session = session

def clear_session():
    global _current_session
    _current_session = None
```

## Tkinter UI Gating

```python
# In any UI class:
from utils.session import get_session

class MainWindow:
    def _build_toolbar(self):
        session = get_session()

        if session.can('user.create'):
            ttk.Button(self.toolbar, text="Manage Users",
                       command=self._open_user_management).pack(side='right')

        if session.can('backup.create'):
            ttk.Button(self.toolbar, text="Backup DB",
                       command=self._backup).pack(side='right')

    def _open_user_management(self):
        # Double-check even on action (defense in depth)
        session = get_session()
        session.require('user.create')
        UserManagementDialog(self.root, session).show()
```

## Login Dialog

```python
# ui/dialogs/login_dialog.py
import tkinter as tk
from tkinter import ttk, messagebox
from utils.auth import login
from utils.session import UserSession, set_session

class LoginDialog(tk.Toplevel):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.result: UserSession | None = None

        self.title("Login")
        self.resizable(False, False)
        self.grab_set()  # Modal

        self._build()
        self._center()

    def _build(self):
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill='both', expand=True)

        ttk.Label(frame, text="Username:").grid(row=0, column=0, sticky='e', pady=5)
        self._username = ttk.Entry(frame, width=25)
        self._username.grid(row=0, column=1, pady=5)
        self._username.focus()

        ttk.Label(frame, text="Password:").grid(row=1, column=0, sticky='e', pady=5)
        self._password = ttk.Entry(frame, width=25, show='*')
        self._password.grid(row=1, column=1, pady=5)
        self._password.bind('<Return>', lambda _: self._attempt_login())

        ttk.Button(frame, text="Login", command=self._attempt_login).grid(
            row=2, column=0, columnspan=2, pady=15
        )

    def _attempt_login(self):
        username = self._username.get().strip()
        password = self._password.get()

        if not username or not password:
            messagebox.showerror("Error", "Username and password required", parent=self)
            return

        user = login(username, password, self.db)
        if not user:
            messagebox.showerror("Error", "Invalid username or password", parent=self)
            self._password.delete(0, 'end')
            return

        self.result = UserSession(
            user_id=user['id'],
            username=user['username'],
            full_name=user['full_name'] or user['username'],
            role=user['role'],
            session_id=user['session_id'],
        )
        set_session(self.result)
        self.destroy()

    def _center(self):
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")
```

## Account Lockout (Anti-Brute-Force)

```python
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

def login_with_lockout(username: str, password: str, db) -> dict | None:
    from datetime import datetime, timedelta

    row = db.fetchone(
        "SELECT * FROM users WHERE username = ? AND is_active = 1",
        (username,)
    )
    if not row:
        return None

    # Check lockout
    if row['locked_until']:
        locked_until = datetime.fromisoformat(row['locked_until'])
        if datetime.now() < locked_until:
            remaining = int((locked_until - datetime.now()).total_seconds() / 60)
            raise PermissionError(f"Account locked. Try again in {remaining} minutes.")
        else:
            # Lockout expired — reset counter
            db.execute(
                "UPDATE users SET failed_login_count=0, locked_until=NULL WHERE id=?",
                (row['id'],)
            )

    if not verify_password_sha256(password, row['password_hash']):
        new_count = (row['failed_login_count'] or 0) + 1
        if new_count >= MAX_FAILED_ATTEMPTS:
            locked_until = (datetime.now() + timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
            db.execute(
                "UPDATE users SET failed_login_count=?, locked_until=? WHERE id=?",
                (new_count, locked_until, row['id'])
            )
            raise PermissionError(f"Too many failed attempts. Account locked for {LOCKOUT_MINUTES} minutes.")
        else:
            db.execute(
                "UPDATE users SET failed_login_count=? WHERE id=?",
                (new_count, row['id'])
            )
        return None

    # Success — reset lockout
    db.execute(
        "UPDATE users SET failed_login_count=0, locked_until=NULL, last_login=? WHERE id=?",
        (datetime.now().isoformat(), row['id'])
    )
    return dict(row)
```

## Security Checklist

- [ ] Passwords hashed (bcrypt or SHA256+salt, never plaintext)
- [ ] `hmac.compare_digest` used for hash comparison (prevents timing attacks)
- [ ] Failed login counter with lockout
- [ ] Session records in database (can force-logout users)
- [ ] Permission check on every sensitive action (not just UI gating)
- [ ] Audit log on all user create/modify/delete
- [ ] Default accounts' passwords changed at first run
- [ ] No passwords in source code, config files, or logs
