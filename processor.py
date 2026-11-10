import os
import re
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

ACCOUNT_RE = re.compile(r"Statement of Account No\s*-\s*(\d+)")
HEAD_ROWS = 30
HEAD_BYTES = 64 * 1024
SUPPORTED = (".xlsx", ".xls", ".xlsb", ".csv")


def _search_rows(rows):
    for row in rows:
        for cell in row:
            if isinstance(cell, str):
                m = ACCOUNT_RE.search(cell)
                if m:
                    return m.group(1)
    return None


def _scan(path, ext, head):
    """head=True scans only the top of the file; head=False scans everything."""
    if ext == ".csv":
        with open(path, "rb") as f:
            text = f.read(HEAD_BYTES if head else -1).decode("utf-8", errors="ignore")
        m = ACCOUNT_RE.search(text)
        return m.group(1) if m else None

    if ext == ".xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            rows = wb.active.iter_rows(
                min_row=1, max_row=HEAD_ROWS if head else None, values_only=True
            )
            return _search_rows(rows)
        finally:
            wb.close()

    # .xls / .xlsb: pandas only when needed
    import pandas as pd
    engine = "pyxlsb" if ext == ".xlsb" else None
    df = pd.read_excel(path, header=None, engine=engine,
                       nrows=HEAD_ROWS if head else None)
    return _search_rows(df.itertuples(index=False))


def process_file(filename, path, location_map):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in SUPPORTED:
        return "failed", filename, f"Unsupported file type: {ext}"
    try:
        account = _scan(path, ext, head=True) or _scan(path, ext, head=False)
        if not account:
            return "failed", filename, "Account number not found in file"
        loc = location_map.get(account)
        return "success", (f"{account}_{loc}{ext}" if loc else f"{account}{ext}"), None
    except Exception as e:
        return "failed", filename, str(e)