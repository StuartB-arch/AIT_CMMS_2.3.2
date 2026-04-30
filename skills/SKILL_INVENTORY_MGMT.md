# Skill: Inventory Management Module

## When to Use
- Track physical items with quantities (parts, tools, supplies, consumables)
- Min/max stock level alerting
- Supplier and location tracking
- Usage tracking against work orders
- Import/export with CSV or Excel

## Core Schema

```sql
CREATE TABLE inventory_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_number TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT,
    -- Stock levels
    quantity_on_hand REAL DEFAULT 0,
    unit_of_measure TEXT DEFAULT 'Each',
    minimum_quantity REAL DEFAULT 0,
    maximum_quantity REAL,
    reorder_point REAL,
    reorder_quantity REAL,
    -- Costs
    unit_cost REAL DEFAULT 0,
    -- Sourcing
    supplier TEXT,
    supplier_part_number TEXT,
    manufacturer TEXT,
    manufacturer_part_number TEXT,
    -- Storage
    location TEXT,
    bin TEXT,
    -- Photos
    photo_1 BLOB,
    photo_2 BLOB,
    -- Metadata
    notes TEXT,
    status TEXT DEFAULT 'Active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX idx_inventory_category ON inventory_items(category);
CREATE INDEX idx_inventory_status ON inventory_items(status);

-- Track every stock movement
CREATE TABLE stock_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    part_number TEXT REFERENCES inventory_items(part_number),
    transaction_type TEXT NOT NULL,   -- RECEIPT / ISSUE / ADJUSTMENT / RETURN / TRANSFER
    quantity_change REAL NOT NULL,     -- Positive = in, negative = out
    quantity_after REAL NOT NULL,      -- Stock level after transaction
    reference_type TEXT,               -- WO / PO / MANUAL / AUDIT
    reference_number TEXT,             -- Work order number, PO number, etc.
    notes TEXT,
    performed_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_stock_tx_part ON stock_transactions(part_number);
CREATE INDEX idx_stock_tx_date ON stock_transactions(created_at);
```

## InventoryManager Class

