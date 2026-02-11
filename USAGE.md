# Screen Guard (prototype)

`screen_guard.py` monitors your screen and refreshes your browser tab when likely ad/inappropriate content is detected.

## What was improved

- Better dependency errors (clear install message instead of crash on import).
- Safer refresh behavior:
  - requires consecutive hits (`--min-consecutive-hits`, default `2`)
  - enforces cooldown (`--cooldown-seconds`, default `10`)
- Optional OCR-only mode with `--no-ai`.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
# Linux system deps used by OCR + refresh hotkey
sudo apt-get install -y tesseract-ocr xdotool
```

## Run (safe first)

```bash
python screen_guard.py --dry-run --interval 3 --threshold 1.0 --debug-dir ./debug_captures
```

## Useful options

```bash
# Reduce accidental refreshes further
python screen_guard.py --dry-run --min-consecutive-hits 3 --cooldown-seconds 20

# OCR-only fallback (no CLIP model)
python screen_guard.py --dry-run --no-ai
```

## Notes

- This is still a heuristic tool, not guaranteed moderation.
- On macOS/Windows, replace Linux `xdotool` in `refresh_page()`.
