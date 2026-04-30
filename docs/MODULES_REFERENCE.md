# AIT CMMS 2.3.2 — Modules Reference

## Module Map

| Module | Lines | Responsibility |
|--------|-------|---------------|
| `AIT_CMMS_REV3.py` | 24,153 | Main app, UI, orchestration |
| `pm_scheduler.py` | ~1,300 | PM scheduling engine |
| `mro_stock_module.py` | ~3,200 | MRO inventory UI + CRUD |
| `manuals_module.py` | ~1,200 | Document management |
| `equipment_history.py` | ~850 | Audit trail queries |
| `equipment_manager.py` | ~500 | Equipment CRUD |
| `cm_parts_integration.py` | ~730 | CM parts tracking |
| `backup_manager.py` | ~920 | Backup/restore logic |
| `backup_ui.py` | ~780 | Backup UI dialogs |
| `csv_manager.py` | ~1,100 | CSV sync engine |
| `sqlite_compat.py` | ~430 | SQL dialect converter |
| `database_utils.py` | ~270 | DB pool + transactions |
| `user_management_ui.py` | ~580 | User CRUD UI |
| `password_change_ui.py` | ~240 | Password change dialog |
| `skydrol_pm_task.py` | ~780 | Hydraulic PM workflow |
| `migrate_multiuser.py` | ~360 | DB migration script |

---

## Core Infrastructure Modules

### `database_utils.py`

**Purpose**: Database connection pooling, transaction management, optimistic concurrency.

**Key Classes:**
```python
class DatabaseConnectionPool:
    # Singleton. Call get_instance() everywhere.
    def get_cursor(self) -> ContextManager[sqlite3.Cursor]
    def get_connection(self) -> sqlite3.Connection

class TransactionManager:
    # Context manager for explicit transactions
    def __enter__(self) -> sqlite3.Cursor
    def __exit__(self, exc_type, ...) -> None  # auto commit/rollback

class OptimisticConcurrencyControl:
    # version-column based conflict detection
    def update_with_version(table, id, data, expected_version) -> bool
```

**Usage Pattern:**
```python
db_pool = DatabaseConnectionPool.get_instance()
with db_pool.get_cursor() as cursor:
    cursor.execute("SELECT * FROM equipment WHERE bfm_equipment_no = ?", (bfm_no,))
    row = cursor.fetchone()
```

---

### `sqlite_compat.py`

**Purpose**: Allow PostgreSQL-flavored SQL to run on SQLite without rewriting queries.

**Key Class:**
```python
class SQLiteCompat:
    @staticmethod
    def convert_sql(sql: str) -> str
        # Replaces PG-specific syntax with SQLite equivalents
```

**Conversions handled:**
- Type definitions: `SERIAL`, `BOOLEAN`, `BYTEA`, `TIMESTAMP WITH TIME ZONE`
- Operators: `ILIKE`, `::cast`, `@>` (jsonb contains)
- Functions: `EXTRACT(epoch...)`, `GREATEST()`, `COALESCE()`
- Intervals: `NOW() - INTERVAL '30 days'`
- Conflict clauses: `ON CONFLICT DO NOTHING` → `INSERT OR IGNORE`
- Returning: `RETURNING id` → stripped (use `lastrowid`)

---

## Business Logic Modules

### `pm_scheduler.py`

**Purpose**: Determine which equipment needs PM, prioritize it, and assign it to technicians.

**Key Classes:**
```python
class PMType(Enum):
    MONTHLY = "Monthly"
    SIX_MONTH = "Six Month"
    ANNUAL = "Annual"

class PMStatus(Enum):
    DUE = "due"
    NOT_DUE = "not_due"
    RECENTLY_COMPLETED = "recently_completed"
    CONFLICTED = "conflicted"

@dataclass
class Equipment:
    bfm_equipment_no: str
    description: str
    location: str
    sap_material_no: str
    # ... PM dates, status flags

class PMEligibilityChecker:
    def check_eligibility(self, equipment: Equipment, pm_type: PMType) -> PMStatus
    def is_overdue(self, equipment: Equipment, pm_type: PMType) -> bool
    def days_until_due(self, equipment: Equipment, pm_type: PMType) -> int

class PMAssignmentGenerator:
    def generate_assignments(
        self,
        eligible_equipment: list[Equipment],
        technicians: list[str],
        week_start: date
    ) -> list[PMAssignment]
    # Priority: P1 (overdue) → P2 (due) → P3 (due soon) → P4 (scheduled)
    # SAP grouping: same SAP → same technician
    # Round-robin balancing: no technician gets too many

class PMSchedulingService:
    def generate_weekly_schedule(self, week_start: date) -> list[PMAssignment]
    def get_technician_workload(self, week_start: date) -> dict[str, int]
```

---

### `csv_manager.py`

**Purpose**: Two-way synchronization between `PM_MASTER_2026_CLEANED.csv` and the `equipment` table.

**Key Class:**
```python
class CSVManager:
    CSV_FILENAME = "PM_MASTER_2026_CLEANED.csv"

    def startup_sync(self) -> SyncResult:
        # Read CSV, upsert into equipment table
        # Preserves manually-edited DB fields

    def shutdown_export(self) -> None:
        # Write current PM dates from DB back to CSV

    def update_equipment_pm_dates(self, bfm_no: str, pm_type: str, completion_date: date) -> None:
        # Called after each PM completion — update CSV immediately

    def import_new_equipment(self, csv_row: dict) -> None:
        # Add new equipment from CSV to database
```

