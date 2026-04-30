# AIT CMMS 2.3.2 — System Architecture

## High-Level Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Tkinter GUI Layer                   │
│  AITCMMSSystem (main window + tab controller)       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────┐  │
│  │Equipment │ │  PM Sched│ │MRO Stock │ │Manuals│  │
│  │  Tab     │ │  Tab     │ │  Tab     │ │  Tab  │  │
│  └──────────┘ └──────────┘ └──────────┘ └───────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │  Users   │ │ Backups  │ │ Reports  │            │
│  │  Tab     │ │  Tab     │ │  Tab     │            │
│  └──────────┘ └──────────┘ └──────────┘            │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│                  Service Layer                       │
│  UserManager    PMSchedulingService  CSVManager     │
│  AuditLogger    EquipmentManager     BackupManager  │
│  MROStockMgr    ManualsManager       CMPartsInteg   │
│  EquipmentHistory                 SkydrolPMTask     │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│               Database Abstraction Layer             │
│  DatabaseConnectionPool (singleton)                 │
│  TransactionManager (context manager)               │
│  sqlite_compat (SQL dialect converter)              │
│  OptimisticConcurrencyControl (version columns)     │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│                    SQLite Database                   │
│              ait_cmms.db (local file)               │
│  18 tables, indexes, triggers, audit_log            │
└─────────────────────────────────────────────────────┘
```

---

## Architectural Patterns

### 1. Monolith with Modular Files

The application is organized as a monolith — a single Python process — but split across ~15 `.py` files. The main file (`AIT_CMMS_REV3.py`) imports and orchestrates all modules. Each module encapsulates one domain area.

**Why**: Desktop app simplicity. No microservices overhead. Works offline.

### 2. Singleton Database Pool

```python
# database_utils.py
class DatabaseConnectionPool:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
```

All modules share one database connection pool instance via `db_pool = DatabaseConnectionPool.get_instance()`.

### 3. Context Manager for Transactions

```python
with db_pool.get_cursor() as cursor:
    cursor.execute("SELECT ...")
    results = cursor.fetchall()
# Connection auto-committed or rolled back on exception
```

### 4. SQL Compatibility Layer

`sqlite_compat.py` intercepts all SQL before it reaches SQLite and converts PostgreSQL-specific syntax:

| PostgreSQL | SQLite |
|-----------|--------|
| `SERIAL` | `INTEGER` |
| `BOOLEAN` | `INTEGER` |
| `BYTEA` | `BLOB` |
| `INTERVAL '30 days'` | `julianday calculations` |
| `EXTRACT(epoch...)` | `strftime(...)` |
| `ILIKE` | `LOWER(...) LIKE LOWER(...)` |
| `ON CONFLICT DO NOTHING` | `INSERT OR IGNORE` |

### 5. Optimistic Concurrency Control

For multi-user scenarios where two users might edit the same record:

```python
# version column on every table
UPDATE equipment SET description=?, version=version+1
WHERE bfm_equipment_no=? AND version=?
-- If 0 rows updated → conflict detected
```

### 6. Role-Based UI Gating

UI elements are enabled/disabled at render time based on `self.current_user_role`:

```python
if self.current_user_role == 'Manager':
    user_mgmt_btn.config(state='normal')
else:
    user_mgmt_btn.config(state='disabled')
```

### 7. Background Threading for CSV Sync

```python
# Non-blocking CSV sync at startup
threading.Thread(
    target=self.csv_manager.startup_sync,
    daemon=True
).start()
```

### 8. PDF Generation Pipeline

```
PM Completion Form Data
        │
        ▼
  ReportLab Canvas
        │
        ▼
  BytesIO buffer
        │
        ▼
  Save to disk / open in viewer
```

---

## Data Flow: PM Scheduling

```
PM_MASTER_2026_CLEANED.csv
        │ (startup_sync)
        ▼
equipment table (SQLite)
        │
        ▼
PMEligibilityChecker
  - Is it due? (last PM date + frequency < today)
  - Is it in run_to_failure?
  - Is it deactivated?
        │
        ▼
PMAssignmentGenerator
  - Priority scoring (P1=high, P4=low)
  - Round-robin across technician list
  - SAP grouping (same SAP number → same tech)
  - Capacity capping (max PMs per technician)
        │
        ▼
weekly_pm_schedules table
        │
        ▼
PM Schedule Tab (UI display)
        │
        ▼ (technician completes PM)
pm_completions table
        │
        ▼
CSV updated with new next PM date
```

---

## Data Flow: User Authentication

```
Login Dialog
  username + password (plaintext)
        │
        ▼
UserManager.verify_login()
  - Fetch password_hash FROM users WHERE username=?
  - hashlib.sha256(password).hexdigest() == stored_hash
        │
        ▼
Session Created
  INSERT INTO user_sessions (user_id, login_time, is_active)
        │
        ▼
Role Loaded
  self.current_user_role = row['role']
        │
        ▼
UI Rendered with role-gated elements
```

---

## Module Dependency Graph

```
AIT_CMMS_REV3.py (orchestrator)
├── database_utils.py
│   └── sqlite_compat.py
├── pm_scheduler.py
│   └── database_utils.py
├── mro_stock_module.py
│   └── database_utils.py
├── manuals_module.py
│   └── database_utils.py
├── equipment_history.py
│   └── database_utils.py
├── equipment_manager.py
│   └── database_utils.py
├── cm_parts_integration.py
│   └── database_utils.py
├── backup_manager.py
│   └── database_utils.py
├── backup_ui.py
│   └── backup_manager.py
├── csv_manager.py
│   └── database_utils.py
├── user_management_ui.py
│   └── database_utils.py
├── password_change_ui.py
│   └── database_utils.py
└── skydrol_pm_task.py
    └── database_utils.py
```

---

## Scaling Considerations

| Concern | Current Approach | Better Approach for Scale |
|---------|-----------------|--------------------------|
| Database | SQLite single file | PostgreSQL with connection pool |
| Concurrency | Optimistic locking | PostgreSQL row-level locking |
| UI | Tkinter (single thread) | Web app (React + FastAPI) |
| Deployment | Manual file copy | Docker + installer |
| Auth | SHA256 passwords | bcrypt + JWT |
| Backups | Manual + scheduled | Automated cloud backup |
| Reports | ReportLab | Jinja2 templates + WeasyPrint |
