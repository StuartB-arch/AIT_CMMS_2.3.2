# AIT CMMS 2.3.2 — Deployment Guide

## Requirements

### System Requirements
- **Python**: 3.8 or higher
- **OS**: Windows 10/11 (primary), Linux, macOS
- **RAM**: 512 MB minimum, 1 GB recommended
- **Storage**: 500 MB for application + database growth
- **Display**: 1080p minimum (1440p or 4K recommended)

### Python Dependencies

```bash
pip install pandas reportlab python-docx Pillow
```

Or create `requirements.txt`:
```
pandas>=1.5.0
reportlab>=3.6.0
python-docx>=0.8.11
Pillow>=9.0.0
```

Install:
```bash
pip install -r requirements.txt
```

**Built-in (no install needed):**
- `tkinter` (included with Python on Windows/Mac; on Linux: `sudo apt install python3-tk`)
- `sqlite3`
- `hashlib`
- `threading`
- `json`
- `csv`
- `pathlib`

---

## First-Time Setup

### 1. Clone or Copy the Application

```bash
git clone <repo-url>
cd AIT_CMMS_2.3.2
```

Or simply copy the directory to the target machine.

### 2. Prepare the CSV Master File

Place `PM_MASTER_2026_CLEANED.csv` in the application root directory. This file is the equipment master list and will be used to populate the database on first run.

**Required CSV columns:**
```
BFM Equipment No, SAP Material No, Description, Location,
Monthly PM, Six Month PM, Annual PM,
Last Monthly PM, Last Six Month PM, Last Annual PM,
Next Monthly PM, Next Six Month PM, Next Annual PM
```

### 3. Run the Application

```bash
python AIT_CMMS_REV3.py
```

On first run, the application will:
1. Create `ait_cmms.db` (SQLite database)
2. Create all 18 tables with indexes
3. Insert default users (admin, apenson)
4. Run CSV sync to import equipment from `PM_MASTER_2026_CLEANED.csv`

### 4. Change Default Passwords

Log in with the default admin credentials and immediately change the password for both default accounts via the User Management dialog.

---

## Shared Network Deployment (Multi-User)

For multiple users on the same network:

1. Place the application folder on a **network share** accessible to all users
2. All users run `AIT_CMMS_REV3.py` from the shared path
3. SQLite handles concurrent access via file locking (suitable for ~5 simultaneous users)

**Limitations of SQLite concurrent access:**
- Works well for up to ~5 simultaneous writers
- For more users, migrate to PostgreSQL (see below)

### Windows Network Share Example
```
\\SERVER\CMMS\AIT_CMMS_2.3.2\
  AIT_CMMS_REV3.py
  ait_cmms.db         ← shared database
  PM_MASTER_2026_CLEANED.csv
  img\
  ...
```

Create a shortcut on each user's desktop pointing to:
```
python \\SERVER\CMMS\AIT_CMMS_2.3.2\AIT_CMMS_REV3.py
```

---

## PostgreSQL Migration (Optional)

The application includes a legacy PostgreSQL configuration. To re-enable:

1. Set up a PostgreSQL server (or Neon cloud)
2. Update `DB_CONFIG` in `AIT_CMMS_REV3.py`:

```python
self.DB_CONFIG = {
    'host': 'your-postgres-host',
    'port': 5432,
    'database': 'cmms_db',
    'user': 'cmms_user',
    'password': 'your-password',
    'sslmode': 'require'
}
```

3. Run the schema creation scripts against PostgreSQL
4. Disable `sqlite_compat.py` conversions by using raw psycopg2 instead of the SQLite adapter

---

## Creating a Windows Executable

Use PyInstaller to create a standalone `.exe`:

```bash
pip install pyinstaller

pyinstaller --onefile \
  --add-data "img;img" \
  --add-data "PM_MASTER_2026_CLEANED.csv;." \
  --hidden-import="PIL._tkinter_finder" \
  --windowed \
  AIT_CMMS_REV3.py
```

The resulting `dist/AIT_CMMS_REV3.exe` runs without a Python installation.

**Notes:**
- `--windowed` suppresses the console window
- Add all `.py` module files as data if not auto-detected
- Database file (`ait_cmms.db`) should be distributed separately and placed beside the `.exe`

---

## Backup Configuration

Default backup directory: `./backups/` (relative to application root)

Backup files are named: `ait_cmms_backup_YYYYMMDD_HHMMSS.db`

Configure auto-backup interval in the Backup UI dialog. Recommended: every 4 hours.

---

## Updating the Application

1. Stop all user sessions (or notify users)
2. Create a manual backup via the Backup UI
3. Replace `.py` files with new versions
4. Run database migration if provided:
   ```bash
   python migrate_multiuser.py
   ```
5. Restart application — it will apply any schema changes automatically

---

## Troubleshooting

### Application Won't Start
```bash
python debug_startup.py
```
This runs startup diagnostics without launching the full GUI.

### Database Integrity Issues
```bash
python diagnose_assets.py
```

### Duplicate Equipment Records
```bash
python analyze_duplicate_assets.py
```

### Tkinter Not Available (Linux)
```bash
sudo apt-get install python3-tk
```

### Import Errors
```bash
pip install --upgrade pandas reportlab python-docx Pillow
```

---

## File Permissions

| File/Folder | Required Permission |
|------------|-------------------|
| `ait_cmms.db` | Read + Write (all users) |
| `PM_MASTER_2026_CLEANED.csv` | Read + Write (app updates it on PM completion) |
| `backups/` | Read + Write (backup creation) |
| `img/` | Read only |
| `*.py` | Read only (execute) |

---

## Environment Variables (Optional)

None required. All configuration is in-code. To externalize:

```python
import os
DB_PATH = os.environ.get('CMMS_DB_PATH', 'ait_cmms.db')
CSV_PATH = os.environ.get('CMMS_CSV_PATH', 'PM_MASTER_2026_CLEANED.csv')
BACKUP_DIR = os.environ.get('CMMS_BACKUP_DIR', 'backups')
```
