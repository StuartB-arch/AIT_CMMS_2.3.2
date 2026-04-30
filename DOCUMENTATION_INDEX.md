# AIT CMMS 2.3.2 — Documentation Index

## About This Documentation Set

This documentation was reverse-engineered from the AIT CMMS 2.3.2 source code. It serves two purposes:

1. **Reference documentation** for the existing application (in `docs/`)
2. **Reusable skill templates** for building similar applications (`skills/`)

---

## Application Documentation (`docs/`)

| File | What It Covers |
|------|---------------|
| [docs/OVERVIEW.md](docs/OVERVIEW.md) | What the app is, key modules, data volumes, entry point |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System diagram, patterns, module dependency graph, data flows |
| [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) | All 18 tables with columns, types, indexes, and design decisions |
| [docs/MODULES_REFERENCE.md](docs/MODULES_REFERENCE.md) | Every Python module — class names, key methods, usage patterns |
| [docs/BUSINESS_LOGIC.md](docs/BUSINESS_LOGIC.md) | PM scheduling rules, state machines, work order numbering, audit logic |
| [docs/USER_ROLES.md](docs/USER_ROLES.md) | Manager / Technician / Parts Coordinator permissions, UI gating, session tracking |
| [docs/DEPLOYMENT_GUIDE.md](docs/DEPLOYMENT_GUIDE.md) | Install requirements, setup steps, network share, PyInstaller packaging, troubleshooting |

---

## Reusable Skill Templates (`skills/`)

These templates can be picked up and used for any new application. Each is self-contained with working code, patterns, and best practices.

| Skill File | Use When You Need To... |
|-----------|------------------------|
| [skills/SKILL_PYTHON_DESKTOP_APP.md](skills/SKILL_PYTHON_DESKTOP_APP.md) | Build any Python + Tkinter desktop app from scratch |
| [skills/SKILL_CMMS_SYSTEM.md](skills/SKILL_CMMS_SYSTEM.md) | Build a CMMS / asset management / maintenance system |
| [skills/SKILL_DATABASE_LAYER.md](skills/SKILL_DATABASE_LAYER.md) | Set up SQLite with connection pooling, migrations, repository pattern |
| [skills/SKILL_PM_SCHEDULING.md](skills/SKILL_PM_SCHEDULING.md) | Implement PM scheduling with priority queues and technician assignment |
| [skills/SKILL_RBAC_AUTH.md](skills/SKILL_RBAC_AUTH.md) | Add user login, roles, and permission-gated features |
| [skills/SKILL_INVENTORY_MGMT.md](skills/SKILL_INVENTORY_MGMT.md) | Build an inventory module with stock levels, alerts, transactions |
| [skills/SKILL_PDF_REPORTS.md](skills/SKILL_PDF_REPORTS.md) | Generate professional PDF forms and reports with ReportLab |
| [skills/SKILL_AUDIT_TRAIL.md](skills/SKILL_AUDIT_TRAIL.md) | Add a full audit log with before/after values and compliance queries |
| [skills/SKILL_CSV_SYNC.md](skills/SKILL_CSV_SYNC.md) | Sync data between CSV files and a database (import/export/live sync) |
| [skills/SKILL_MULTI_USER.md](skills/SKILL_MULTI_USER.md) | Handle concurrent users with session tracking and optimistic locking |

---

## Quick Reference: Application Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3 |
| GUI | Tkinter + ttk |
| Database | SQLite (via `sqlite3` built-in) |
| ORM | None — raw SQL with `sqlite3.Row` |
| PDF | ReportLab |
| Excel/CSV | pandas |
| Images | Pillow (PIL) |
| Word docs | python-docx |
| Auth | SHA256 password hashing |
| Packaging | PyInstaller (optional) |

---

## Quick Reference: Database Tables

| Table | Purpose |
|-------|---------|
| `users` | User accounts |
| `user_sessions` | Login session tracking |
| `equipment` | Asset registry (core table) |
| `pm_completions` | PM completion records |
| `weekly_pm_schedules` | Current week's PM assignments |
| `pm_templates` | Reusable PM checklists |
| `corrective_maintenance` | Reactive maintenance work orders |
| `cm_parts_requests` | Parts requested for CM work orders |
| `work_orders` | General work orders |
| `equipment_missing_parts` | Equipment awaiting parts |
| `parts_inventory` | Local spare parts stock |
| `mro_inventory` | MRO stock with images |
| `cannot_find_assets` | Missing/unlocatable equipment |
| `run_to_failure_assets` | Equipment excluded from PM |
| `deactivated_assets` | Retired equipment |
| `equipment_manuals` | Technical document storage |
| `audit_log` | Change audit trail |

---

## How to Use the Skills for a New Application

### Starting a Similar App from Scratch

1. **Start with** `SKILL_PYTHON_DESKTOP_APP.md` — copy the project structure and entry point
2. **Set up the database** using `SKILL_DATABASE_LAYER.md` — connection pool, schema migrations
3. **Add authentication** using `SKILL_RBAC_AUTH.md` — login dialog, password hashing, permissions
4. **Add audit logging** using `SKILL_AUDIT_TRAIL.md` — wire up after every save/delete
5. **Build the core domain** using the domain-specific skills (PM, Inventory, etc.)
6. **Add PDF generation** using `SKILL_PDF_REPORTS.md` for any form outputs
7. **Add CSV import/export** using `SKILL_CSV_SYNC.md` for data exchange

### Building Something Better

To upgrade this application to a production-grade web app:

| Current | Upgrade To |
|---------|-----------|
| Tkinter | React or Vue.js frontend |
| SQLite | PostgreSQL (scale to 1000s of users) |
| SHA256 passwords | bcrypt + JWT tokens |
| Manual backup | Automated cloud backup (S3) |
| ReportLab | Jinja2 templates + WeasyPrint |
| CSV sync | REST API + webhooks for ERP integration |
| No CI/CD | GitHub Actions with pytest |
| No Docker | Docker Compose for dev, Kubernetes for prod |

---

## Application File Map

```
AIT_CMMS_2.3.2/
├── DOCUMENTATION_INDEX.md         ← You are here
├── docs/
│   ├── OVERVIEW.md
│   ├── ARCHITECTURE.md
│   ├── DATABASE_SCHEMA.md
│   ├── MODULES_REFERENCE.md
│   ├── BUSINESS_LOGIC.md
│   ├── USER_ROLES.md
│   └── DEPLOYMENT_GUIDE.md
├── skills/
│   ├── SKILL_PYTHON_DESKTOP_APP.md
│   ├── SKILL_CMMS_SYSTEM.md
│   ├── SKILL_DATABASE_LAYER.md
│   ├── SKILL_PM_SCHEDULING.md
│   ├── SKILL_RBAC_AUTH.md
│   ├── SKILL_INVENTORY_MGMT.md
│   ├── SKILL_PDF_REPORTS.md
│   ├── SKILL_AUDIT_TRAIL.md
│   ├── SKILL_CSV_SYNC.md
│   └── SKILL_MULTI_USER.md
├── AIT_CMMS_REV3.py               ← Main application
├── pm_scheduler.py
├── mro_stock_module.py
├── [... other modules ...]
└── ait_cmms.db                    ← SQLite database (created on first run)
```
