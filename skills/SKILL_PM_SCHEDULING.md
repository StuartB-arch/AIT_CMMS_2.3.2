# Skill: Preventive Maintenance Scheduling Engine

## What This Skill Covers
Building a PM scheduling system that:
- Determines what equipment needs maintenance and when
- Prioritizes work (overdue first)
- Distributes work across technicians fairly
- Respects technician capacity
- Groups related work to reduce travel
- Prevents scheduling deactivated / run-to-failure equipment

## Core Concepts

| Term | Definition |
|------|-----------|
| PM Frequency | Days between PMs (Monthly=30, Quarterly=90, Annual=365) |
| Due Date | `last_pm_date + frequency` |
| Overdue | Today > due_date |
| Priority | P1=overdue, P2=due this week, P3=due soon, P4=filler |
| Capacity | Max PMs a technician can do in a week |
| Technician Workload | Count of PMs assigned to a technician for a given week |
| Grouping | Assigning related equipment to the same technician |

## Complete Scheduling Engine

```python
# pm_scheduling_engine.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import IntEnum
from typing import Callable

# --- Domain Types ---

class Priority(IntEnum):
    P1_OVERDUE = 1
    P2_DUE_THIS_WEEK = 2
    P3_DUE_SOON = 3
    P4_ELIGIBLE = 4

PM_FREQUENCIES: dict[str, int] = {
    'Monthly': 30,
    'Quarterly': 90,
    'Semi-Annual': 180,
    'Annual': 365,
}

@dataclass
class Equipment:
    asset_id: str
    name: str
    location: str
    group_key: str = ''         # e.g., SAP number — group by same group_key
    pm_types: list[str] = field(default_factory=list)   # Which PMs this equipment needs
    last_pm: dict[str, date | None] = field(default_factory=dict)

@dataclass
class PMAssignment:
    asset_id: str
    pm_type: str
    priority: Priority
    technician: str
    week_start: date
    notes: str = ''

    @property
    def week_end(self) -> date:
        return self.week_start + timedelta(days=4)  # Monday–Friday

# --- Eligibility Checker ---

def get_pm_priority(
    last_pm: date | None,
    pm_type: str,
    today: date,
    due_soon_days: int = 14,
    eligible_window_days: int = 30,
) -> Priority | None:
    freq = PM_FREQUENCIES.get(pm_type)
    if freq is None:
        return None

    if last_pm is None:
        return Priority.P1_OVERDUE  # Never done = overdue

    days_since = (today - last_pm).days
    days_until_due = freq - days_since

    if days_until_due <= 0:
        return Priority.P1_OVERDUE
    elif days_until_due <= 7:
        return Priority.P2_DUE_THIS_WEEK
    elif days_until_due <= due_soon_days:
        return Priority.P3_DUE_SOON
    elif days_until_due <= eligible_window_days:
        return Priority.P4_ELIGIBLE
    else:
        return None  # Not eligible yet


def get_eligible_work(
    equipment_list: list[Equipment],
    today: date,
    excluded_asset_ids: set[str] = None,
) -> list[tuple[Equipment, str, Priority]]:
    """
    Returns list of (equipment, pm_type, priority) sorted P1→P4.
    Excludes equipment in excluded_asset_ids (deactivated, RTF, missing).
    """
    excluded = excluded_asset_ids or set()
    eligible = []

    for equip in equipment_list:
        if equip.asset_id in excluded:
            continue
        for pm_type in equip.pm_types:
            priority = get_pm_priority(
                equip.last_pm.get(pm_type),
                pm_type,
                today
            )
            if priority is not None:
                eligible.append((equip, pm_type, priority))

    # Sort: P1 first, then by days since last PM descending (oldest first)
    eligible.sort(key=lambda x: (
        x[2].value,
        -(today - (x[0].last_pm.get(x[1]) or date.min)).days
    ))
    return eligible


# --- Assignment Generator ---

def generate_weekly_schedule(
    equipment_list: list[Equipment],
    technicians: list[str],
    week_start: date,
    weekly_target: int = 100,
    excluded_asset_ids: set[str] = None,
    already_scheduled: set[tuple[str, str]] = None,  # {(asset_id, pm_type)}
    group_key_fn: Callable[[Equipment], str] = None,
) -> list[PMAssignment]:
    """
    Generates PM assignments for one week.

    Args:
        equipment_list: All active equipment
        technicians: Available technician names
        week_start: Monday of the target week
        weekly_target: Total PMs to schedule for the week
        excluded_asset_ids: Equipment to skip (RTF, missing, deactivated)
        already_scheduled: (asset_id, pm_type) pairs already assigned this week
        group_key_fn: Optional function to group equipment → same technician
    """
    if not technicians:
        return []

    today = week_start
    already_scheduled = already_scheduled or set()
    max_per_tech = weekly_target // len(technicians)

    # Get all eligible work not yet scheduled
    eligible = [
        (eq, pm_type, priority)
        for eq, pm_type, priority in get_eligible_work(equipment_list, today, excluded_asset_ids)
        if (eq.asset_id, pm_type) not in already_scheduled
    ]

    # Track technician workloads
    tech_workload: dict[str, int] = {t: 0 for t in technicians}

    # Track group → technician assignments (for SAP/location grouping)
    group_assignment: dict[str, str] = {}

    assignments: list[PMAssignment] = []

    for equip, pm_type, priority in eligible:
        if len(assignments) >= weekly_target:
            break

        # Find technician for this equipment
        group_key = (group_key_fn(equip) if group_key_fn else '') or equip.asset_id

        # If we've already assigned this group, use same technician
        if group_key in group_assignment:
            tech = group_assignment[group_key]
            if tech_workload.get(tech, 0) >= max_per_tech:
                # Group tech is full — skip or find another
                tech = _pick_least_loaded_tech(tech_workload, max_per_tech)
        else:
            tech = _pick_least_loaded_tech(tech_workload, max_per_tech)

        if tech is None:
            continue  # All technicians at capacity

        group_assignment[group_key] = tech
        tech_workload[tech] += 1

        assignments.append(PMAssignment(
            asset_id=equip.asset_id,
            pm_type=pm_type,
            priority=priority,
            technician=tech,
            week_start=week_start,
        ))

    return assignments


def _pick_least_loaded_tech(
    workload: dict[str, int],
    max_per_tech: int
) -> str | None:
    available = [(count, tech) for tech, count in workload.items() if count < max_per_tech]
    if not available:
        return None
    return min(available)[1]  # Technician with fewest assignments
```

