# Skill: Building a CMMS (Computerized Maintenance Management System)

## What Is a CMMS?

A CMMS manages the maintenance of physical assets (equipment, vehicles, buildings, machinery). Core functions:
- Track all assets and their maintenance schedules
- Generate and assign preventive maintenance work orders
- Record completed maintenance with labor time and notes
- Track corrective (reactive) maintenance
- Manage spare parts inventory
- Produce compliance reports

## Core Domain Model

```
Equipment (asset registry)
  └── has PM schedule (monthly / quarterly / annual)
  └── has maintenance history (completed PMs)
  └── has work orders (CM, repairs)
  └── has spare parts usage
  └── has status (Active / RTF / Missing / Deactivated)

User (technician / manager)
  └── assigned to work orders
  └── records PM completions
  └── manages inventory

WorkOrder
  └── linked to Equipment
  └── has type: PM (preventive) or CM (corrective)
  └── has status: Open / In Progress / Completed
  └── has labor time, notes, parts used

Inventory (spare parts)
  └── has min/max stock levels
  └── linked to work orders (parts consumption)
  └── triggers alerts when below minimum
```

## Essential Database Tables

```sql
-- Asset registry
CREATE TABLE equipment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id TEXT UNIQUE NOT NULL,       -- Human-readable ID (e.g., EQ-001)
    name TEXT NOT NULL,
    description TEXT,
    category TEXT,
    location TEXT,
    manufacturer TEXT,
    model TEXT,
    serial_number TEXT,
    install_date DATE,
    status TEXT DEFAULT 'Active',        -- Active/RTF/Missing/Deactivated
    -- PM configuration
    pm_monthly INTEGER DEFAULT 0,        -- Boolean flag
    pm_quarterly INTEGER DEFAULT 0,
    pm_annual INTEGER DEFAULT 0,
    -- PM dates (denormalized for fast scheduling queries)
    last_pm_monthly DATE,
    last_pm_quarterly DATE,
    last_pm_annual DATE,
    next_pm_monthly DATE,
    next_pm_quarterly DATE,
    next_pm_annual DATE,
    -- Photos
    photo_1 BLOB,
    photo_2 BLOB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

-- PM completion records
CREATE TABLE pm_completions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id TEXT REFERENCES equipment(asset_id),
    pm_type TEXT NOT NULL,               -- Monthly/Quarterly/Annual
    completed_by TEXT,
    completed_date DATE,
    labor_hours REAL,
    notes TEXT,
    checklist_json TEXT,                 -- JSON array of completed checklist items
    pdf_generated INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Work orders (both PM and CM)
CREATE TABLE work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wo_number TEXT UNIQUE NOT NULL,      -- WO-20260430-001
    asset_id TEXT REFERENCES equipment(asset_id),
    wo_type TEXT,                        -- PM / CM / Inspection / Repair
    title TEXT NOT NULL,
    description TEXT,
    priority TEXT DEFAULT 'Medium',      -- Critical/High/Medium/Low
    status TEXT DEFAULT 'Open',          -- Open/In Progress/On Hold/Completed/Cancelled
    requested_by TEXT,
    assigned_to TEXT,
    estimated_hours REAL,
    actual_hours REAL,
    requested_date DATE,
    due_date DATE,
    completed_date DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

-- Spare parts inventory
CREATE TABLE parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_number TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT,
    unit_of_measure TEXT,
    quantity_on_hand REAL DEFAULT 0,
    minimum_quantity REAL DEFAULT 0,
    reorder_quantity REAL,
    unit_cost REAL,
    supplier TEXT,
    supplier_part_number TEXT,
    location TEXT,
    bin_number TEXT,
    last_ordered DATE,
    notes TEXT,
    status TEXT DEFAULT 'Active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Parts usage against work orders
CREATE TABLE work_order_parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wo_number TEXT REFERENCES work_orders(wo_number),
    part_number TEXT REFERENCES parts(part_number),
    quantity_used REAL,
    unit_cost REAL,
    notes TEXT,
    recorded_by TEXT,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Scheduled maintenance (the weekly schedule board)
CREATE TABLE scheduled_maintenance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id TEXT REFERENCES equipment(asset_id),
    pm_type TEXT,
    assigned_to TEXT,
    scheduled_date DATE,
    week_start DATE,
    status TEXT DEFAULT 'Scheduled',
    completed_date DATE,
    actual_hours REAL,
    notes TEXT,
    UNIQUE(week_start, asset_id, pm_type)
);
```

## PM Scheduling Algorithm

