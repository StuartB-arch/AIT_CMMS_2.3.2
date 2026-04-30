# Skill: CSV Data Synchronization

## When to Use
- Master data lives in a spreadsheet that non-technical users maintain
- Need to import bulk equipment/item lists from Excel/CSV
- Need to export data for reporting in Excel
- CSV serves as a portable backup of the database
- On-startup sync to pick up changes made outside the app

## CSV Manager Pattern

```python
# utils/csv_sync.py
import csv
import pandas as pd
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Callable

@dataclass
class SyncResult:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list = None

    def __post_init__(self):
        self.errors = self.errors or []

    @property
    def total_processed(self):
        return self.inserted + self.updated + self.skipped

    def __str__(self):
        return (f"Sync complete: {self.inserted} inserted, "
                f"{self.updated} updated, {self.skipped} skipped, "
                f"{len(self.errors)} errors")


class CSVSyncManager:
    """
    Manages bidirectional sync between a CSV file and a database table.

    Usage:
        sync = CSVSyncManager(
            db=db,
            csv_path='equipment.csv',
            table='equipment',
            key_column='asset_id',         # DB column name
            csv_key_column='Asset ID',     # CSV header name
            column_map={                   # CSV header → DB column
                'Asset ID': 'asset_id',
                'Name': 'name',
                'Location': 'location',
            }
        )
        result = sync.import_csv()         # CSV → DB
        sync.export_csv()                  # DB → CSV
    """

    def __init__(
        self,
        db,
        csv_path: str,
        table: str,
        key_column: str,
        csv_key_column: str,
        column_map: dict[str, str],
        transform_in: Callable = None,   # Optional transform on import
        transform_out: Callable = None,  # Optional transform on export
    ):
        self.db = db
        self.csv_path = Path(csv_path)
        self.table = table
        self.key_column = key_column
        self.csv_key_column = csv_key_column
        self.column_map = column_map
        self.transform_in = transform_in
        self.transform_out = transform_out

    def import_csv(self, upsert: bool = True) -> SyncResult:
        """Read CSV and upsert/insert into database."""
        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV not found: {self.csv_path}")

        result = SyncResult()

        with open(self.csv_path, 'r', newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        for i, csv_row in enumerate(rows, 2):
            try:
                # Map CSV columns to DB columns
                db_row = {}
                for csv_col, db_col in self.column_map.items():
                    raw = csv_row.get(csv_col, '').strip()
                    db_row[db_col] = self._coerce_value(db_col, raw)

                # Apply optional transform
                if self.transform_in:
                    db_row = self.transform_in(db_row)

                key_value = db_row.get(self.key_column)
                if not key_value:
                    result.skipped += 1
                    continue

                # Check if exists
                existing = self.db.fetchone(
                    f"SELECT {self.key_column} FROM {self.table} WHERE {self.key_column} = ?",
                    (key_value,)
                )

                if existing and upsert:
                    # Update existing
                    db_row['updated_at'] = datetime.now().isoformat()
                    set_clause = ', '.join([f"{k} = ?" for k in db_row if k != self.key_column])
                    params = [v for k, v in db_row.items() if k != self.key_column]
                    params.append(key_value)
                    self.db.execute(
                        f"UPDATE {self.table} SET {set_clause} WHERE {self.key_column} = ?",
                        tuple(params)
                    )
                    result.updated += 1
                elif not existing:
                    # Insert new
                    db_row['created_at'] = datetime.now().isoformat()
                    cols = ', '.join(db_row.keys())
                    placeholders = ', '.join(['?'] * len(db_row))
                    self.db.execute(
                        f"INSERT INTO {self.table} ({cols}) VALUES ({placeholders})",
                        tuple(db_row.values())
                    )
                    result.inserted += 1
                else:
                    result.skipped += 1

            except Exception as e:
                result.errors.append(f"Row {i}: {e}")

        return result

    def export_csv(self, where: str = '', params: tuple = ()) -> Path:
        """Export database table to CSV file."""
        db_cols = list(self.column_map.values())
        csv_cols = list(self.column_map.keys())

        sql = f"SELECT {', '.join(db_cols)} FROM {self.table}"
        if where:
            sql += f" WHERE {where}"
        sql += f" ORDER BY {self.key_column}"

        rows = self.db.fetchall(sql, params)

        with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(csv_cols)
            for row in rows:
                record = dict(row)
                if self.transform_out:
                    record = self.transform_out(record)
                writer.writerow([record.get(col, '') for col in db_cols])

        return self.csv_path

    def update_single_record(self, key_value: str, updates: dict):
        """Update one record in DB and immediately write it back to CSV."""
        # Update in DB
        set_clause = ', '.join([f"{k} = ?" for k in updates])
        params = tuple(updates.values()) + (key_value,)
        self.db.execute(
            f"UPDATE {self.table} SET {set_clause} WHERE {self.key_column} = ?",
            params
        )

        # Refresh CSV (re-export full table)
        self.export_csv()

    def _coerce_value(self, column: str, raw: str):
        """Convert empty strings and type-coerce values."""
        if raw == '' or raw is None:
            return None
        # Boolean columns
        if column.startswith(('is_', 'has_', 'pm_', 'monthly_', 'annual_', 'active_')):
            return 1 if raw.lower() in ('1', 'true', 'yes', 'x', 'y') else 0
        # Date columns
        if column.endswith(('_date', '_at', '_pm')):
            return self._parse_date(raw)
        return raw

    @staticmethod
    def _parse_date(value: str) -> str | None:
        """Parse flexible date strings to YYYY-MM-DD."""
        if not value:
            return None
        formats = ['%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%d/%m/%Y', '%Y/%m/%d',
                   '%m/%d/%y', '%B %d, %Y', '%b %d, %Y']
        for fmt in formats:
            try:
                return datetime.strptime(value.strip(), fmt).strftime('%Y-%m-%d')
            except ValueError:
                continue
        return None  # Could not parse
```

