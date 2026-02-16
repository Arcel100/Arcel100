# YouTube Bad Ad Guard

Python script to monitor a YouTube page and react based on where bad content is detected:

- **Inside video player:** close the page/tab.
- **Outside video player** (side/recommended/ad thumbnails): refresh the page.

Also includes an optional **rabbit test mode**.
If rabbit is detected anywhere, it closes the page/tab (for testing behavior).

## File
- `youtube_bad_ad_guard.py`

## Install
```bash
pip install selenium nudenet pillow transformers torch
```

You also need Chrome + ChromeDriver installed and compatible.

## Run
```bash
python youtube_bad_ad_guard.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

## Rabbit test mode
```bash
python youtube_bad_ad_guard.py "https://www.youtube.com/watch?v=VIDEO_ID" \
  --rabbit-test-mode \
  --rabbit-threshold 0.45
```

## Helpful options
```bash
python youtube_bad_ad_guard.py "https://www.youtube.com/watch?v=VIDEO_ID" \
  --threshold 0.60 \
  --scan-interval 5 \
  --refresh-cooldown 20 \
  --max-inside-images 2 \
  --max-outside-images 8
```

## Notes
- This is best-effort detection and can produce false positives/false negatives.
- Keep your own YouTube SafeSearch / restricted settings enabled too.
- Rabbit mode is for testing and can be turned off by removing `--rabbit-test-mode`.
