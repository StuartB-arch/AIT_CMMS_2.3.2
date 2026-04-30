# AIT CMMS 2.3.2 — Application Overview

## What Is This Application?

AIT CMMS 2.3.2 is a **Computerized Maintenance Management System (CMMS)** built as a Python/Tkinter desktop application. It manages preventive and corrective maintenance scheduling, equipment tracking, MRO inventory, and compliance documentation for industrial/aviation maintenance operations (specifically tuned for A220 aircraft ground support equipment).

---

## Core Purpose

| Goal | How It's Achieved |
|------|-------------------|
| Track all maintainable equipment | Equipment registry with SAP/BFM numbers, photos, locations |
| Schedule preventive maintenance | Automatic PM generation with P1–P4 priority assignment |
| Assign work to technicians | Workload-balanced weekly PM schedule with capacity management |
| Record completed maintenance | PM completion forms generating signed PDF documents |
| Manage spare parts | MRO stock module with min/max levels, images, supplier data |
| Audit everything | Full audit log on all create/update/delete operations |
| Support multiple users | Role-based access with session tracking |
| Store equipment documentation | Manual/technical document upload and search |

---

## Application Type

- **Type**: Desktop GUI application
- **Language**: Python 3
- **GUI Framework**: Tkinter (tkinter.ttk for themed widgets)
- **Database**: SQLite (local), with legacy PostgreSQL (Neon cloud) compatibility layer
- **Platform**: Windows primary, Linux/macOS compatible
- **Deployment**: Single-machine or shared-network SQLite file

---

## User Roles

| Role | Access Level |
|------|-------------|
| **Manager** | Full access — user management, backups, all reports, all modules |
| **Technician** | PM completion, equipment lookup, schedule view |
| **Parts Coordinator** | MRO stock management, parts ordering, inventory reports |

---

## Key Modules

| File | Purpose | Size |
|------|---------|------|
| `AIT_CMMS_REV3.py` | Main application — UI, integration, startup | 24,153 lines |
| `pm_scheduler.py` | PM scheduling engine and priority algorithm | 40 KB |
| `mro_stock_module.py` | MRO inventory management UI + logic | 101 KB |
| `manuals_module.py` | Equipment manuals upload/search | 39 KB |
| `equipment_history.py` | Audit trail queries for equipment | 27 KB |
| `cm_parts_integration.py` | Parts tracking for corrective maintenance | 23 KB |
| `backup_manager.py` | Database backup and restore | 29 KB |
| `csv_manager.py` | Two-way CSV sync with master equipment list | 35 KB |
| `sqlite_compat.py` | PostgreSQL→SQLite SQL compatibility converter | 13 KB |
| `database_utils.py` | Connection pooling, transactions, concurrency | 8 KB |
| `skydrol_pm_task.py` | Hydraulic unit (Skydrol) weekly PM workflow | 24 KB |
| `user_management_ui.py` | User CRUD dialog (Manager only) | 18 KB |

---

## Data Volume Expectations

- Equipment records: ~2,000+ items (based on PM_MASTER_2026_CLEANED.csv)
- PM completions: Hundreds per month
- MRO inventory: Hundreds to thousands of parts
- Weekly PM target: ~130 PMs per week
- Users: Small team (5–20)

---

## Entry Point

```python
# AIT_CMMS_REV3.py, line 24151
if __name__ == "__main__":
    root = tk.Tk()
    app = AITCMMSSystem(root)
    root.mainloop()
```

---

## Application Lifecycle

1. **Startup**: Clear `__pycache__`, set DPI scaling, initialize database
2. **Login**: Authenticate user, create session record, load role permissions
3. **CSV Sync**: Background sync of `PM_MASTER_2026_CLEANED.csv` → database
4. **Main Loop**: Tkinter event loop with tabbed interface
5. **Shutdown**: Export updated PM dates back to CSV, close session

---

## Design Philosophy

- **Self-contained**: Single SQLite file, no server required
- **Offline-first**: Works without internet after initial setup
- **Audit-ready**: Every data change logged to `audit_log` table
- **CSV-backed**: Master equipment list survives database rebuilds
- **Role-gated**: UI elements hidden/disabled based on role
- **Modular**: Each major feature in its own Python module
