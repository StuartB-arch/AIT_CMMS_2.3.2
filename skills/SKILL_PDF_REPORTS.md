# Skill: PDF Report Generation with ReportLab

## When to Use
- Generate work order forms, completion records, compliance reports
- Professional PDF output needed (not just print-to-PDF)
- Need headers, footers, tables, logos, signatures
- Python desktop app — no browser or server available

## Installation

```bash
pip install reportlab
```

## Quick Reference

```python
from reportlab.lib.pagesizes import LETTER, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle,
    Spacer, HRFlowable, Image
)
from reportlab.platypus.flowables import PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from io import BytesIO
```

## Complete PM Completion Form Example

```python
# utils/pdf_generator.py
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle,
    Spacer, HRFlowable, Image
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO
from datetime import datetime
from pathlib import Path


def generate_pm_completion_pdf(data: dict) -> bytes:
    """
    data = {
        'equipment_id': 'EQ-001',
        'equipment_name': 'Hydraulic Pump Unit A',
        'location': 'Bay 3 - North',
        'pm_type': 'Annual',
        'technician': 'John Smith',
        'completion_date': '2026-04-30',
        'labor_hours': 2.5,
        'notes': 'Replaced filter. All checks nominal.',
        'checklist': [
            {'item': 'Inspect fluid level', 'completed': True},
            {'item': 'Check for leaks', 'completed': True},
            {'item': 'Replace filter', 'completed': True},
        ],
        'logo_path': 'assets/logo.png',  # Optional
    }
    """
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    story = []

    # --- Title block ---
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Normal'],
        fontSize=16,
        fontName='Helvetica-Bold',
        alignment=TA_CENTER,
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=11,
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    label_style = ParagraphStyle(
        'Label',
        parent=styles['Normal'],
        fontSize=9,
        fontName='Helvetica-Bold',
    )
    value_style = ParagraphStyle(
        'Value',
        parent=styles['Normal'],
        fontSize=9,
    )

    # Logo (if provided)
    logo_path = data.get('logo_path')
    if logo_path and Path(logo_path).exists():
        logo = Image(logo_path, width=1.5 * inch, height=0.6 * inch)
        logo.hAlign = 'CENTER'
        story.append(logo)
        story.append(Spacer(1, 6))

    story.append(Paragraph("PREVENTIVE MAINTENANCE COMPLETION RECORD", title_style))
    story.append(Paragraph(f"{data['pm_type']} PM — {data['completion_date']}", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.darkblue))
    story.append(Spacer(1, 12))

    # --- Equipment Details table ---
    details = [
        ['Equipment ID:', data.get('equipment_id', ''), 'PM Type:', data.get('pm_type', '')],
        ['Equipment Name:', data.get('equipment_name', ''), 'Location:', data.get('location', '')],
        ['Technician:', data.get('technician', ''), 'Date Completed:', data.get('completion_date', '')],
        ['Labor Hours:', str(data.get('labor_hours', '')), 'Due Date:', data.get('pm_due_date', 'N/A')],
    ]

    detail_table = Table(
        details,
        colWidths=[1.3 * inch, 2.4 * inch, 1.3 * inch, 2.4 * inch]
    )
    detail_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#E8EAF6')),
        ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#E8EAF6')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(detail_table)
    story.append(Spacer(1, 16))

    # --- Checklist ---
    if data.get('checklist'):
        story.append(Paragraph("MAINTENANCE CHECKLIST", styles['Heading3']))
        story.append(Spacer(1, 6))

        checklist_data = [['#', 'Task / Check Item', 'Completed']]
        for i, item in enumerate(data['checklist'], 1):
            status = '✓' if item.get('completed') else '✗'
            color = 'green' if item.get('completed') else 'red'
            checklist_data.append([
                str(i),
                item['item'],
                Paragraph(f'<font color="{color}">{status}</font>', value_style)
            ])

        checklist_table = Table(
            checklist_data,
            colWidths=[0.4 * inch, 6.0 * inch, 0.8 * inch]
        )
        checklist_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F5F5F5')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (2, 0), (2, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(checklist_table)
        story.append(Spacer(1, 16))

    # --- Notes ---
    if data.get('notes'):
        story.append(Paragraph("NOTES", styles['Heading3']))
        story.append(Spacer(1, 4))
        notes_table = Table(
            [[data['notes']]],
            colWidths=[7.2 * inch]
        )
        notes_table.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(notes_table)
        story.append(Spacer(1, 20))

    # --- Signature lines ---
    sig_data = [
        ['Technician Signature:', '_' * 30, 'Date:', '_' * 15],
        ['Supervisor Signature:', '_' * 30, 'Date:', '_' * 15],
    ]
    sig_table = Table(sig_data, colWidths=[1.5 * inch, 3.0 * inch, 0.6 * inch, 2.3 * inch])
    sig_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(sig_table)

    # --- Footer ---
    def add_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.grey)
        footer_text = (
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
            f"Page {doc.page}  |  CONFIDENTIAL — MAINTENANCE RECORD"
        )
        canvas.drawCentredString(LETTER[0] / 2, 0.5 * inch, footer_text)
        canvas.restoreState()

    doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
    return buffer.getvalue()
```

