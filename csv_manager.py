"""
csv_manager.py — AIT CMMS CSV Integration
Handles bidirectional sync between PM_MASTER_2026_CLEANED.csv and the PostgreSQL database.

  startup_sync()   → reads CSV, upserts into DB (new rows + updates PM flags/dates)
  shutdown_export()→ reads DB, writes updated PM dates back to CSV
  update_equipment_pm_dates() → updates a single record after PM completion
"""
import os
import shutil
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable


CSV_FILENAME = "PM_MASTER_2026_CLEANED.csv"

# Maps CSV column headers to database column names
_CSV_TO_DB = {
    "SAP Material No":    "sap_material_no",
    "BFM Equipment No":   "bfm_equipment_no",
    "Description":        "description",
    "Tool ID/Drawing No": "tool_id_drawing_no",
    "Location":           "location",
    "Master LIN":         "master_lin",
    "Monthly PM":         "monthly_pm",
    "Six Month PM":       "six_month_pm",
    "Annual PM":          "annual_pm",
    "Last Monthly PM":    "last_monthly_pm",
    "Last Six Month PM":  "last_six_month_pm",
    "Last Annual PM":     "last_annual_pm",
    "Next Monthly PM":    "next_monthly_pm",
    "Next Six Month PM":  "next_six_month_pm",
    "Next Annual PM":     "next_annual_pm",
    "Status":             "status",
}

_PM_INTERVALS = {
    "Monthly":   ("Last Monthly PM",   "Next Monthly PM",   30),
    "Six Month": ("Last Six Month PM", "Next Six Month PM", 180),
    "Annual":    ("Last Annual PM",    "Next Annual PM",    365),
}


def _csv_path() -> Path:
    return Path(__file__).parent / CSV_FILENAME


def _parse_bool(val) -> bool:
    if isinstance(val, bool):
        return val
    return str(val).strip().lower() in ("true", "1", "yes")


