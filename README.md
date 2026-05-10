def scan_pdf_fields(param):
    passw-level editing of AcroForm fields in PDF files.
It allows you to inspect and manipulate field properties (`/Rect`, `/P`) directly via pikepdf, without re-rendering the document.

## Features

- Open a PDF and view all form fields in a table
- For each field, display: name, physical page, `/P` page reference, `/Rect` coordinates, and object id
- Field editing actions:
  - **Clear /Rect** — replace coordinates with an empty array `[]`
  - **Delete /Rect** — fully remove the `/Rect` key
  - **Set /Rect** — set new coordinates `[left, bottom, right, top]`
  - **Delete /P** — remove the page binding
  - **Set /P** — bind the field to a valid or intentionally invalid page
- Undo last action
- Save As — write the modified PDF to a new file
- DEBUG mode: dump full information about every field via PyMuPDF
- Log panel with search (`Ctrl+F` / `Cmd+F`)

## Project structure

```
Edit_PDF_Fields/
├── Edit_PDF_fields.py   # Main GUI application
├── check.py             # CLI utility: scan fields and print a status table
├── test.py              # CLI utility: set field coordinates from a script
├── main.py              # Entry-point stub
├── pyproject.toml       # Project configuration (uv)
└── uv.lock              # Dependency lock file
```

## Requirements

- **Python 3.11 or newer**
- [uv](https://docs.astral.sh/uv/) — Python package and project manager
- Tkinter (bundled with the official Python distribution; required for the GUI)

## Installing Python

### macOS

The recommended way is to let `uv` install the correct Python version automatically:

```bash
uv python install 3.11
```

Alternatively, install via Homebrew:

```bash
brew install python@3.11
```

> The Python shipped with the OS is not recommended — it may lack Tkinter or be too old.

### Windows

Download the official installer from [python.org](https://www.python.org/downloads/) (3.11 or newer).
During installation, make sure the following options are enabled:

- **Add Python to PATH**
- **tcl/tk and IDLE** (required for the Tkinter GUI)

Or use `uv`:

```powershell
uv python install 3.11
```

### Linux (Debian/Ubuntu)

```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3-tk
```

For other distributions install the equivalent `python3.11` and `python3-tk` packages.

## Installing uv

### macOS / Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Windows (PowerShell)

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Verify the installation:

```bash
uv --version
```

## Project setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd Edit_PDF_Fields
```

### 2. Create the virtual environment and sync dependencies

```bash
uv sync
```

`uv` will read `pyproject.toml` / `uv.lock` and create a `.venv/` automatically.

### 3. Add PDF libraries

The project does not pin runtime PDF dependencies yet, so add them once:

```bash
uv add pymupdf pikepdf
```

### 4. Run the GUI

```bash
uv run python Edit_PDF_fields.py
```

## Using the GUI

1. Click **Open PDF** and pick a file.
2. The left table will list every form widget with the columns:
   - **Field** — field name (`/T`)
   - **PhysPage** — physical page where the annotation actually lives
   - **Page (/P)** — page derived from the field's `/P` reference
   - **PageId** — object reference `objnum gennum R`
   - **Rect** — `[left, bottom, right, top]`
3. Select a field in the table, then use the buttons on the right to edit it.
4. Click **Save As…** to write the modified document to disk.

> All edits are kept in memory until **Save As…** is used. The original file is never modified.

## CLI utilities

### check.py — scan fields

Prints every top-level AcroForm field with its coordinates, page, and a status flag:

```bash
uv run python check.py
```

Status values:

- `OK` — field is visible and bound to a page
- `GHOST` — `/Rect` is missing
- `ZERO-SIZE` — coordinates are `[0, 0, 0, 0]`
- `ORPHAN` — no `/P` (not bound to a page)

Edit the bottom of the file to point at the PDF you want to scan:

```python
scan_pdf_fields("your_file.pdf")
```

### test.py — set field coordinates from a script

Moves a single field to new coordinates and binds it to a chosen page:

```bash
uv run python test.py
```

Configure the constants at the top of the file:

```python
INPUT_FILE = "input.pdf"
OUTPUT_FILE = "result.pdf"
FIELD_NAME = "FieldName"
NEW_COORDS = [100, 500, 300, 550]   # [left, bottom, right, top]
TARGET_PAGE_INDEX = 0               # 0 = first page
```

## Dependencies

| Library | Purpose |
|---------|---------|
| [PyMuPDF](https://pymupdf.readthedocs.io/) (`fitz`) | Read widgets, map page xrefs |
| [pikepdf](https://pikepdf.readthedocs.io/) | Low-level PDF object editing |
| `tkinter` | GUI (ships with the standard Python distribution) |

## Troubleshooting

- **`ModuleNotFoundError: No module named '_tkinter'`** — Tkinter is not installed for your Python. On Linux install `python3-tk`; on Windows reinstall Python with the *tcl/tk and IDLE* option enabled.
- **`uv: command not found`** — restart the terminal after installing uv, or add `~/.local/bin` to your `PATH`.
- **Window opens but no fields are listed** — the PDF likely has no AcroForm fields, or all widgets lack `/T` names. Use **DEBUG Fields** to dump raw widget info.

Good luck with your PDF field editing!