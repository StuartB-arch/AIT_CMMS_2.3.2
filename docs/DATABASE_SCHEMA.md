# AIT CMMS 2.3.2 — Database Schema

## Database Engine
- **Engine**: SQLite 3 (`ait_cmms.db`)
- **Legacy**: PostgreSQL (Neon cloud) — SQL ported via `sqlite_compat.py`
- **Location**: Same directory as `AIT_CMMS_REV3.py`

---

## Entity Relationship Summary

```
users ──────────────── user_sessions
  │                        │
  │              equipment ─┬──── pm_completions
  │                         ├──── weekly_pm_schedules
  │                         ├──── corrective_maintenance ── cm_parts_requests
  │                         ├──── work_orders
  │                         ├──── equipment_missing_parts
  │                         ├──── cannot_find_assets
  │                         ├──── run_to_failure_assets
  │                         ├──── deactivated_assets
  │                         ├──── pm_templates
  │                         └──── equipment_manuals
  │
  ├──── parts_inventory
  ├──── mro_stock
  ├──── mro_inventory
  └──── audit_log
```

---

## Table Definitions

### `users`
Authentication and user management.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| username | TEXT UNIQUE NOT NULL | Login name |
| password_hash | TEXT NOT NULL | SHA256 hex digest |
| full_name | TEXT | Display name |
| role | TEXT | Manager / Technician / Parts Coordinator |
| email | TEXT | Optional |
| is_active | INTEGER DEFAULT 1 | Boolean (0/1) |
| created_date | TIMESTAMP DEFAULT NOW | |
| updated_date | TIMESTAMP | |
| last_login | TIMESTAMP | Updated on each login |
| created_by | TEXT | Username of creator |
| notes | TEXT | Free-form notes |

**Default users created on init:**
- Admin (Manager role)
- apenson (Parts Coordinator role)

---

### `user_sessions`
Tracks active and historical login sessions.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| user_id | INTEGER FK → users.id | |
| username | TEXT | Denormalized for audit speed |
| login_time | TIMESTAMP | |
| last_activity | TIMESTAMP | Updated on actions |
| logout_time | TIMESTAMP | NULL if still active |
| is_active | INTEGER DEFAULT 1 | |

---

### `equipment`
Master equipment registry. Core table.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| sap_material_no | TEXT | SAP ERP number |
| bfm_equipment_no | TEXT UNIQUE NOT NULL | Primary business key |
| description | TEXT | Equipment description |
| tool_id_drawing_no | TEXT | Drawing/tool ID |
| location | TEXT | Physical location |
| master_lin | TEXT | Master line item number |
| monthly_pm | INTEGER | Boolean: requires monthly PM |
| six_month_pm | INTEGER | Boolean: requires 6-month PM |
| annual_pm | INTEGER | Boolean: requires annual PM |
| last_monthly_pm | DATE | Date of last monthly PM |
| last_six_month_pm | DATE | Date of last 6-month PM |
| last_annual_pm | DATE | Date of last annual PM |
| next_monthly_pm | DATE | Calculated next due date |
| next_six_month_pm | DATE | Calculated next due date |
| next_annual_pm | DATE | Calculated next due date |
| status | TEXT DEFAULT 'Active' | Active / Run to Failure / Missing / Deactivated |
| picture_1_data | BLOB | Binary image data |
| picture_2_data | BLOB | Binary image data |
| created_date | TIMESTAMP | |
| updated_date | TIMESTAMP | |

**Business Keys**: `bfm_equipment_no` is the primary cross-system identifier. `sap_material_no` links to ERP.

---

### `pm_completions`
Record of every completed preventive maintenance event.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| bfm_equipment_no | TEXT FK → equipment | |
| pm_type | TEXT | Monthly / Six Month / Annual |
| technician_name | TEXT | Who performed the PM |
| completion_date | DATE | When PM was done |
| location | TEXT | Where PM was done |
| labor_hours | INTEGER | Hours component |
| labor_minutes | INTEGER | Minutes component |
| pm_due_date | DATE | Original due date |
| special_equipment | TEXT | Any special tools used |
| notes | TEXT | Free-form notes |
| next_annual_pm_date | DATE | Calculated next annual due |
| document_name | TEXT | Reference document |
| document_revision | TEXT | Document revision level |
| created_date | TIMESTAMP | |

---

