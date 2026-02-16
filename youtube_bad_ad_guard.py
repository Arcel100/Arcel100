#!/usr/bin/env python3
"""
Desktop Bad Content Guard

Monitors the whole screen while you browse.
If explicit content is detected:
- roughly in center area (likely main video/content): Ctrl+W to close tab
- outside center area (likely sidebar/ad/recommendations): Ctrl+R to refresh page

Optional test mode:
- Rabbit detection (CLIP zero-shot): if rabbit is detected, Ctrl+W.
"""

from __future__ import annotations

import argparse
import io
import logging
import tempfile
import time
from pathlib import Path
from typing import Iterable

from nudenet import NudeDetector
from PIL import Image

EXPLICIT_LABELS = {
    "EXPOSED_BREAST_F",
    "EXPOSED_BREAST_M",
    "EXPOSED_BUTTOCKS",
    "EXPOSED_GENITALIA_F",
    "EXPOSED_GENITALIA_M",
    "EXPOSED_ANUS",
}

BROWSER_HINTS = ("youtube", "firefox", "chrome", "edge", "opera", "brave", "safari")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor whole screen and react to bad content while browsing."
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.60,
        help="Confidence threshold for explicit labels (default: 0.60).",
    )
    parser.add_argument(
        "--scan-interval",
        type=float,
        default=2.0,
        help="Seconds between scans (default: 2).",
    )
    parser.add_argument(
        "--refresh-cooldown",
        type=float,
        default=15.0,
        help="Minimum seconds between refresh actions (default: 15).",
    )
    parser.add_argument(
        "--close-cooldown",
        type=float,
        default=5.0,
        help="Minimum seconds between Ctrl+W actions (default: 5).",
    )
    parser.add_argument(
        "--center-ratio",
        type=float,
        default=0.55,
        help="Center box ratio to treat as main video/content (default: 0.55).",
    )
    parser.add_argument(
        "--rabbit-test-mode",
        action="store_true",
        help="Enable rabbit detection test mode; rabbit found => Ctrl+W.",
    )
    parser.add_argument(
        "--rabbit-threshold",
        type=float,
        default=0.45,
        help="Rabbit detection threshold in test mode (default: 0.45).",
    )
    return parser.parse_args()


def load_automation_modules() -> tuple[object, object]:
    try:
        import mss
        import pyautogui
    except ImportError as exc:
        raise RuntimeError(
            "Missing desktop dependencies. Install with: "
            "pip install mss pyautogui pygetwindow"
        ) from exc

    pyautogui.FAILSAFE = False
    return mss, pyautogui


def load_window_module() -> object | None:
    try:
        import pygetwindow

        return pygetwindow
    except Exception:
        return None


def is_browser_foreground(pygetwindow_mod: object | None) -> bool:
    if pygetwindow_mod is None:
        return True

    try:
        title = pygetwindow_mod.getActiveWindowTitle() or ""
    except Exception:
        return True

    title_lower = title.lower()
    return any(hint in title_lower for hint in BROWSER_HINTS)


def capture_primary_screen_png(mss_mod: object) -> tuple[bytes, tuple[int, int]]:
    with mss_mod.mss() as sct:
        monitor = sct.monitors[1]
        shot = sct.grab(monitor)
        img = Image.frombytes("RGB", shot.size, shot.rgb)
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue(), shot.size


def normalize_rgb(image_bytes: bytes) -> bytes:
    with Image.open(io.BytesIO(image_bytes)) as img:
        rgb = img.convert("RGB")
        out = io.BytesIO()
        rgb.save(out, format="PNG")
        return out.getvalue()


def detector_matches_explicit(
    detector: NudeDetector,
    image_bytes: bytes,
    threshold: float,
    explicit_labels: Iterable[str],
) -> list[dict]:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = Path(tmp.name)

    try:
        detections = detector.detect(str(tmp_path))
    finally:
        tmp_path.unlink(missing_ok=True)

    return [
        d
        for d in detections
        if d.get("class") in explicit_labels and d.get("score", 0.0) >= threshold
    ]


