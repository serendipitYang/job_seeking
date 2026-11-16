"""Local application state with an atomic XLSX export on each checkbox change.

The workbook is the commit point; unrelated columns and worksheets are preserved.
"""
import fcntl
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HEADERS = ['Job ID', 'Company', 'Job title', 'Location', 'Job URL', 'Match score',
           'Application deadline', 'Applied', 'First marked applied (UTC)', 'Last updated (UTC)']


def settings(base, config):
    cfg = config.get('applications', {})
    path = (base / cfg.get('workbook', 'applications.xlsx')).resolve()
    if path.suffix.lower() != '.xlsx':
        raise ValueError('Application workbook must be .xlsx')
    return path, cfg.get('sheet', 'Applications')


def read_records(base, config):
    from openpyxl import load_workbook
    path, sheet = settings(base, config)
    if not path.exists():
        return {}
    wb = load_workbook(path)
    try:
        if sheet not in wb.sheetnames:
            return {}
        ws = wb[sheet]
        if [c.value for c in ws[1]][:len(HEADERS)] != HEADERS:
            raise ValueError('Application sheet headers differ; choose a new sheet name to preserve existing data')
        return {str(row[0]): {'applied': row[7] is True, 'applied_at': row[8], 'updated_at': row[9]}
                for row in ws.iter_rows(min_row=2, max_col=len(HEADERS), values_only=True) if row[0]}
    finally:
        wb.close()


def mark_applied(base, config, job, applied):
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    if type(applied) is not bool:
        raise ValueError('applied must be a boolean')
    path, sheet = settings(base, config)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.xlsx.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (path.parent / ('~$' + path.name)).exists():
            raise ValueError('Close this workbook in Excel before saving an application')
        wb = load_workbook(path) if path.exists() else Workbook()
        if not path.exists():
            wb.active.title = sheet
        ws = wb[sheet] if sheet in wb.sheetnames else wb.create_sheet(sheet)
        if ws.cell(1, 1).value is None and ws.max_row == 1:
            for col, title in enumerate(HEADERS, 1):
                ws.cell(1, col, title)
            ws.freeze_panes = 'C2'
            for col, width in enumerate([28, 22, 60, 36, 65, 14, 23, 13, 29, 26], 1):
                ws.column_dimensions[get_column_letter(col)].width = width
                ws.cell(1, col).font = Font(bold=True, color='FFFFFF')
                ws.cell(1, col).fill = PatternFill('solid', fgColor='122D43')
        elif [c.value for c in ws[1]][:len(HEADERS)] != HEADERS:
            wb.close()
            raise ValueError('Application sheet headers differ; choose a new sheet name')
        row = next((r for r in range(2, ws.max_row + 1) if ws.cell(r, 1).value == job['id']), ws.max_row + 1)
        stamp = datetime.now(timezone.utc).isoformat()
        first = ws.cell(row, 9).value or (stamp if applied else None)
        values = [job['id'], job['company'], job['title'], job.get('location'), job['url'],
                  (job.get('match') or {}).get('score'), (job.get('deadline') or {}).get('date'), applied, first, stamp]
        for col, value in enumerate(values, 1):
            cell = ws.cell(row, col)
            cell.value = value
            if isinstance(value, str):
                cell.data_type = 's'  # Never interpret employer-controlled text as Excel formulas.
            cell.alignment = Alignment(vertical='top', wrap_text=True)
        ws.cell(row, 5).hyperlink = job['url'] if job['url'].startswith('https://') else None
        ws.cell(row, 5).font = Font(color='075FCA', underline='single')
        ws.cell(row, 6).number_format = '0.0'
        ws.auto_filter.ref = f'A1:J{ws.max_row}'
        fd, tmp = tempfile.mkstemp(suffix='.xlsx', dir=str(path.parent))
        os.close(fd)
        try:
            wb.save(tmp)
            wb.close()
            os.replace(tmp, path)
        finally:
            wb.close()
            if os.path.exists(tmp):
                os.unlink(tmp)
        return {'applied': applied, 'applied_at': first, 'updated_at': stamp}
