#!/usr/bin/env python3
"""Screen Guard prototype.

Monitors the screen, estimates whether content is ad-like or inappropriate,
and refreshes the active browser tab when confidence is high enough.

This tool is heuristic and may produce false positives/negatives.
"""

from __future__ import annotations

import argparse
import ctypes
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

AD_KEYWORDS = {
    "sponsored",
    "promoted",
    "buy now",
    "shop now",
    "limited offer",
    "click here",
    "sale",
    "discount",
    "subscribe",
    "sign up",
    "install",
}


class DependencyError(RuntimeError):
    """Raised when optional runtime dependencies are missing."""


def normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


@dataclass
class DetectionResult:
    ad_score: float
    adult_score: float
    ocr_hits: list[str]

    @property
    def total_score(self) -> float:
        # Adult detections are weighted more heavily than ad detections.
        return (self.ad_score * 0.6) + (self.adult_score * 1.2) + (len(self.ocr_hits) * 0.2)


class ScreenGuard:
    def __init__(
        self,
        monitor_interval: float,
        threshold: float,
        dry_run: bool,
        debug_dir: Path | None,
        min_consecutive_hits: int,
        cooldown_seconds: float,
        no_ai: bool,
    ) -> None:
        self.monitor_interval = monitor_interval
        self.threshold = threshold
        self.dry_run = dry_run
        self.debug_dir = debug_dir
        self.min_consecutive_hits = min_consecutive_hits
        self.cooldown_seconds = cooldown_seconds
        self.no_ai = no_ai

        self.image_grab = None
        self.pytesseract = None
        self.classifier = None

        self.last_refresh_at: float = 0.0
        self.consecutive_hits: int = 0

        self.ad_labels = [
            "online advertisement banner",
            "sponsored product image",
            "normal website content",
        ]
        self.adult_labels = [
            "adult explicit image",
            "safe-for-work content",
        ]

        self._load_dependencies()

        if debug_dir:
            debug_dir.mkdir(parents=True, exist_ok=True)

    def _load_dependencies(self) -> None:
        try:
            from PIL import ImageGrab  # type: ignore
            import pytesseract  # type: ignore
        except ModuleNotFoundError as exc:
            raise DependencyError(
                "Missing dependencies. Install with: python -m pip install -r requirements.txt"
            ) from exc

        self.image_grab = ImageGrab
        self.pytesseract = pytesseract

        if not self.no_ai:
            try:
                from transformers import pipeline  # type: ignore
            except ModuleNotFoundError as exc:
                raise DependencyError(
                    "Missing transformers/torch. Install with: python -m pip install -r requirements.txt"
                ) from exc

            self.classifier = pipeline(
                "zero-shot-image-classification",
                model="openai/clip-vit-base-patch32",
            )

    def capture_screen(self):
        return self.image_grab.grab(all_screens=True)

    def classify_image(self, image) -> tuple[float, float]:
        if self.classifier is None:
            return 0.0, 0.0

        ad_scores = self.classifier(image, candidate_labels=self.ad_labels)
        adult_scores = self.classifier(image, candidate_labels=self.adult_labels)

        ad_score = 0.0
        adult_score = 0.0

        for entry in ad_scores:
            if entry["label"] == "online advertisement banner":
                ad_score = float(entry["score"])
                break

        for entry in adult_scores:
            if entry["label"] == "adult explicit image":
                adult_score = float(entry["score"])
                break

        return ad_score, adult_score

    def detect_ocr_keywords(self, image) -> list[str]:
        text = normalize_text(self.pytesseract.image_to_string(image))
        return sorted([kw for kw in AD_KEYWORDS if kw in text])

    def analyze(self, image) -> DetectionResult:
        ad_score, adult_score = self.classify_image(image)
        ocr_hits = self.detect_ocr_keywords(image)
        return DetectionResult(ad_score=ad_score, adult_score=adult_score, ocr_hits=ocr_hits)

    def _can_refresh_now(self) -> bool:
        if self.cooldown_seconds <= 0:
            return True
        elapsed = time.time() - self.last_refresh_at
        return elapsed >= self.cooldown_seconds

    def _refresh_windows(self) -> None:
        user32 = ctypes.windll.user32
        vk_ctrl = 0x11
        vk_r = 0x52
        key_up = 0x0002

        user32.keybd_event(vk_ctrl, 0, 0, 0)
        user32.keybd_event(vk_r, 0, 0, 0)
        user32.keybd_event(vk_r, 0, key_up, 0)
        user32.keybd_event(vk_ctrl, 0, key_up, 0)

    def _refresh_linux(self) -> None:
        cmd = ["xdotool", "key", "ctrl+r"]
        subprocess.run(cmd, check=True)

    def _refresh_macos(self) -> None:
        script = 'tell application "System Events" to keystroke "r" using command down'
        cmd = ["osascript", "-e", script]
        subprocess.run(cmd, check=True)

    def refresh_page(self) -> None:
        if self.dry_run:
            print("[DRY RUN] Refresh would be triggered (Ctrl/Cmd+R).")
            return

        if not self._can_refresh_now():
            print("Cooldown active; skipping refresh.")
            return

        try:
            if sys.platform.startswith("win"):
                self._refresh_windows()
            elif sys.platform == "darwin":
                self._refresh_macos()
            elif sys.platform.startswith("linux"):
                self._refresh_linux()
            else:
                print(f"Unsupported platform '{sys.platform}'. Use --dry-run.", file=sys.stderr)
                return

            self.last_refresh_at = time.time()
            print("Triggered browser refresh.")
        except FileNotFoundError:
            if sys.platform.startswith("linux"):
                print("xdotool not found. Install it or use --dry-run.", file=sys.stderr)
            elif sys.platform == "darwin":
                print("osascript not found. Use --dry-run.", file=sys.stderr)
            else:
                print("Refresh tool not found. Use --dry-run.", file=sys.stderr)
        except subprocess.CalledProcessError as exc:
            print(f"Failed to refresh page: {exc}", file=sys.stderr)

    def maybe_dump_debug(self, image, result: DetectionResult, index: int) -> None:
        if not self.debug_dir:
            return
        target = self.debug_dir / f"capture_{index:05d}_score_{result.total_score:.2f}.png"
        image.save(target)

    def run(self) -> None:
        print(
            f"ScreenGuard started. interval={self.monitor_interval}s "
            f"threshold={self.threshold} dry_run={self.dry_run} "
            f"min_hits={self.min_consecutive_hits} cooldown={self.cooldown_seconds}s no_ai={self.no_ai}"
        )

        i = 0
        while True:
            i += 1
            image = self.capture_screen()
            result = self.analyze(image)

            above_threshold = result.total_score >= self.threshold
            self.consecutive_hits = self.consecutive_hits + 1 if above_threshold else 0

            print(
                f"#{i} ad={result.ad_score:.3f} adult={result.adult_score:.3f} "
                f"ocr_hits={result.ocr_hits} total={result.total_score:.3f} "
                f"consecutive_hits={self.consecutive_hits}"
            )

            self.maybe_dump_debug(image, result, i)

            if self.consecutive_hits >= self.min_consecutive_hits:
                print("Threshold hit count reached. Triggering refresh...")
                self.refresh_page()
                self.consecutive_hits = 0

            time.sleep(self.monitor_interval)


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return parsed


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be > 0")
    return parsed


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI screen monitor prototype")
    parser.add_argument("--interval", type=positive_float, default=3.0, help="capture interval in seconds")
    parser.add_argument("--threshold", type=positive_float, default=1.0, help="refresh threshold")
    parser.add_argument("--dry-run", action="store_true", help="do not actually send refresh key")
    parser.add_argument(
        "--debug-dir",
        type=Path,
        default=None,
        help="if set, save captured images for tuning and troubleshooting",
    )
    parser.add_argument(
        "--min-consecutive-hits",
        type=positive_int,
        default=2,
        help="number of consecutive detections required before refresh",
    )
    parser.add_argument(
        "--cooldown-seconds",
        type=positive_float,
        default=10.0,
        help="minimum time between refreshes",
    )
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="disable CLIP model scoring and rely only on OCR keyword heuristics",
    )
    return parser.parse_args(argv)


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    try:
        guard = ScreenGuard(
            monitor_interval=args.interval,
            threshold=args.threshold,
            dry_run=args.dry_run,
            debug_dir=args.debug_dir,
            min_consecutive_hits=args.min_consecutive_hits,
            cooldown_seconds=args.cooldown_seconds,
            no_ai=args.no_ai,
        )
    except DependencyError as exc:
        print(f"Dependency error: {exc}", file=sys.stderr)
        return 2

    guard.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