## Summary Report (Multi-Page Table)

```python
def generate_pm_summary_report(month: str, records: list[dict]) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"PM Summary Report — {month}", styles['Title']))
    story.append(Spacer(1, 12))

    # Stats block
    total = len(records)
    completed = sum(1 for r in records if r['status'] == 'Completed')
    story.append(Paragraph(
        f"Total Scheduled: {total}  |  Completed: {completed}  |  "
        f"Compliance: {completed/total*100:.1f}%" if total else "No records",
        styles['Normal']
    ))
    story.append(Spacer(1, 12))

    # Data table
    headers = ['Equipment ID', 'Description', 'PM Type', 'Assigned To', 'Status', 'Completed']
    table_data = [headers] + [
        [r.get('asset_id', ''), r.get('description', '')[:40],
         r.get('pm_type', ''), r.get('assigned_to', ''),
         r.get('status', ''), r.get('completed_date', '')]
        for r in records
    ]

    table = Table(table_data, repeatRows=1)  # repeatRows=1 repeats header on each page
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F0F0F0')]),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(table)

    doc.build(story)
    return buffer.getvalue()
```

## Save and Open PDF

```python
import os
import tempfile
import subprocess
import platform

def save_and_open_pdf(pdf_bytes: bytes, filename: str = "report.pdf"):
    """Save PDF to temp file and open with default viewer."""
    temp_dir = tempfile.gettempdir()
    path = os.path.join(temp_dir, filename)

    with open(path, 'wb') as f:
        f.write(pdf_bytes)

    if platform.system() == 'Windows':
        os.startfile(path)
    elif platform.system() == 'Darwin':
        subprocess.run(['open', path])
    else:
        subprocess.run(['xdg-open', path])

    return path
```

## Common TableStyle Commands Reference

```python
TableStyle([
    # Background colors
    ('BACKGROUND', (col_start, row_start), (col_end, row_end), colors.navy),
    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),

    # Text
    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ('FONTSIZE', (0, 0), (-1, -1), 9),
    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),   # LEFT / CENTER / RIGHT
    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),   # TOP / MIDDLE / BOTTOM

    # Borders
    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
    ('BOX', (0, 0), (-1, -1), 1, colors.black),
    ('LINEBELOW', (0, 0), (-1, 0), 2, colors.darkblue),  # Thick header bottom border

    # Padding
    ('TOPPADDING', (0, 0), (-1, -1), 6),
    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ('RIGHTPADDING', (0, 0), (-1, -1), 8),

    # Span cells
    ('SPAN', (0, 0), (3, 0)),   # Merge columns 0-3 on row 0
])
```