def _norm_date(val) -> Optional[str]:
    """Normalize date to YYYY-MM-DD string; returns None if blank/invalid."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("none", "nat", "nan", ""):
        return None
    for fmt in ("%m/%d/%Y %H:%M", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.split(" ")[0], fmt.split(" ")[0]).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s  # return as-is if unparseable


def _newer(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """Return the more recent of two YYYY-MM-DD date strings; None beats nothing."""
    if not a:
        return b
    if not b:
        return a
    try:
        return a if datetime.strptime(a[:10], "%Y-%m-%d") >= datetime.strptime(b[:10], "%Y-%m-%d") else b
    except ValueError:
        return a


def _fmt_date(val) -> str:
    if not val:
        return ""
    return str(val).split(" ")[0]


def _fmt_bool(val) -> str:
    return "True" if val else "False"


def _safe_str(val) -> str:
    s = str(val).strip() if val is not None else ""
    return "" if s.lower() in ("nan", "none") else s


class CSVManager:
    """Manages read/write sync between PM_MASTER_2026_CLEANED.csv and PostgreSQL."""

    def __init__(self, conn, csv_path: Optional[str] = None):
        self.conn = conn
        self.path = Path(csv_path) if csv_path else _csv_path()

    # ── Startup ──────────────────────────────────────────────────────────────

    def startup_sync(self, status_cb: Optional[Callable] = None) -> dict:
        """
        Read CSV and upsert all records into the database.
        - New BFM numbers → INSERT
        - Existing records → UPDATE pm flags, metadata, and merge dates (keep newer)
        Returns a result dict: {inserted, updated, skipped, errors}
        """
        if not self.path.exists():
            msg = f"PM Master CSV not found: {self.path}"
            print(f"[CSVManager] WARNING: {msg}")
            return {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0, "message": msg}

        if status_cb:
            status_cb("Reading PM Master CSV file...")

        try:
            df = pd.read_csv(self.path, encoding="utf-8-sig", dtype=str)
            df.columns = df.columns.str.strip()
        except Exception as exc:
            print(f"[CSVManager] ERROR reading CSV: {exc}")
            return {"inserted": 0, "updated": 0, "skipped": 0, "errors": 1, "message": str(exc)}

        inserted = updated = skipped = errors = 0
        total = len(df)
        cursor = self.conn.cursor()

        for idx, row in df.iterrows():
            bfm_no = _safe_str(row.get("BFM Equipment No", ""))
            if not bfm_no:
                skipped += 1
                continue

            if status_cb and idx % 200 == 0:
                status_cb(f"Syncing CSV → database ({idx}/{total})…")

            try:
                sap_no       = _safe_str(row.get("SAP Material No", ""))
                description  = _safe_str(row.get("Description", ""))
                tool_id      = _safe_str(row.get("Tool ID/Drawing No", ""))
                location     = _safe_str(row.get("Location", ""))
                master_lin   = _safe_str(row.get("Master LIN", ""))
                monthly_pm   = _parse_bool(row.get("Monthly PM", "False"))
                six_month_pm = _parse_bool(row.get("Six Month PM", "False"))
                annual_pm    = _parse_bool(row.get("Annual PM", "False"))
                last_monthly  = _norm_date(row.get("Last Monthly PM"))
                last_six      = _norm_date(row.get("Last Six Month PM"))
                last_annual   = _norm_date(row.get("Last Annual PM"))
                next_monthly  = _norm_date(row.get("Next Monthly PM"))
                next_six      = _norm_date(row.get("Next Six Month PM"))
                next_annual   = _norm_date(row.get("Next Annual PM"))
                status = _safe_str(row.get("Status", "Active")) or "Active"

                cursor.execute(
                    """SELECT id, last_monthly_pm, last_six_month_pm, last_annual_pm
                       FROM equipment WHERE bfm_equipment_no = %s""",
                    (bfm_no,),
                )
                existing = cursor.fetchone()

                if existing is None:
                    cursor.execute(
                        """INSERT INTO equipment (
                               sap_material_no, bfm_equipment_no, description,
                               tool_id_drawing_no, location, master_lin,
                               monthly_pm, six_month_pm, annual_pm,
                               last_monthly_pm, last_six_month_pm, last_annual_pm,
                               next_monthly_pm, next_six_month_pm, next_annual_pm,
                               status
                           ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (
                            sap_no, bfm_no, description, tool_id, location, master_lin,
                            monthly_pm, six_month_pm, annual_pm,
                            last_monthly, last_six, last_annual,
                            next_monthly, next_six, next_annual,
                            status,
                        ),
                    )
                    inserted += 1
                else:
                    # Merge dates: keep whichever is more recent (DB completion records win ties)
                    final_last_monthly = _newer(existing[1], last_monthly)
                    final_last_six     = _newer(existing[2], last_six)
                    final_last_annual  = _newer(existing[3], last_annual)

                    cursor.execute(
                        """UPDATE equipment SET
                               sap_material_no     = %s,
                               description         = %s,
                               tool_id_drawing_no  = %s,
                               location            = %s,
                               master_lin          = %s,
                               monthly_pm          = %s,
                               six_month_pm        = %s,
                               annual_pm           = %s,
                               last_monthly_pm     = %s,
                               last_six_month_pm   = %s,
                               last_annual_pm      = %s,
                               next_monthly_pm     = %s,
                               next_six_month_pm   = %s,
                               next_annual_pm      = %s,
                               status              = %s,
                               updated_date        = CURRENT_TIMESTAMP
                           WHERE bfm_equipment_no = %s""",
                        (
                            sap_no, description, tool_id, location, master_lin,
                            monthly_pm, six_month_pm, annual_pm,
                            final_last_monthly, final_last_six, final_last_annual,
                            next_monthly, next_six, next_annual,
                            status, bfm_no,
                        ),
                    )
                    updated += 1

            except Exception as exc:
                errors += 1
                print(f"[CSVManager] ERROR row {idx} ({bfm_no}): {exc}")

        try:
            self.conn.commit()
        except Exception as exc:
            print(f"[CSVManager] ERROR commit failed: {exc}")
            errors += 1

        msg = f"CSV sync: {inserted} new, {updated} updated, {skipped} skipped, {errors} errors"
        print(f"[CSVManager] {msg}")
        if status_cb:
            status_cb(msg)
        return {"inserted": inserted, "updated": updated, "skipped": skipped, "errors": errors}

    # ── Shutdown ─────────────────────────────────────────────────────────────

    def shutdown_export(self, status_cb: Optional[Callable] = None) -> bool:
        """
        Export current database equipment state back to the CSV.
        Creates a timestamped backup of the original CSV first.
        Returns True on success.
        """
        if status_cb:
            status_cb("Exporting PM data to CSV…")

        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """SELECT sap_material_no, bfm_equipment_no, description,
                          tool_id_drawing_no, location, master_lin,
                          monthly_pm, six_month_pm, annual_pm,
                          last_monthly_pm, last_six_month_pm, last_annual_pm,
                          next_monthly_pm, next_six_month_pm, next_annual_pm,
                          status
                   FROM equipment ORDER BY id"""
            )
            rows = cursor.fetchall()
        except Exception as exc:
            print(f"[CSVManager] ERROR querying DB for export: {exc}")
            return False

        db_by_bfm = {row[1]: row for row in rows if row[1]}

        # Load existing CSV to preserve the ID column and row order
        if self.path.exists():
            try:
                existing_df = pd.read_csv(self.path, encoding="utf-8-sig", dtype=str)
                existing_df.columns = existing_df.columns.str.strip()
            except Exception as exc:
                print(f"[CSVManager] WARNING: could not read existing CSV: {exc}")
                existing_df = None
        else:
            existing_df = None

        if existing_df is not None and "BFM Equipment No" in existing_df.columns:
            # Update rows in place
            for idx, csv_row in existing_df.iterrows():
                bfm_no = _safe_str(csv_row.get("BFM Equipment No", ""))
                if bfm_no in db_by_bfm:
                    r = db_by_bfm[bfm_no]
                    existing_df.at[idx, "SAP Material No"]    = _safe_str(r[0])
                    existing_df.at[idx, "Description"]        = _safe_str(r[2])
                    existing_df.at[idx, "Tool ID/Drawing No"] = _safe_str(r[3])
                    existing_df.at[idx, "Location"]           = _safe_str(r[4])
                    existing_df.at[idx, "Master LIN"]         = _safe_str(r[5])
                    existing_df.at[idx, "Monthly PM"]         = _fmt_bool(r[6])
                    existing_df.at[idx, "Six Month PM"]       = _fmt_bool(r[7])
                    existing_df.at[idx, "Annual PM"]          = _fmt_bool(r[8])
                    existing_df.at[idx, "Last Monthly PM"]    = _fmt_date(r[9])
                    existing_df.at[idx, "Last Six Month PM"]  = _fmt_date(r[10])
                    existing_df.at[idx, "Last Annual PM"]     = _fmt_date(r[11])
                    existing_df.at[idx, "Next Monthly PM"]    = _fmt_date(r[12])
                    existing_df.at[idx, "Next Six Month PM"]  = _fmt_date(r[13])
                    existing_df.at[idx, "Next Annual PM"]     = _fmt_date(r[14])
                    existing_df.at[idx, "Status"]             = _safe_str(r[15]) or "Active"

            # Append records added via the app that aren't yet in the CSV
            existing_bfm = set(existing_df["BFM Equipment No"].str.strip().tolist())
            next_id = int(existing_df["ID"].max()) + 1 if "ID" in existing_df.columns else len(existing_df) + 1
            new_rows = []
            for bfm_no, r in db_by_bfm.items():
                if bfm_no not in existing_bfm:
                    new_rows.append({
                        "ID":                next_id,
                        "SAP Material No":   _safe_str(r[0]),
                        "BFM Equipment No":  bfm_no,
                        "Description":       _safe_str(r[2]),
                        "Tool ID/Drawing No":_safe_str(r[3]),
                        "Location":          _safe_str(r[4]),
                        "Master LIN":        _safe_str(r[5]),
                        "Monthly PM":        _fmt_bool(r[6]),
                        "Six Month PM":      _fmt_bool(r[7]),
                        "Annual PM":         _fmt_bool(r[8]),
                        "Last Monthly PM":   _fmt_date(r[9]),
                        "Last Six Month PM": _fmt_date(r[10]),
                        "Last Annual PM":    _fmt_date(r[11]),
                        "Next Monthly PM":   _fmt_date(r[12]),
                        "Next Six Month PM": _fmt_date(r[13]),
                        "Next Annual PM":    _fmt_date(r[14]),
                        "Status":            _safe_str(r[15]) or "Active",
                    })
                    next_id += 1
            if new_rows:
                existing_df = pd.concat([existing_df, pd.DataFrame(new_rows)], ignore_index=True)

            output_df = existing_df
        else:
            # Build fresh CSV from DB data
            output_rows = []
            for i, (bfm_no, r) in enumerate(db_by_bfm.items(), 1):
                output_rows.append({
                    "ID":                i,
                    "SAP Material No":   _safe_str(r[0]),
                    "BFM Equipment No":  bfm_no,
                    "Description":       _safe_str(r[2]),
                    "Tool ID/Drawing No":_safe_str(r[3]),
                    "Location":          _safe_str(r[4]),
                    "Master LIN":        _safe_str(r[5]),
                    "Monthly PM":        _fmt_bool(r[6]),
                    "Six Month PM":      _fmt_bool(r[7]),
                    "Annual PM":         _fmt_bool(r[8]),
                    "Last Monthly PM":   _fmt_date(r[9]),
                    "Last Six Month PM": _fmt_date(r[10]),
                    "Last Annual PM":    _fmt_date(r[11]),
                    "Next Monthly PM":   _fmt_date(r[12]),
                    "Next Six Month PM": _fmt_date(r[13]),
                    "Next Annual PM":    _fmt_date(r[14]),
                    "Status":            _safe_str(r[15]) or "Active",
                })
            output_df = pd.DataFrame(output_rows)

        # Backup original before overwriting
        if self.path.exists():
            backup = self.path.with_name(
                f"{self.path.stem}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )
            try:
                shutil.copy2(self.path, backup)
                print(f"[CSVManager] Backup saved → {backup.name}")
            except Exception as exc:
                print(f"[CSVManager] WARNING: backup failed: {exc}")

        try:
            output_df.to_csv(self.path, index=False, encoding="utf-8-sig")
            msg = f"CSV export complete ({len(output_df)} records) → {self.path.name}"
            print(f"[CSVManager] {msg}")
            if status_cb:
                status_cb(msg)
            return True
        except Exception as exc:
            print(f"[CSVManager] ERROR writing CSV: {exc}")
            return False

    # ── Per-completion update ─────────────────────────────────────────────────

    def update_equipment_pm_dates(self, bfm_no: str, pm_type: str, completion_date: str) -> bool:
        """
        Update Last/Next PM date columns in the CSV for one equipment record.
        Called immediately after a PM completion is saved to the database.
        pm_type must be one of: 'Monthly', 'Six Month', 'Annual'
        """
        if pm_type not in _PM_INTERVALS:
            return False
        if not self.path.exists():
            return False

        try:
            df = pd.read_csv(self.path, encoding="utf-8-sig", dtype=str)
            df.columns = df.columns.str.strip()
            mask = df["BFM Equipment No"].str.strip() == bfm_no
            if not mask.any():
                return False

            last_col, next_col, days = _PM_INTERVALS[pm_type]
            comp_dt = datetime.strptime(completion_date[:10], "%Y-%m-%d")
            next_dt = comp_dt + timedelta(days=days)

            df.loc[mask, last_col] = comp_dt.strftime("%Y-%m-%d")
            df.loc[mask, next_col] = next_dt.strftime("%Y-%m-%d")
            df.to_csv(self.path, index=False, encoding="utf-8-sig")
            return True
        except Exception as exc:
            print(f"[CSVManager] ERROR updating PM dates for {bfm_no}: {exc}")
            return False
