# Skill: Python Desktop Application with Tkinter

## When to Use This Skill
- Building a standalone desktop app with no web server required
- Target users are non-technical (no CLI usage)
- Works offline / on isolated networks
- Windows + Linux + macOS support needed
- Small-to-medium teams (1–50 users)

## Tech Stack

| Component | Choice | Why |
|-----------|--------|-----|
| Language | Python 3.10+ | Rapid dev, huge ecosystem |
| GUI | Tkinter + ttk | Built-in, cross-platform, no install |
| Database | SQLite | Zero-config, single file, no server |
| PDF | ReportLab | Production-quality PDF generation |
| Spreadsheet | openpyxl / pandas | Excel import/export |
| Images | Pillow | All image formats |
| Packaging | PyInstaller | Single .exe with no Python needed |

## Project Structure

```
my_app/
├── main.py                    # Entry point — Tk() + MainApp()
├── app.py                     # Main application class
├── database/
│   ├── __init__.py
│   ├── connection.py          # Connection pool singleton
│   ├── schema.py              # CREATE TABLE statements
│   └── migrations/
│       └── 001_initial.sql
├── modules/
│   ├── __init__.py
│   ├── module_a.py            # One file per major feature domain
│   └── module_b.py
├── ui/
│   ├── __init__.py
│   ├── main_window.py         # Main window with tabs
│   ├── dialogs/
│   │   ├── login_dialog.py
│   │   └── settings_dialog.py
│   └── widgets/
│       └── searchable_table.py
├── utils/
│   ├── auth.py                # Login, password hashing
│   ├── audit.py               # Audit log
│   ├── pdf_generator.py       # ReportLab helpers
│   └── csv_sync.py            # CSV import/export
├── assets/
│   └── logo.png
├── backups/                   # Auto-created at runtime
├── requirements.txt
└── README.md
```

## Main Entry Point Pattern

```python
# main.py
import tkinter as tk
from app import MainApp

def main():
    root = tk.Tk()
    root.title("My Application v1.0")

    # DPI scaling for high-res displays
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI
    except Exception:
        pass

    # Get screen dimensions
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()

    # Scale fonts based on resolution
    scale = 2.0 if screen_h >= 2160 else 1.6 if screen_h >= 1440 else 1.3
    default_font_size = int(10 * scale)

    import tkinter.font as tkfont
    default_font = tkfont.nametofont("TkDefaultFont")
    default_font.configure(size=default_font_size)

    app = MainApp(root)
    root.state('zoomed')  # Start maximized
    root.mainloop()

if __name__ == "__main__":
    main()
```

## Main Application Class Pattern

```python
# app.py
import tkinter as tk
from tkinter import ttk, messagebox

class MainApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.current_user = None
        self.current_role = None

        self._init_database()
        self._show_login()

    def _init_database(self):
        from database.connection import DatabasePool
        from database.schema import create_tables
        self.db = DatabasePool.get_instance()
        create_tables(self.db)

    def _show_login(self):
        from ui.dialogs.login_dialog import LoginDialog
        dialog = LoginDialog(self.root)
        self.root.wait_window(dialog)

        if dialog.authenticated_user:
            self.current_user = dialog.authenticated_user
            self.current_role = dialog.authenticated_role
            self._build_ui()
        else:
            self.root.destroy()

    def _build_ui(self):
        # Toolbar
        self._create_toolbar()

        # Tabbed notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True)

        # Add tabs based on role
        self._add_tab_equipment()
        if self.current_role in ('Manager', 'Supervisor'):
            self._add_tab_admin()

    def _create_toolbar(self):
        toolbar = ttk.Frame(self.root)
        toolbar.pack(side='top', fill='x', pady=2)

        ttk.Label(toolbar, text=f"User: {self.current_user}").pack(side='left', padx=10)
        ttk.Label(toolbar, text=f"Role: {self.current_role}").pack(side='left', padx=10)
        ttk.Button(toolbar, text="Logout", command=self._logout).pack(side='right', padx=5)

    def _logout(self):
        if messagebox.askyesno("Logout", "Are you sure you want to logout?"):
            self.root.destroy()

    def _add_tab_equipment(self):
        from ui.tabs.equipment_tab import EquipmentTab
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="Equipment")
        EquipmentTab(frame, self.db, self.current_user, self.current_role)
```

## Database Connection Pool Pattern