```python
# modules/inventory_manager.py
import json
import csv
from datetime import datetime
from io import StringIO
from typing import Optional
from dataclasses import dataclass

@dataclass
class StockAlert:
    part_number: str
    name: str
    quantity_on_hand: float
    minimum_quantity: float
    shortage: float

class InventoryManager:
    def __init__(self, db, audit=None):
        self.db = db
        self.audit = audit

    # --- CRUD ---

    def get_item(self, part_number: str) -> dict | None:
        row = self.db.fetchone(
            "SELECT * FROM inventory_items WHERE part_number = ?",
            (part_number,)
        )
        return dict(row) if row else None

    def search(self, query: str, category: str = None) -> list[dict]:
        conditions = [
            "(part_number LIKE ? OR name LIKE ? OR description LIKE ? OR supplier LIKE ?)"
        ]
        params = [f"%{query}%"] * 4

        if category:
            conditions.append("category = ?")
            params.append(category)

        where = ' AND '.join(conditions)
        rows = self.db.fetchall(
            f"SELECT * FROM inventory_items WHERE {where} AND status = 'Active' ORDER BY name",
            tuple(params)
        )
        return [dict(r) for r in rows]

    def create_item(self, data: dict) -> dict:
        data['created_at'] = datetime.now().isoformat()
        data['updated_at'] = datetime.now().isoformat()
        cols = ', '.join(data.keys())
        placeholders = ', '.join(['?'] * len(data))
        with self.db.get_cursor() as cursor:
            cursor.execute(
                f"INSERT INTO inventory_items ({cols}) VALUES ({placeholders})",
                tuple(data.values())
            )
        if self.audit:
            self.audit.log_insert('inventory_items', data['part_number'], data)
        return self.get_item(data['part_number'])

    def update_item(self, part_number: str, data: dict) -> bool:
        old = self.get_item(part_number)
        data['updated_at'] = datetime.now().isoformat()
        set_clause = ', '.join([f"{k} = ?" for k in data.keys()])
        params = tuple(data.values()) + (part_number,)
        with self.db.get_cursor() as cursor:
            cursor.execute(
                f"UPDATE inventory_items SET {set_clause} WHERE part_number = ?",
                params
            )
            changed = cursor.rowcount > 0
        if changed and self.audit and old:
            self.audit.log_update('inventory_items', part_number, old, {**old, **data})
        return changed

    def delete_item(self, part_number: str, reason: str = None) -> bool:
        old = self.get_item(part_number)
        result = self.update_item(part_number, {'status': 'Inactive'})
        if result and self.audit:
            self.audit.log('DELETE', 'inventory_items', part_number,
                           old_values=old, notes=f"Deactivated: {reason}")
        return result

    # --- Stock Movements ---

    def adjust_stock(
        self,
        part_number: str,
        quantity_change: float,
        transaction_type: str,
        reference_number: str = None,
        notes: str = None,
        performed_by: str = None
    ) -> dict:
        """
        quantity_change: positive = receiving stock, negative = consuming stock
        """
        item = self.get_item(part_number)
        if not item:
            raise ValueError(f"Part {part_number} not found")

        new_quantity = item['quantity_on_hand'] + quantity_change
        if new_quantity < 0:
            raise ValueError(
                f"Insufficient stock. Have {item['quantity_on_hand']}, "
                f"need {abs(quantity_change)}"
            )

        # Update stock level
        self.update_item(part_number, {'quantity_on_hand': new_quantity})

        # Record transaction
        with self.db.get_cursor() as cursor:
            cursor.execute("""
                INSERT INTO stock_transactions
                    (part_number, transaction_type, quantity_change, quantity_after,
                     reference_number, notes, performed_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                part_number, transaction_type, quantity_change, new_quantity,
                reference_number, notes, performed_by,
                datetime.now().isoformat()
            ))

        return self.get_item(part_number)

    def receive_stock(self, part_number: str, quantity: float, po_number: str = None,
                      notes: str = None, by: str = None) -> dict:
        return self.adjust_stock(part_number, abs(quantity), 'RECEIPT',
                                  po_number, notes, by)

    def issue_stock(self, part_number: str, quantity: float, wo_number: str = None,
                    notes: str = None, by: str = None) -> dict:
        return self.adjust_stock(part_number, -abs(quantity), 'ISSUE',
                                  wo_number, notes, by)

    def manual_adjustment(self, part_number: str, new_quantity: float,
                           reason: str, by: str = None) -> dict:
        item = self.get_item(part_number)
        delta = new_quantity - item['quantity_on_hand']
        return self.adjust_stock(part_number, delta, 'ADJUSTMENT',
                                  notes=reason, performed_by=by)

    # --- Alerts ---

    def get_low_stock_items(self) -> list[StockAlert]:
        rows = self.db.fetchall("""
            SELECT part_number, name, quantity_on_hand, minimum_quantity
            FROM inventory_items
            WHERE status = 'Active'
            AND quantity_on_hand <= minimum_quantity
            AND minimum_quantity > 0
            ORDER BY (quantity_on_hand - minimum_quantity) ASC
        """)
        return [
            StockAlert(
                part_number=r['part_number'],
                name=r['name'],
                quantity_on_hand=r['quantity_on_hand'],
                minimum_quantity=r['minimum_quantity'],
                shortage=r['minimum_quantity'] - r['quantity_on_hand'],
            )
            for r in rows
        ]

    def get_out_of_stock(self) -> list[dict]:
        return [dict(r) for r in self.db.fetchall(
            "SELECT * FROM inventory_items WHERE status='Active' AND quantity_on_hand <= 0"
        )]

    # --- Transaction History ---

    def get_transaction_history(self, part_number: str, limit: int = 50) -> list[dict]:
        rows = self.db.fetchall("""
            SELECT * FROM stock_transactions
            WHERE part_number = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (part_number, limit))
        return [dict(r) for r in rows]

    # --- CSV Import/Export ---

    def export_csv(self) -> str:
        rows = self.db.fetchall(
            "SELECT part_number, name, description, category, quantity_on_hand, "
            "unit_of_measure, minimum_quantity, unit_cost, supplier, location, bin "
            "FROM inventory_items WHERE status = 'Active' ORDER BY name"
        )
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Part Number', 'Name', 'Description', 'Category',
            'Qty On Hand', 'Unit', 'Min Qty', 'Unit Cost', 'Supplier', 'Location', 'Bin'
        ])
        for row in rows:
            writer.writerow(list(row))
        return output.getvalue()

    def import_csv(self, filepath: str) -> dict:
        results = {'created': 0, 'updated': 0, 'errors': []}
        with open(filepath, 'r', newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader, 2):
                try:
                    pn = row.get('Part Number', '').strip()
                    if not pn:
                        continue
                    data = {
                        'part_number': pn,
                        'name': row.get('Name', '').strip(),
                        'description': row.get('Description', '').strip(),
                        'category': row.get('Category', '').strip(),
                        'quantity_on_hand': float(row.get('Qty On Hand', 0) or 0),
                        'unit_of_measure': row.get('Unit', 'Each').strip(),
                        'minimum_quantity': float(row.get('Min Qty', 0) or 0),
                        'unit_cost': float(row.get('Unit Cost', 0) or 0),
                        'supplier': row.get('Supplier', '').strip(),
                        'location': row.get('Location', '').strip(),
                        'bin': row.get('Bin', '').strip(),
                    }
                    if self.get_item(pn):
                        self.update_item(pn, data)
                        results['updated'] += 1
                    else:
                        self.create_item(data)
                        results['created'] += 1
                except Exception as e:
                    results['errors'].append(f"Row {i}: {e}")
        return results

    # --- Statistics ---

    def get_inventory_value(self) -> float:
        row = self.db.fetchone(
            "SELECT SUM(quantity_on_hand * unit_cost) as total FROM inventory_items WHERE status='Active'"
        )
        return row['total'] or 0.0

    def get_category_breakdown(self) -> list[dict]:
        rows = self.db.fetchall("""
            SELECT category, COUNT(*) as item_count,
                   SUM(quantity_on_hand * unit_cost) as total_value
            FROM inventory_items WHERE status = 'Active'
            GROUP BY category ORDER BY total_value DESC
        """)
        return [dict(r) for r in rows]
```