**CSV Column Mapping:**
```python
COLUMN_MAP = {
    'BFM Equipment No': 'bfm_equipment_no',
    'SAP Material No': 'sap_material_no',
    'Description': 'description',
    'Location': 'location',
    'Monthly PM': 'monthly_pm',
    'Six Month PM': 'six_month_pm',
    'Annual PM': 'annual_pm',
    'Last Monthly PM': 'last_monthly_pm',
    # ... etc.
}
```

---

### `equipment_manager.py`

**Purpose**: CRUD operations for equipment records.

**Key Class:**
```python
class EquipmentManager:
    def get_equipment(self, bfm_no: str) -> Equipment | None
    def search_equipment(self, query: str) -> list[Equipment]
    def create_equipment(self, data: dict) -> Equipment
    def update_equipment(self, bfm_no: str, data: dict) -> bool
    def update_equipment_photo(self, bfm_no: str, photo_num: int, image_data: bytes) -> bool
    def get_equipment_status(self, bfm_no: str) -> str
    def mark_cannot_find(self, bfm_no: str, reporter: str, notes: str) -> bool
    def mark_run_to_failure(self, bfm_no: str, justification: str, approver: str) -> bool
    def deactivate_equipment(self, bfm_no: str, reason: str) -> bool
```

---

### `equipment_history.py`

**Purpose**: Query the audit log for equipment-specific history and display it.

**Key Class:**
```python
class EquipmentHistory:
    def get_pm_history(self, bfm_no: str) -> list[PMCompletion]
    def get_cm_history(self, bfm_no: str) -> list[CMRecord]
    def get_status_changes(self, bfm_no: str) -> list[AuditEntry]
    def get_full_history(self, bfm_no: str) -> list[HistoryEntry]
    def export_history_pdf(self, bfm_no: str) -> bytes
```

---

### `mro_stock_module.py`

**Purpose**: Full UI and business logic for MRO inventory management.

**Key Class:**
```python
class MROStockManager:
    def search_inventory(self, query: str) -> list[MROItem]
    def get_item(self, part_number: str) -> MROItem | None
    def create_item(self, data: dict) -> MROItem
    def update_item(self, part_number: str, data: dict) -> bool
    def adjust_quantity(self, part_number: str, delta: int, reason: str) -> bool
    def get_low_stock_items(self) -> list[MROItem]
    def export_inventory_csv(self) -> str  # CSV string
    def import_inventory_csv(self, filepath: str) -> ImportResult
    def upload_item_photo(self, part_number: str, photo_num: int, image_data: bytes) -> bool
```

---

### `manuals_module.py`

**Purpose**: Equipment manual storage, retrieval, and search.

**Key Class:**
```python
class ManualsManager:
    def search_manuals(self, query: str) -> list[Manual]
    def get_manual(self, manual_id: int) -> Manual | None
    def upload_manual(self, file_path: str, metadata: dict) -> Manual
    def download_manual(self, manual_id: int) -> tuple[bytes, str]  # (data, filename)
    def delete_manual(self, manual_id: int) -> bool
    def get_manuals_for_equipment(self, bfm_no: str) -> list[Manual]
```

---

### `backup_manager.py`

**Purpose**: Database backup creation, scheduling, and restore.

**Key Class:**
```python
class BackupManager:
    def create_backup(self, reason: str = "manual") -> BackupResult
    def list_backups(self) -> list[BackupInfo]
    def restore_backup(self, backup_path: str) -> RestoreResult
    def verify_backup(self, backup_path: str) -> bool
    def schedule_auto_backup(self, interval_hours: int) -> None
    def get_backup_status(self) -> BackupStatus
```

---

### `skydrol_pm_task.py`

**Purpose**: Weekly Skydrol (hydraulic fluid) inspection workflow for hydraulic units.

**Key Class:**
```python
class SkydrolPMTaskManager:
    COMBINED_UNIT = "HYD-UNITS-ALL"
    LEGACY_UNITS = ["HYD-UNIT-001", "HYD-UNIT-002", "HYD-UNIT-003"]

    def create_weekly_skydrol_task(self, week_start: date, technician: str) -> WeeklyTask
    def complete_skydrol_task(self, task_id: int, completion_data: dict) -> bool
    def generate_skydrol_pdf(self, task_id: int) -> bytes
    def get_skydrol_history(self, weeks: int = 52) -> list[SkydrolRecord]
```

---

## UI Modules

### `user_management_ui.py`

**Purpose**: Manager-only dialog for creating/editing/deactivating users.

```python
class UserManagementDialog(tk.Toplevel):
    # Launched from main app as modal dialog
    # Lists all users with role/status
    # Create user form
    # Edit user form
    # Deactivate (soft delete) user
    # Reset password
```

### `password_change_ui.py`

**Purpose**: Dialog for any user to change their own password.

```python
class PasswordChangeDialog(tk.Toplevel):
    # Verify current password
    # Enter + confirm new password
    # Enforce minimum complexity
    # Update password_hash in users table
```

### `backup_ui.py`

**Purpose**: UI wrapper around `BackupManager`.

```python
class BackupUI(tk.Toplevel):
    # Manual backup button
    # Backup history list
    # Restore from backup
    # Auto-backup schedule settings
    # Backup verification status
```

---

## Utility/Migration Scripts

| Script | Purpose |
|--------|---------|
| `migrate_multiuser.py` | One-time migration adding multi-user tables to existing single-user DB |
| `analyze_duplicate_assets.py` | Detect duplicate `bfm_equipment_no` values |
| `diagnose_assets.py` | Diagnostic tool for data integrity issues |
| `cleanup_whitespace.py` | Code cleanup utility (strip trailing whitespace) |
| `debug_startup.py` | Debug startup sequence without full UI |