class RabbitDetector:
    def __init__(self, classifier: object):
        self.classifier = classifier

    def is_rabbit(self, image_bytes: bytes, threshold: float) -> tuple[bool, list[dict]]:
        with Image.open(io.BytesIO(image_bytes)) as img:
            rgb = img.convert("RGB")
            labels = ["rabbit", "person", "cat", "dog", "car", "food", "landscape"]
            predictions = self.classifier(rgb, candidate_labels=labels)

        rabbit_scores = [p for p in predictions if p.get("label", "").lower() == "rabbit"]
        rabbit_score = rabbit_scores[0].get("score", 0.0) if rabbit_scores else 0.0
        return rabbit_score >= threshold, predictions


def load_rabbit_detector(enabled: bool) -> RabbitDetector | None:
    if not enabled:
        return None
    from transformers import pipeline

    classifier = pipeline(
        "zero-shot-image-classification",
        model="openai/clip-vit-base-patch32",
    )
    return RabbitDetector(classifier=classifier)


def is_center_detection(detections: list[dict], screen_size: tuple[int, int], center_ratio: float) -> bool:
    width, height = screen_size
    cx1 = width * (1 - center_ratio) / 2
    cy1 = height * (1 - center_ratio) / 2
    cx2 = width - cx1
    cy2 = height - cy1

    for det in detections:
        box = det.get("box")
        if not box or len(box) < 4:
            continue
        x, y, w, h = box[0], box[1], box[2], box[3]
        mx = x + (w / 2)
        my = y + (h / 2)
        if cx1 <= mx <= cx2 and cy1 <= my <= cy2:
            return True
    return False


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    mss_mod, pyautogui = load_automation_modules()
    pygetwindow_mod = load_window_module()

    detector = NudeDetector()
    rabbit_detector = load_rabbit_detector(args.rabbit_test_mode)

    last_refresh = 0.0
    last_close = 0.0

    logging.info("Desktop monitor started. Keep your browser focused while watching YouTube.")

    try:
        while True:
            if not is_browser_foreground(pygetwindow_mod):
                time.sleep(args.scan_interval)
                continue

            image_bytes, screen_size = capture_primary_screen_png(mss_mod)
            normalized = normalize_rgb(image_bytes)

            if rabbit_detector is not None:
                rabbit_found, rabbit_preds = rabbit_detector.is_rabbit(
                    image_bytes=normalized,
                    threshold=args.rabbit_threshold,
                )
                if rabbit_found and time.time() - last_close >= args.close_cooldown:
                    logging.warning("Rabbit detected on screen. Sending Ctrl+W. Predictions: %s", rabbit_preds[:3])
                    pyautogui.hotkey("ctrl", "w")
                    last_close = time.time()
                    time.sleep(args.scan_interval)
                    continue

            matches = detector_matches_explicit(
                detector=detector,
                image_bytes=normalized,
                threshold=args.threshold,
                explicit_labels=EXPLICIT_LABELS,
            )
            if not matches:
                time.sleep(args.scan_interval)
                continue

            if is_center_detection(matches, screen_size, args.center_ratio):
                if time.time() - last_close >= args.close_cooldown:
                    logging.warning("Explicit content in center area -> sending Ctrl+W. %s", matches)
                    pyautogui.hotkey("ctrl", "w")
                    last_close = time.time()
            else:
                if time.time() - last_refresh >= args.refresh_cooldown:
                    logging.warning("Explicit content outside center area -> sending Ctrl+R. %s", matches)
                    pyautogui.hotkey("ctrl", "r")
                    last_refresh = time.time()

            time.sleep(args.scan_interval)

    except KeyboardInterrupt:
        logging.info("Stopped by user.")


if __name__ == "__main__":
    main()