## Database Integration

```python
# How to use the engine with SQLite data

def load_equipment_for_scheduling(db) -> list[Equipment]:
    """Load all active equipment from database."""
    rows = db.fetchall("""
        SELECT asset_id, name, location, sap_material_no,
               pm_monthly, pm_quarterly, pm_annual,
               last_pm_monthly, last_pm_quarterly, last_pm_annual
        FROM equipment
        WHERE status = 'Active'
    """)

    result = []
    for row in rows:
        pm_types = []
        if row['pm_monthly']:   pm_types.append('Monthly')
        if row['pm_quarterly']: pm_types.append('Quarterly')
        if row['pm_annual']:    pm_types.append('Annual')

        if not pm_types:
            continue  # No PM needed

        last_pm = {}
        for pt in pm_types:
            col = f'last_pm_{pt.lower()}'
            raw = row[col]
            last_pm[pt] = date.fromisoformat(raw) if raw else None

        result.append(Equipment(
            asset_id=row['asset_id'],
            name=row['name'],
            location=row['location'],
            group_key=row['sap_material_no'] or row['asset_id'],
            pm_types=pm_types,
            last_pm=last_pm,
        ))
    return result


def get_excluded_equipment(db) -> set[str]:
    """Asset IDs that should not be scheduled."""
    excluded = set()
    for table in ('cannot_find_assets', 'run_to_failure_assets', 'deactivated_assets'):
        rows = db.fetchall(f"SELECT asset_id FROM {table}")
        excluded.update(r['asset_id'] for r in rows)
    return excluded


def get_already_scheduled(db, week_start: date) -> set[tuple]:
    """Assignments already in the schedule for this week."""
    rows = db.fetchall("""
        SELECT asset_id, pm_type FROM scheduled_maintenance
        WHERE week_start = ? AND status != 'Cancelled'
    """, (week_start.isoformat(),))
    return {(r['asset_id'], r['pm_type']) for r in rows}


def save_schedule(db, assignments: list[PMAssignment]):
    """Persist assignments to database."""
    with db.transaction() as cursor:
        for a in assignments:
            cursor.execute("""
                INSERT OR IGNORE INTO scheduled_maintenance
                    (asset_id, pm_type, assigned_to, week_start, status, created_at)
                VALUES (?, ?, ?, ?, 'Scheduled', datetime('now'))
            """, (a.asset_id, a.pm_type, a.technician, a.week_start.isoformat()))


# Full workflow:
def run_weekly_scheduling(db, technicians: list[str], week_start: date) -> list[PMAssignment]:
    equipment = load_equipment_for_scheduling(db)
    excluded = get_excluded_equipment(db)
    already_scheduled = get_already_scheduled(db, week_start)

    assignments = generate_weekly_schedule(
        equipment_list=equipment,
        technicians=technicians,
        week_start=week_start,
        weekly_target=130,
        excluded_asset_ids=excluded,
        already_scheduled=already_scheduled,
        group_key_fn=lambda eq: eq.group_key,
    )

    save_schedule(db, assignments)
    return assignments
```

