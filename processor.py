import io
import os
import re
import pandas as pd
from location_map import account_location_map


def process_file(filename: str, file_bytes: bytes):
    """
    Same detection logic as your original main.py, but works fully
    in-memory (BytesIO) instead of reading/moving files on disk.

    Returns: (status, new_filename, output_bytes, error_message)
      status is "success" or "failed"
    """
    ext = os.path.splitext(filename)[1].lower()

    try:
        bio = io.BytesIO(file_bytes)

        if ext in (".xlsx", ".xls"):
            df = pd.read_excel(bio, header=None)
        elif ext == ".xlsb":
            df = pd.read_excel(bio, header=None, engine="pyxlsb")
        elif ext == ".csv":
            bio.seek(0)
            df = pd.read_csv(bio, header=None)
        else:
            return "failed", filename, file_bytes, f"Unsupported file type: {ext}"

        account_number = None

        for i in range(df.shape[0]):
            for j in range(df.shape[1]):
                cell = df.iat[i, j]
                if isinstance(cell, str) and "Statement of Account No" in cell:
                    match = re.search(r"Account No\s*-\s*(\d+)", cell)
                    if match:
                        account_number = match.group(1)
                        break
            if account_number:
                break

        if account_number:
            location = account_location_map.get(account_number)
            new_filename = (
                f"{account_number}_{location}{ext}"
                if location
                else f"{account_number}{ext}"
            )
            return "success", new_filename, file_bytes, None
        else:
            return "failed", filename, file_bytes, "Account number not found in file"

    except Exception as e:
        return "failed", filename, file_bytes, str(e)