```python
from datetime import date, timedelta
from dataclasses import dataclass
from enum import Enum

class Priority(Enum):
    P1 = 1  # Overdue
    P2 = 2  # Due this week
    P3 = 3  # Due within 2 weeks
    P4 = 4  # Eligible filler

PM_FREQUENCIES = {
    'Monthly': 30,
    'Quarterly': 90,
    'Annual': 365,
}

@dataclass
class PMWork:
    asset_id: str
    pm_type: str
    priority: Priority
    days_overdue: int
    location: str
    category: str

def get_pm_priority(last_pm_date: date | None, pm_type: str, today: date) -> Priority | None:
    freq = PM_FREQUENCIES[pm_type]
    if last_pm_date is None:
        return Priority.P1  # Never done = overdue

    days_since = (today - last_pm_date).days
    days_until_due = freq - days_since

    if days_until_due < 0:
        return Priority.P1   # Overdue
    elif days_until_due <= 7:
        return Priority.P2   # Due this week
    elif days_until_due <= 14:
        return Priority.P3   # Due soon
    elif days_until_due <= 30:
        return Priority.P4   # Fill schedule
    else:
        return None           # Not yet needed

def generate_weekly_schedule(
    equipment_list: list,
    technicians: list[str],
    week_start: date,
    target_per_week: int = 100
) -> list[dict]:
    today = week_start
    assignments = []

    # Collect all eligible work
    eligible = []
    for equip in equipment_list:
        if equip['status'] != 'Active':
            continue
        for pm_type in ['Monthly', 'Quarterly', 'Annual']:
            if not equip.get(f'pm_{pm_type.lower()}'):
                continue
            last_pm = equip.get(f'last_pm_{pm_type.lower()}')
            priority = get_pm_priority(last_pm, pm_type, today)
            if priority:
                eligible.append(PMWork(
                    asset_id=equip['asset_id'],
                    pm_type=pm_type,
                    priority=priority,
                    days_overdue=max(0, (today - (last_pm or date.min)).days - PM_FREQUENCIES[pm_type]),
                    location=equip['location'],
                    category=equip['category'],
                ))

    # Sort by priority (P1 first, then by days overdue)
    eligible.sort(key=lambda x: (x.priority.value, -x.days_overdue))

    # Round-robin assign to technicians
    tech_counts = {t: 0 for t in technicians}
    max_per_tech = target_per_week // len(technicians) if technicians else 0

    for work in eligible[:target_per_week]:
        # Pick least-loaded technician under capacity
        available = [t for t in technicians if tech_counts[t] < max_per_tech]
        if not available:
            break
        tech = min(available, key=lambda t: tech_counts[t])

        assignments.append({
            'asset_id': work.asset_id,
            'pm_type': work.pm_type,
            'assigned_to': tech,
            'priority': work.priority.name,
            'week_start': week_start.isoformat(),
            'status': 'Scheduled',
        })
        tech_counts[tech] += 1

    return assignments
```

## Work Order Number Generation

```python
def generate_wo_number(prefix: str, db) -> str:
    today = date.today().strftime('%Y%m%d')
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM work_orders WHERE wo_number LIKE ?",
            (f"{prefix}-{today}-%",)
        )
        count = cursor.fetchone()[0]
    return f"{prefix}-{today}-{count + 1:03d}"

# Usage:
wo_number = generate_wo_number("WO", db)   # WO-20260430-001
cm_number = generate_wo_number("CM", db)   # CM-20260430-001
```

## Equipment Status State Machine

```python
VALID_TRANSITIONS = {
    'Active': ['Run to Failure', 'Missing', 'Deactivated'],
    'Missing': ['Active', 'Deactivated'],
    'Run to Failure': ['Active', 'Deactivated'],
    'Deactivated': [],  # Terminal state
}

def transition_equipment_status(asset_id: str, new_status: str, db, user: str) -> bool:
    with db.get_cursor() as cursor:
        cursor.execute("SELECT status FROM equipment WHERE asset_id = ?", (asset_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Equipment {asset_id} not found")

        current = row['status']
        if new_status not in VALID_TRANSITIONS[current]:
            raise ValueError(f"Cannot transition from {current} to {new_status}")

        cursor.execute(
            "UPDATE equipment SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE asset_id = ?",
            (new_status, asset_id)
        )
    log_audit(user, 'UPDATE', 'equipment', asset_id, {'status': current}, {'status': new_status})
    return True
```

## Minimum Viable Feature Set

**Phase 1 — Core (must have):**
- [ ] Equipment registry (CRUD + photos)
- [ ] PM schedule generation (monthly/quarterly/annual)
- [ ] PM completion recording
- [ ] Basic work order management
- [ ] User login with roles

**Phase 2 — Operations (should have):**
- [ ] Weekly schedule board (technician view)
- [ ] Parts inventory with min/max alerts
- [ ] PDF work order forms
- [ ] Equipment status management (RTF, Missing, Deactivated)
- [ ] Audit trail

**Phase 3 — Reporting (nice to have):**
- [ ] PM compliance reports by period
- [ ] Technician productivity reports
- [ ] Equipment downtime reports
- [ ] Inventory consumption reports
- [ ] Dashboard KPIs

**Phase 4 — Advanced:**
- [ ] Document/manual management
- [ ] CSV/Excel bulk import
- [ ] Email notifications
- [ ] Mobile-friendly UI
- [ ] API for integration

## CMMS Best Practices

1. **Asset IDs are immutable** — Once assigned, never change `asset_id`. Use it as FK everywhere.
2. **Never hard-delete equipment** — Status transitions only. Audit history preserved.
3. **Denormalize next PM dates** — Store `next_pm_*` on the equipment record for fast scheduling queries. Update after every PM completion.
4. **PDF every completion** — Generate and store a signed PDF for every completed PM. Required for compliance audits.
5. **Audit everything** — Log every INSERT/UPDATE/DELETE with old and new values.
6. **CSV as a backup format** — Maintain a CSV export as a human-readable backup of equipment data.
7. **Priority drives the schedule** — Overdue PMs (P1) must fill the schedule before scheduled PMs (P4). Never let equipment fall further behind.
8. **Technician capacity** — Respect realistic daily/weekly work capacity (hours). Don't assign 200 PMs to one technician.
9. **Parts before scheduling** — Don't schedule a PM if required parts are out of stock.
10. **Location grouping** — Assign same-location PMs to same technician to minimize travel.
