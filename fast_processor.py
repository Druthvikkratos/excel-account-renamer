import io, os, re
from openpyxl import load_workbook

PATTERN = re.compile(r"Account No\s*-\s*(\d+)")
MAX_ROWS = 30  # raise if the header can sit lower

def _find_account(ext, bio):
    if ext == ".csv":
        text = bio.read(20000).decode("utf-8", errors="ignore")
        m = PATTERN.search(text)
        return m.group(1) if m else None

    if ext == ".xlsx":
        wb = load_workbook(bio, read_only=True, data_only=True)
        ws = wb.active
        for row in ws.iter_rows(min_row=1, max_row=MAX_ROWS, values_only=True):
            for cell in row:
                if isinstance(cell, str):
                    m = PATTERN.search(cell)
                    if m:
                        wb.close()
                        return m.group(1)
        wb.close()
        return None

    # .xls / .xlsb: fall back to pandas, but only the top rows
    import pandas as pd
    engine = "pyxlsb" if ext == ".xlsb" else None
    df = pd.read_excel(bio, header=None, nrows=MAX_ROWS, engine=engine)
    for v in df.to_numpy().ravel():
        if isinstance(v, str):
            m = PATTERN.search(v)
            if m:
                return m.group(1)
    return None