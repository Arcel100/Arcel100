# Screen Guard (prototype)

`screen_guard.py` monitors your screen and refreshes your browser tab only when content looks **inappropriate/intrusive**.

## Windows 11 quick start (recommended)

1. Install Python 3.10+.
2. Open PowerShell in this project folder.
3. Run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

4. Install Tesseract OCR for Windows (required by `pytesseract`):
   - Download installer from: https://github.com/UB-Mannheim/tesseract/wiki
   - During install, keep default path (usually `C:\Program Files\Tesseract-OCR`).

5. If needed, set PATH in PowerShell for current session:

```powershell
$env:Path += ";C:\Program Files\Tesseract-OCR"
```

## Run (safe first)

```powershell
python screen_guard.py --dry-run --interval 3 --threshold 1.4 --debug-dir .\debug_captures
```

## Then enable real refresh

```powershell
python screen_guard.py --interval 3 --threshold 1.4 --min-consecutive-hits 3 --cooldown-seconds 20
```

On Windows, refresh is sent with native key events (`Ctrl+R`) and does not require `xdotool`.

## Useful options

```powershell
# OCR-only fallback (no CLIP model)
python screen_guard.py --dry-run --no-ai
```

## What counts as inappropriate/intrusive

- Adult/explicit visual content.
- Intrusive popup-style ad visuals.
- OCR text terms such as `xxx`, `porn`, `casino`, `bet now`, `free spins`, `virus detected`, `you won`.

Normal non-intrusive ads should trigger much less often with these defaults.

## Notes

- Keep your browser window focused so refresh is sent to the correct app.
- This is still heuristic, so false positives/negatives can happen.
- Linux/macOS are still supported (Linux uses `xdotool`, macOS uses `osascript`).
