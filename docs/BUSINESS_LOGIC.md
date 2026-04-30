# AIT CMMS 2.3.2 — Business Logic

## PM Scheduling Logic

### PM Types and Frequencies

| PM Type | Frequency | Days Between PMs |
|---------|-----------|-----------------|
| Monthly | Every 30 days | 30 |
| Six Month | Every 180 days | 180 |
| Annual | Every 365 days | 365 |
| Run to Failure | Never scheduled | N/A |
| CANNOT FIND | Never scheduled | N/A |

### Priority Classification

Equipment is classified P1–P4 before scheduling:

| Priority | Condition | Description |
|----------|-----------|-------------|
| P1 | PM overdue by > 0 days | Critical — schedule immediately |
| P2 | PM due within this week | Normal due PM |
| P3 | PM due within 2 weeks | Soon due — fill schedule |
| P4 | PM eligible but not urgent | Low priority filler |

### Assignment Rules

1. **P1 first, then P2, P3, P4** — Higher priority equipment fills the schedule before lower priority.
2. **SAP grouping** — All equipment with the same `sap_material_no` goes to the same technician for that week. Reduces travel and setup time.
3. **Round-robin balancing** — Technicians receive assignments in rotation to balance workload.
4. **Capacity cap** — Maximum PMs per technician per week is calculated from `weekly_pm_target / num_technicians`.
5. **Weekly target** — 130 PMs per week system-wide.
6. **Deduplication** — Equipment already in `weekly_pm_schedules` for the target week is skipped.

### PM Eligibility Checks

Before scheduling, equipment must pass all checks:
- `status == 'Active'` (not deactivated, missing, or run-to-failure)
- Not in `cannot_find_assets` table
- Not in `run_to_failure_assets` table
- Not in `deactivated_assets` table
- Has the relevant PM flag set (`monthly_pm = 1`, etc.)
- Not already completed this cycle (last PM date + frequency > today - grace_period)

### Skydrol PM Special Case

Hydraulic units require a weekly Skydrol inspection separate from the monthly/annual PM schedule:
- Combined unit `HYD-UNITS-ALL` is created if legacy individual units exist
- Task generates a specialized PDF checklist
- Must be assigned to a qualified technician each week
- Recorded separately from standard PM completions

---

## Equipment Status State Machine

```
                    ┌─────────┐
                    │ Active  │◄─────────────────────┐
                    └────┬────┘                      │
                         │                           │
          ┌──────────────┼──────────────┐            │
          ▼              ▼              ▼            │
   ┌─────────────┐ ┌──────────┐ ┌──────────────┐   │
   │Cannot Find  │ │Run to    │ │ Deactivated  │   │
   │(Missing)    │ │Failure   │ │ (Retired)    │   │
   └──────┬──────┘ └──────────┘ └──────────────┘   │
          │ (found)                                 │
          └─────────────────────────────────────────┘
```

- **Active → Cannot Find**: Equipment physically missing. Assigned to technician to locate.
- **Active → Run to Failure**: Manager approves no-PM status with justification.
- **Active → Deactivated**: Equipment retired with reason documented.
- **Cannot Find → Active**: Equipment re-located. Removed from `cannot_find_assets`.
- **Run to Failure/Deactivated**: Terminal states (require manual DB intervention to reverse).

---

## Work Order Number Generation

All auto-generated numbers follow the pattern `PREFIX-YYYYMMDD-NNN`:

```python
def generate_cm_number():
    date_str = datetime.today().strftime('%Y%m%d')
    last_num = get_last_sequence_for_date(date_str, 'CM')
    return f"CM-{date_str}-{last_num + 1:03d}"
    # Example: CM-20260430-001
```

| Type | Prefix | Table |
|------|--------|-------|
| Corrective Maintenance | CM | corrective_maintenance |
| Equipment Missing Parts | EMP | equipment_missing_parts |
| Work Order | WO | work_orders |