### `weekly_pm_schedules`
The working PM assignment table for the current/future weeks.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| bfm_equipment_no | TEXT FK → equipment | |
| pm_type | TEXT | Monthly / Six Month / Annual |
| assigned_technician | TEXT | Technician name |
| scheduled_date | DATE | Target date |
| week_start_date | DATE | Monday of the week |
| week_end_date | DATE | Friday of the week |
| status | TEXT DEFAULT 'Scheduled' | Scheduled / Completed / Cancelled |
| completion_date | DATE | Actual completion date |
| labor_hours | REAL | Actual hours |
| notes | TEXT | |
| created_date | TIMESTAMP | |

**Unique Index**: `(week_start_date, bfm_equipment_no, pm_type)` — prevents duplicate assignments.

---

### `corrective_maintenance`
Work orders for unplanned/reactive maintenance.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| cm_number | TEXT UNIQUE NOT NULL | Auto-generated (CM-YYYYMMDD-NNN) |
| bfm_equipment_no | TEXT FK → equipment | |
| description | TEXT | Problem description |
| location | TEXT | |
| reported_by | TEXT | |
| reported_date | DATE | |
| priority | TEXT | High / Medium / Low |
| status | TEXT DEFAULT 'Open' | Open / In Progress / Closed |
| assigned_technician | TEXT | |
| labor_hours | REAL | |
| notes | TEXT | |
| closed_date | DATE | NULL until closed |
| closed_by | TEXT | |
| created_date | TIMESTAMP | |
| updated_date | TIMESTAMP | |

---

### `cm_parts_requests`
Parts requested against a corrective maintenance work order.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| cm_number | TEXT FK → corrective_maintenance | CASCADE DELETE |
| bfm_equipment_no | TEXT | Denormalized |
| part_number | TEXT | |
| model_number | TEXT | |
| website | TEXT | Supplier URL |
| requested_by | TEXT | |
| requested_date | DATE | |
| notes | TEXT | |
| email_sent | INTEGER DEFAULT 0 | Boolean |
| email_sent_at | TIMESTAMP | |
| created_date | TIMESTAMP | |

---

### `equipment_missing_parts`
Equipment that cannot be serviced because parts are missing.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| emp_number | TEXT UNIQUE NOT NULL | Auto-generated (EMP-YYYYMMDD-NNN) |
| bfm_equipment_no | TEXT FK → equipment | |
| description | TEXT | |
| location | TEXT | |
| reported_by | TEXT | |
| reported_date | DATE | |
| priority | TEXT | High / Medium / Low |
| status | TEXT DEFAULT 'Open' | Open / Closed |
| assigned_technician | TEXT | |
| missing_parts_description | TEXT | What parts are missing |
| notes | TEXT | |
| closed_date | DATE | |
| closed_by | TEXT | |
| created_date | TIMESTAMP | |
| updated_date | TIMESTAMP | |

**Indexes**: status, assigned_technician, priority, reported_date

---

### `work_orders`
General-purpose work orders.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| wo_number | TEXT UNIQUE NOT NULL | Auto-generated |
| bfm_equipment_no | TEXT FK → equipment | |
| wo_type | TEXT | Type/category |
| description | TEXT | |
| location | TEXT | |
| requested_by | TEXT | |
| requested_date | DATE | |
| priority | TEXT | |
| status | TEXT DEFAULT 'Open' | Open / In Progress / Completed |
| assigned_technician | TEXT | |
| estimated_hours | REAL | |
| actual_hours | REAL | |
| completed_date | DATE | |
| notes | TEXT | |
| created_date | TIMESTAMP | |

---

### `parts_inventory`
Local spare parts stock.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| part_number | TEXT UNIQUE NOT NULL | |
| description | TEXT | |
| quantity | INTEGER DEFAULT 0 | |
| min_quantity | INTEGER DEFAULT 0 | Alert threshold |
| location | TEXT | Physical location |
| unit_cost | REAL | |
| last_ordered | DATE | |
| supplier | TEXT | |
| notes | TEXT | |
| created_date | TIMESTAMP | |
| updated_date | TIMESTAMP | |

---

### `mro_inventory`
Detailed MRO (Maintenance, Repair, Operations) inventory with images.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| name | TEXT NOT NULL | Item name |
| part_number | TEXT UNIQUE NOT NULL | |
| model_number | TEXT | |
| equipment | TEXT | Associated equipment |
| engineering_system | TEXT | System classification |
| unit_of_measure | TEXT | Each / Box / Gallon / etc. |
| quantity_in_stock | REAL DEFAULT 0 | |
| unit_price | REAL DEFAULT 0 | |
| minimum_stock | REAL DEFAULT 0 | Alert threshold |
| supplier | TEXT | |
| location | TEXT | |
| rack | TEXT | Storage rack |
| row | TEXT | Storage row |
| bin | TEXT | Storage bin |
| picture_1_path | TEXT | File path |
| picture_2_path | TEXT | File path |
| picture_1_data | BLOB | Binary image data |
| picture_2_data | BLOB | Binary image data |
| notes | TEXT | |
| last_updated | TIMESTAMP | |
| created_date | TIMESTAMP | |
| status | TEXT DEFAULT 'Active' | |

