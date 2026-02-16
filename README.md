# YouTube Bad Ad Guard (Desktop Mode)

This script now watches your **whole screen** while you use YouTube in your normal browser.

Behavior:
- If explicit content is detected in the **center area** (likely main video/content), it sends **Ctrl+W** to close the current tab.
- If explicit content is detected **outside the center area** (likely sidebar/recommendation/ad area), it sends **Ctrl+R** to refresh.
- Optional rabbit test mode can send **Ctrl+W** when a rabbit is detected.

## File
- `youtube_bad_ad_guard.py`

## Install
```bash
pip install selenium nudenet pillow transformers torch mss pyautogui pygetwindow
```

## Run
```bash
python youtube_bad_ad_guard.py
```

Then just browse/watch YouTube normally in your browser window.

## Rabbit test mode
```bash
python youtube_bad_ad_guard.py --rabbit-test-mode --rabbit-threshold 0.45
```

## Helpful options
```bash
python youtube_bad_ad_guard.py \
  --threshold 0.60 \
  --scan-interval 2 \
  --refresh-cooldown 15 \
  --close-cooldown 5 \
  --center-ratio 0.55
```

## Notes
- This is best-effort detection and can produce false positives/false negatives.
- Keep your browser focused so hotkeys apply to that tab/window.
- On some systems, screen capture/hotkeys may need accessibility permissions.
- Rabbit mode is for testing and can be turned off by removing `--rabbit-test-mode`.