---

## Password Security

```python
import hashlib

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, stored_hash: str) -> bool:
    return hash_password(password) == stored_hash
```

**Note**: SHA256 without salt. For production hardening, upgrade to `bcrypt` or `argon2-cffi`.

---

## Audit Logging

Every data modification is logged:

```python
class AuditLogger:
    def log(
        self,
        user_name: str,
        action: str,           # INSERT / UPDATE / DELETE
        table_name: str,
        record_id: str,
        old_values: dict = None,
        new_values: dict = None,
        notes: str = None
    ) -> None:
        audit_entry = {
            'user_name': user_name,
            'action': action,
            'table_name': table_name,
            'record_id': str(record_id),
            'old_values': json.dumps(old_values) if old_values else None,
            'new_values': json.dumps(new_values) if new_values else None,
            'notes': notes,
            'action_timestamp': datetime.now().isoformat()
        }
        INSERT INTO audit_log ...
```

**What gets audited:**
- Equipment creates, updates, status changes
- PM completions
- User creates, updates, deactivations
- MRO inventory adjustments
- Backup creates and restores

---

## CSV Synchronization Rules

**On Startup (CSV → Database):**
1. Read `PM_MASTER_2026_CLEANED.csv`
2. For each row, `INSERT OR REPLACE INTO equipment ...`
3. If equipment exists in DB but not CSV → leave it (manual additions preserved)
4. If equipment exists in CSV but not DB → insert it
5. CSV is authoritative for: `bfm_equipment_no`, `sap_material_no`, `description`, `location`, PM flags
6. DB is authoritative for: PM completion dates, photos, notes added via UI

**On PM Completion (DB → CSV):**
1. Update `last_*_pm` and `next_*_pm` dates in database
2. Immediately write updated row back to CSV
3. CSV is always consistent with last PM completion

**On Shutdown (DB → CSV):**
1. Export all equipment PM dates from database to CSV
2. Ensures CSV survives database file loss

---

## Multi-User Concurrency Control

When two users edit the same record simultaneously:

```python
# Read with version
SELECT *, version FROM equipment WHERE bfm_equipment_no = ?
# stored_version = row['version']

# Write with version check
rows_affected = UPDATE equipment
    SET description = ?, version = version + 1
    WHERE bfm_equipment_no = ? AND version = ?
    -- params: (new_description, bfm_no, stored_version)

if rows_affected == 0:
    raise ConcurrencyConflict("Record modified by another user")
```

If the update fails (0 rows affected), the user is shown the current values and asked to re-review.

---

## DPI Scaling Logic

```python
def get_dpi_scale_factor(screen_height: int) -> float:
    if screen_height >= 2160:   # 4K
        return 2.2
    elif screen_height >= 1440: # 1440p
        return 1.9
    else:                        # 1080p or less
        return 1.6

# Applied to all fonts
base_font_size = 12
scaled_font_size = int(base_font_size * scale_factor)
```

---

## MRO Stock Alert Logic

Items below minimum stock trigger visual alerts in the inventory UI:

```python
def is_low_stock(item: MROItem) -> bool:
    return item.quantity_in_stock <= item.minimum_stock

def get_stock_status_color(item: MROItem) -> str:
    if item.quantity_in_stock == 0:
        return 'red'        # Out of stock
    elif is_low_stock(item):
        return 'orange'     # Low stock warning
    else:
        return 'green'      # Adequate stock
```

---

## Backup Strategy

1. **Manual backup**: User-triggered, stored in `backups/` subdirectory
2. **Auto backup**: Scheduled interval (configurable hours), runs in background thread
3. **Backup format**: Copy of `ait_cmms.db` with timestamp in filename
4. **Verification**: SQLite integrity check on backup file before confirming success
5. **Retention**: Last N backups kept (configurable)
6. **Restore**: Copies backup over current `ait_cmms.db`, reinitializes connection pool