## Stock Level Color Coding (Tkinter)

```python
def get_stock_color(quantity: float, minimum: float) -> str:
    if quantity <= 0:
        return '#FFCCCC'   # Red — out of stock
    elif quantity <= minimum:
        return '#FFE0B2'   # Orange — at or below minimum
    elif quantity <= minimum * 1.5:
        return '#FFF9C4'   # Yellow — getting low
    else:
        return '#C8E6C9'   # Green — adequate

# In TreeView:
for item in inventory_items:
    color = get_stock_color(item['quantity_on_hand'], item['minimum_quantity'])
    row_id = tree.insert('', 'end', values=(...))
    tree.item(row_id, tags=(color,))

tree.tag_configure('#FFCCCC', background='#FFCCCC')
tree.tag_configure('#FFE0B2', background='#FFE0B2')
tree.tag_configure('#FFF9C4', background='#FFF9C4')
tree.tag_configure('#C8E6C9', background='#C8E6C9')
```

## Best Practices

1. **Every stock change = a transaction record** — Never just UPDATE quantity without logging the transaction.
2. **Negative stock prevention** — Validate before issuing. Raise an error, never go negative.
3. **quantity_after on every transaction** — Enables reconstruction of stock history without re-summing.
4. **Unit of measure** — Always store it. "5" means nothing without "5 gallons" or "5 each."
5. **Min/max vs. reorder point** — Minimum = alert threshold. Reorder point = when to order. Maximum = don't over-order.
6. **Audit every adjustment** — Stock adjustments are high-fraud-risk operations.
7. **Photo storage** — Store as BLOB in DB to avoid broken file path references.
8. **CSV export always** — Users will always want Excel. Build it in from day one.