---

### `cannot_find_assets`
Equipment that cannot be physically located.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| bfm_equipment_no | TEXT UNIQUE FK → equipment | |
| description | TEXT | |
| location | TEXT | Expected location |
| last_known_location | TEXT | Last confirmed location |
| reported_by | TEXT | |
| reported_date | DATE | |
| technician_name | TEXT | Who last saw it |
| assigned_technician | TEXT | Who is searching |
| status | TEXT | Open / Found / Deactivated |
| search_status | TEXT | Active Search / Suspended |
| priority | TEXT | |
| found_date | DATE | |
| notes | TEXT | |
| created_date | TIMESTAMP | |
| updated_date | TIMESTAMP | |

---

### `run_to_failure_assets`
Equipment deliberately excluded from preventive maintenance.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| bfm_equipment_no | TEXT UNIQUE FK → equipment | |
| description | TEXT | |
| location | TEXT | |
| justification | TEXT | Why RTF is approved |
| approved_by | TEXT | Manager who approved |
| approval_date | DATE | |
| status | TEXT DEFAULT 'Active' | |
| created_date | TIMESTAMP | |
| updated_date | TIMESTAMP | |

---

### `deactivated_assets`
Equipment that has been retired/decommissioned.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| bfm_equipment_no | TEXT UNIQUE | |
| description | TEXT | |
| location | TEXT | |
| deactivated_by | TEXT | |
| deactivation_date | DATE | |
| reason | TEXT | Reason for deactivation |
| status | TEXT DEFAULT 'Deactivated' | |
| notes | TEXT | |
| created_date | TIMESTAMP | |
| updated_date | TIMESTAMP | |

---

### `audit_log`
Complete audit trail for compliance.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| user_name | TEXT | Who made the change |
| action | TEXT | INSERT / UPDATE / DELETE |
| table_name | TEXT | Which table was changed |
| record_id | TEXT | Which record |
| old_values | TEXT | JSON of previous state |
| new_values | TEXT | JSON of new state |
| notes | TEXT | Context notes |
| action_timestamp | TIMESTAMP DEFAULT NOW | |

---

### `pm_templates`
Reusable PM checklists per equipment type.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| bfm_equipment_no | TEXT FK → equipment | |
| template_name | TEXT | |
| checklist_json | TEXT | JSON array of checklist items |
| is_default | INTEGER DEFAULT 0 | Boolean |
| created_by | TEXT | |
| created_date | TIMESTAMP | |
| updated_date | TIMESTAMP | |

---

### `equipment_manuals`
Equipment technical documentation store.

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| title | TEXT NOT NULL | |
| description | TEXT | |
| category | TEXT | |
| sap_number | TEXT | SAP link |
| bfm_number | TEXT | Equipment link |
| equipment_name | TEXT | |
| file_name | TEXT | Original filename |
| file_extension | TEXT | pdf / docx / etc. |
| file_data | BLOB | Binary file content |
| file_size | INTEGER | Bytes |
| uploaded_by | TEXT | |
| upload_date | TIMESTAMP | |
| last_updated | TIMESTAMP | |
| tags | TEXT | Comma-separated tags |
| status | TEXT DEFAULT 'Active' | |
| notes | TEXT | |

---

## Key Design Decisions

1. **`bfm_equipment_no` as business key** — Not `id`. Cross-table joins use this human-readable key.
2. **Binary blobs in SQLite** — Photos and documents stored directly in DB (BLOB). Avoids file path management.
3. **Denormalized locations** — Location stored in multiple tables for query speed.
4. **Status enum pattern** — All status columns use TEXT with application-enforced enumerations.
5. **Auto-generated numbers** — CM/WO/EMP numbers follow pattern `PREFIX-YYYYMMDD-NNN` for readability.
6. **Soft deletes** — Equipment moved to `cannot_find_assets`, `run_to_failure_assets`, or `deactivated_assets` rather than deleted.
7. **PM dates on equipment** — `next_*_pm` dates denormalized onto `equipment` table for fast scheduling queries.
