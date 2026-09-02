---
title: Excel Account Renamer
emoji: 📊
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
---

# Excel Account Renamer
Upload Excel/CSV files, get them renamed by account number + location, download as one ZIP.


# Desktop build — quick start

## 1. Setup (one time)
```
pip install -r requirements-desktop.txt
```

## 2. Adjust the import in desktop.py
Open `desktop.py` and check this line:
```python
from app import demo
```
- `app` must match your actual Python filename (e.g. if your file is `main.py`, use `from main import demo`).
- `demo` must match the variable name of your `gr.Blocks(...)` / `gr.Interface(...)` object.

If your Gradio object is built inside a function instead of at module level (e.g. `def build_ui(): ... return demo`), tell me and I'll adjust `desktop.py` to call that function instead of importing a bare variable.

## 3. Run it as a desktop app
```
python desktop.py
```
A native window should open showing your existing UI, with no browser tabs/URL bar.

## 4. Package into a standalone .exe / app
```
pyinstaller --onefile --windowed --name AccountRenamer desktop.py
```
The built executable will be in `dist/AccountRenamer.exe` (Windows) or `dist/AccountRenamer` (Mac/Linux app bundle equivalent).

If your app reads any local files at runtime (icons, templates, sample data), add them with `--add-data`, e.g.:
```
pyinstaller --onefile --windowed --add-data "assets;assets" --name AccountRenamer desktop.py
```
(On Mac/Linux use `:` instead of `;` in `--add-data`.)

## Notes
- Your Render deployment and `requirements.txt` are unaffected — this build only adds `desktop.py` and `requirements-desktop.txt` alongside your existing files.
- `desktop.py` auto-picks a free local port starting at 7860, so it won't clash with anything else running on the machine.