```python
# database/connection.py
import sqlite3
from contextlib import contextmanager
from pathlib import Path
import threading

DB_PATH = Path(__file__).parent.parent / "app_data.db"

class DatabasePool:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._local = threading.local()

    @classmethod
    def get_instance(cls) -> 'DatabasePool':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")   # Better concurrent reads
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def get_cursor(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
```

## Schema Pattern

```python
# database/schema.py
TABLES = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT,
        role TEXT NOT NULL DEFAULT 'User',
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
]

def create_tables(db):
    with db.get_cursor() as cursor:
        for sql in TABLES:
            cursor.execute(sql)
```

## Searchable Table Widget

```python
# ui/widgets/searchable_table.py
import tkinter as tk
from tkinter import ttk

class SearchableTable(ttk.Frame):
    def __init__(self, parent, columns: list[tuple], on_select=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.on_select = on_select
        self._build(columns)

    def _build(self, columns):
        # Search bar
        search_frame = ttk.Frame(self)
        search_frame.pack(fill='x', pady=5)
        ttk.Label(search_frame, text="Search:").pack(side='left')
        self._search_var = tk.StringVar()
        self._search_var.trace_add('write', lambda *_: self._filter())
        ttk.Entry(search_frame, textvariable=self._search_var, width=40).pack(side='left', padx=5)
        ttk.Button(search_frame, text="Clear", command=self._clear_search).pack(side='left')

        # Treeview
        self._tree = ttk.Treeview(
            self,
            columns=[c[0] for c in columns],
            show='headings',
            selectmode='browse'
        )
        for col_id, col_label, col_width in columns:
            self._tree.heading(col_id, text=col_label,
                               command=lambda c=col_id: self._sort(c))
            self._tree.column(col_id, width=col_width)

        scrollbar = ttk.Scrollbar(self, orient='vertical', command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        self._tree.bind('<<TreeviewSelect>>', self._on_select)
        self._all_rows = []

    def load(self, rows: list[tuple]):
        self._all_rows = rows
        self._render(rows)

    def _render(self, rows):
        self._tree.delete(*self._tree.get_children())
        for row in rows:
            self._tree.insert('', 'end', values=row)

    def _filter(self):
        query = self._search_var.get().lower()
        if not query:
            self._render(self._all_rows)
        else:
            filtered = [r for r in self._all_rows
                        if any(query in str(v).lower() for v in r)]
            self._render(filtered)

    def _clear_search(self):
        self._search_var.set('')

    def _sort(self, col):
        col_idx = self._tree['columns'].index(col)
        rows = [(self._tree.set(item, col), item)
                for item in self._tree.get_children()]
        rows.sort()
        for i, (_, item) in enumerate(rows):
            self._tree.move(item, '', i)

    def _on_select(self, _event):
        selected = self._tree.selection()
        if selected and self.on_select:
            values = self._tree.item(selected[0])['values']
            self.on_select(values)

    def get_selected(self):
        selected = self._tree.selection()
        if selected:
            return self._tree.item(selected[0])['values']
        return None
```

## PyInstaller Build Script

```bash
#!/bin/bash
# build.sh
pyinstaller \
  --name "MyApp" \
  --onefile \
  --windowed \
  --icon "assets/icon.ico" \
  --add-data "assets:assets" \
  --hidden-import "PIL._tkinter_finder" \
  main.py

echo "Build complete: dist/MyApp.exe"
```

## Best Practices

1. **Always use `row_factory = sqlite3.Row`** — access columns by name, not index
2. **WAL mode** — `PRAGMA journal_mode=WAL` dramatically improves concurrent reads
3. **Foreign keys** — Enable with `PRAGMA foreign_keys=ON` every connection
4. **Thread-local connections** — Each thread gets its own SQLite connection
5. **Context managers for DB** — Auto-commit on success, auto-rollback on exception
6. **Ttk themed widgets** — Use `ttk.*` over `tk.*` for native look
7. **DPI scaling** — Always handle high-DPI displays or text will be tiny on 4K
8. **Background threads** — Use `threading.Thread(daemon=True)` for long operations; never block the UI thread
9. **Packaged data** — Use `Path(__file__).parent` for paths, not `os.getcwd()`
10. **Graceful shutdown** — Use `root.protocol("WM_DELETE_WINDOW", on_close)` to save state on close