## PM Completion Recording

```python
def record_pm_completion(
    db,
    asset_id: str,
    pm_type: str,
    technician: str,
    completed_date: date,
    labor_hours: float,
    notes: str = '',
    checklist: list[dict] = None
) -> int:
    import json
    freq = PM_FREQUENCIES[pm_type]
    next_due = (completed_date + timedelta(days=freq)).isoformat()

    with db.transaction() as cursor:
        # 1. Record completion
        cursor.execute("""
            INSERT INTO pm_completions
                (asset_id, pm_type, completed_by, completed_date,
                 labor_hours, notes, checklist_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """, (asset_id, pm_type, technician, completed_date.isoformat(),
              labor_hours, notes, json.dumps(checklist) if checklist else None))
        completion_id = cursor.lastrowid

        # 2. Update equipment PM dates
        last_col = f"last_pm_{pm_type.lower().replace(' ', '_')}"
        next_col = f"next_pm_{pm_type.lower().replace(' ', '_')}"
        cursor.execute(f"""
            UPDATE equipment
            SET {last_col} = ?, {next_col} = ?, updated_at = datetime('now')
            WHERE asset_id = ?
        """, (completed_date.isoformat(), next_due, asset_id))

        # 3. Update schedule record to Completed
        cursor.execute("""
            UPDATE scheduled_maintenance
            SET status = 'Completed', completed_date = ?, actual_hours = ?
            WHERE asset_id = ? AND pm_type = ? AND status = 'Scheduled'
        """, (completed_date.isoformat(), labor_hours, asset_id, pm_type))

    return completion_id
```

## PM Compliance Report

```python
def get_pm_compliance(db, start_date: date, end_date: date) -> dict:
    """Calculate PM compliance rate for a date range."""
    scheduled = db.fetchone("""
        SELECT COUNT(*) as total FROM scheduled_maintenance
        WHERE week_start BETWEEN ? AND ?
        AND status != 'Cancelled'
    """, (start_date.isoformat(), end_date.isoformat()))['total']

    completed = db.fetchone("""
        SELECT COUNT(*) as total FROM scheduled_maintenance
        WHERE week_start BETWEEN ? AND ?
        AND status = 'Completed'
    """, (start_date.isoformat(), end_date.isoformat()))['total']

    return {
        'scheduled': scheduled,
        'completed': completed,
        'compliance_rate': (completed / scheduled * 100) if scheduled else 0,
        'overdue': scheduled - completed,
    }
```