## Pandas-Powered Import (for Complex Sheets)

```python
def import_excel_sheet(
    db,
    excel_path: str,
    sheet_name: str,
    table: str,
    column_map: dict,
    key_col: str
) -> SyncResult:
    """Import from Excel with pandas (handles merged cells, multi-header, etc.)"""
    df = pd.read_excel(excel_path, sheet_name=sheet_name, header=0)

    # Rename columns
    df = df.rename(columns={v: k for k, v in column_map.items()})

    # Drop rows where key is empty
    df = df.dropna(subset=[key_col])

    # Strip whitespace from all string columns
    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].str.strip()

    result = SyncResult()
    for _, row in df.iterrows():
        try:
            record = row.where(pd.notna(row), None).to_dict()
            # ... upsert logic same as above
            result.inserted += 1
        except Exception as e:
            result.errors.append(str(e))

    return result
```

## Background Sync Thread

```python
import threading

def run_startup_sync_in_background(sync_manager: CSVSyncManager, on_complete: callable = None):
    """Run CSV import in background thread so UI stays responsive."""
    def _run():
        try:
            result = sync_manager.import_csv()
            print(f"Background sync: {result}")
            if on_complete:
                on_complete(result)
        except Exception as e:
            print(f"Background sync error: {e}")

    thread = threading.Thread(target=_run, daemon=True, name="csv-sync")
    thread.start()
    return thread
```

## Date Parsing Utility

```python
from datetime import datetime

DATE_FORMATS = [
    '%Y-%m-%d',       # 2026-04-30 (ISO)
    '%m/%d/%Y',       # 04/30/2026 (US)
    '%m-%d-%Y',       # 04-30-2026
    '%d/%m/%Y',       # 30/04/2026 (EU)
    '%m/%d/%y',       # 04/30/26 (short year)
    '%B %d, %Y',      # April 30, 2026
    '%b %d, %Y',      # Apr 30, 2026
    '%Y%m%d',         # 20260430 (compact)
]

def parse_date_flexible(value: str) -> str | None:
    """Try all common date formats, return YYYY-MM-DD or None."""
    if not value or not str(value).strip():
        return None
    value = str(value).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None
```

## CSV Validation Before Import

```python
def validate_csv(filepath: str, required_columns: list[str]) -> list[str]:
    """Returns list of error messages. Empty list = valid."""
    errors = []
    try:
        with open(filepath, 'r', newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []

            # Check required columns present
            for col in required_columns:
                if col not in headers:
                    errors.append(f"Missing required column: '{col}'")

            if errors:
                return errors  # Don't bother reading rows

            # Check for empty key column
            key_col = required_columns[0]
            for i, row in enumerate(reader, 2):
                if not row.get(key_col, '').strip():
                    errors.append(f"Row {i}: Empty value in required column '{key_col}'")

    except Exception as e:
        errors.append(f"Cannot read file: {e}")

    return errors
```

## Tkinter File Picker Integration

```python
from tkinter import filedialog, messagebox

def pick_and_import_csv(parent_widget, sync_manager: CSVSyncManager):
    filepath = filedialog.askopenfilename(
        parent=parent_widget,
        title="Select CSV File",
        filetypes=[("CSV Files", "*.csv"), ("All Files", "*.*")]
    )
    if not filepath:
        return

    # Validate first
    errors = validate_csv(filepath, required_columns=['Asset ID', 'Name'])
    if errors:
        messagebox.showerror("Invalid CSV", '\n'.join(errors[:10]), parent=parent_widget)
        return

    # Import
    try:
        result = sync_manager.import_csv_from_path(filepath)
        messagebox.showinfo(
            "Import Complete",
            f"Imported successfully!\n\n"
            f"New records: {result.inserted}\n"
            f"Updated: {result.updated}\n"
            f"Errors: {len(result.errors)}",
            parent=parent_widget
        )
        if result.errors:
            messagebox.showwarning("Import Warnings",
                                   '\n'.join(result.errors[:20]),
                                   parent=parent_widget)
    except Exception as e:
        messagebox.showerror("Import Failed", str(e), parent=parent_widget)
```

## Best Practices

1. **CSV as authoritative backup** — Export DB → CSV on shutdown, import CSV → DB on startup.
2. **`utf-8-sig` encoding** — Handles Excel's BOM (byte-order mark) that breaks standard `utf-8`.
3. **Strip all values** — CSV data almost always has leading/trailing spaces.
4. **Parse dates flexibly** — Users type dates in every format imaginable.
5. **`INSERT OR IGNORE` / upsert** — Never crash on duplicate keys; update instead.
6. **Validate before importing** — Check required columns and key values before processing thousands of rows.
7. **Background thread for large files** — Never block the UI thread during file I/O.
8. **Log every import** — Audit who imported what file when, with counts.
9. **Preserve DB-only fields** — CSV import should NOT overwrite fields that only exist in DB (photos, notes added via UI).
10. **`repeatrows=1` on multi-page exports** — Always repeat table headers on PDF/Excel exports.
