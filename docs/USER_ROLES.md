# AIT CMMS 2.3.2 — User Roles & Permissions

## Role Definitions

### Manager
Full system access. Responsible for configuration, user management, and oversight.

**Exclusive capabilities:**
- Create, edit, deactivate user accounts
- View and manage all users' sessions
- Create and restore database backups
- Approve Run-to-Failure designations
- Close corrective maintenance work orders
- View all technician workloads and KPIs
- Configure PM scheduling parameters
- Access all reports

### Technician
Day-to-day maintenance operations. Cannot modify system configuration.

**Capabilities:**
- View and search all equipment
- View their own PM schedule
- Record PM completions (generates PDF)
- View PM history for equipment
- Add notes to work orders
- View MRO inventory (read-only)
- Change their own password

**Restrictions:**
- Cannot manage users
- Cannot perform database backups
- Cannot approve Run-to-Failure
- Cannot close/delete work orders
- Cannot modify inventory quantities

### Parts Coordinator
Inventory-focused role. Manages MRO stock and parts requests.

**Capabilities:**
- Full MRO inventory management (create/update/delete items)
- Adjust stock quantities with reason tracking
- Upload/manage item photos
- Export inventory reports
- Manage parts requests (cm_parts_requests)
- View equipment registry (read-only)
- View PM schedules (read-only)
- Change their own password

**Restrictions:**
- Cannot manage users
- Cannot record PM completions
- Cannot create work orders
- Cannot access backup functions

---

## Role Implementation

Roles are stored in the `users.role` column and loaded at login:

```python
# After successful authentication
self.current_user_role = user_row['role']
self.current_user_name = user_row['username']
self.current_user_full_name = user_row['full_name']
self.user_id = user_row['id']
```

UI elements are gated at creation time:

```python
def create_user_management_button(self):
    state = 'normal' if self.current_user_role == 'Manager' else 'disabled'
    btn = ttk.Button(
        self.toolbar,
        text="Manage Users",
        state=state,
        command=self.open_user_management
    )
```

---

## Default Users Created on Init

| Username | Full Name | Role | Purpose |
|----------|-----------|------|---------|
| admin | System Administrator | Manager | Initial setup account |
| apenson | A. Penson | Parts Coordinator | Default parts coordinator |

Both have known default passwords that **must be changed** after first login.

---

## Session Tracking

Every login creates a `user_sessions` record:

```sql
INSERT INTO user_sessions (user_id, username, login_time, is_active)
VALUES (?, ?, datetime('now'), 1)
```

On logout or app close:
```sql
UPDATE user_sessions
SET logout_time = datetime('now'), is_active = 0
WHERE id = ? AND is_active = 1
```

A Manager can view all active sessions and force-logout users if needed.

---

## Password Rules

Current implementation:
- Stored as SHA256 hex digest
- No minimum length enforced in code (UI may prompt)
- No complexity requirements enforced in code
- No expiry policy

**Recommended improvements for production:**
- Use `bcrypt` with work factor ≥ 12
- Minimum 12 characters
- Require uppercase + digit + symbol
- 90-day expiry with history check
- Account lockout after 5 failed attempts

---

## Adding a New Role

To add a role (e.g., "Supervisor"):

1. Add role option to user creation form in `user_management_ui.py`
2. Add permission checks throughout `AIT_CMMS_REV3.py` where Manager-only gates exist
3. Update role-check helper:

```python
def has_permission(self, permission: str) -> bool:
    PERMISSIONS = {
        'Manager': ['user_manage', 'backup', 'approve_rtf', 'close_wo', 'all_reports'],
        'Supervisor': ['approve_rtf', 'close_wo', 'all_reports'],
        'Technician': ['pm_complete', 'view_schedule'],
        'Parts Coordinator': ['mro_manage', 'parts_request'],
    }
    return permission in PERMISSIONS.get(self.current_user_role, [])
```
