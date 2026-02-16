#!/usr/bin/env python3
"""
YouTube Bad Ad Guard

Monitors YouTube images and applies actions based on where a bad image is found:
- Explicit content INSIDE the main video player -> close the tab/page
- Explicit content OUTSIDE the player (sidebar/recommendations) -> refresh the page

Optional test mode:
- Rabbit detection (via CLIP zero-shot): if rabbit is detected anywhere, close the page.
"""

from __future__ import annotations

import argparse
import io
import logging
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from nudenet import NudeDetector
from PIL import Image
from selenium import webdriver
from selenium.common.exceptions import JavascriptException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By


EXPLICIT_LABELS = {
    "EXPOSED_BREAST_F",
    "EXPOSED_BREAST_M",
    "EXPOSED_BUTTOCKS",
    "EXPOSED_GENITALIA_F",
    "EXPOSED_GENITALIA_M",
    "EXPOSED_ANUS",
}

INSIDE_VIDEO = "inside_video"
OUTSIDE_VIDEO = "outside_video"


@dataclass
class Sample:
    location: str
    image_bytes: bytes


@dataclass
class RabbitDetector:
    classifier: object

    def is_rabbit(self, image_bytes: bytes, threshold: float) -> tuple[bool, list[dict]]:
        with Image.open(io.BytesIO(image_bytes)) as img:
            rgb = img.convert("RGB")
            labels = ["rabbit", "person", "cat", "dog", "car", "food", "landscape"]
            predictions = self.classifier(rgb, candidate_labels=labels)

        rabbit_scores = [p for p in predictions if p.get("label", "").lower() == "rabbit"]
        rabbit_score = rabbit_scores[0].get("score", 0.0) if rabbit_scores else 0.0
        return rabbit_score >= threshold, predictions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch YouTube and react to explicit/rabbit images based on location."
    )
    parser.add_argument("url", help="YouTube URL to monitor.")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.60,
        help="Confidence threshold for explicit labels (default: 0.60).",
    )
    parser.add_argument(
        "--scan-interval",
        type=float,
        default=5.0,
        help="Seconds between scans (default: 5).",
    )
    parser.add_argument(
        "--refresh-cooldown",
        type=float,
        default=20.0,
        help="Minimum seconds between refreshes (default: 20).",
    )
    parser.add_argument("--headless", action="store_true", help="Run browser headless.")
    parser.add_argument(
        "--max-inside-images",
        type=int,
        default=2,
        help="Max screenshots from inside player per scan (default: 2).",
    )
    parser.add_argument(
        "--max-outside-images",
        type=int,
        default=8,
        help="Max screenshots from outside player per scan (default: 8).",
    )
    parser.add_argument(
        "--rabbit-test-mode",
        action="store_true",
        help="Enable rabbit detection test mode; rabbit found => close page.",
    )
    parser.add_argument(
        "--rabbit-threshold",
        type=float,
        default=0.45,
        help="Rabbit detection threshold in test mode (default: 0.45).",
    )
    return parser.parse_args()


def build_driver(headless: bool) -> webdriver.Chrome:
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1600,1000")
    if headless:
        options.add_argument("--headless=new")
    return webdriver.Chrome(options=options)


def _collect_element_screenshots(
    driver: webdriver.Chrome,
    selectors: list[str],
    location: str,
    limit: int,
) -> list[Sample]:
    samples: list[Sample] = []
    for selector in selectors:
        if len(samples) >= limit:
            break
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            if len(samples) >= limit:
                break
            try:
                if not element.is_displayed():
                    continue
                blob = element.screenshot_as_png
                if blob:
                    samples.append(Sample(location=location, image_bytes=blob))
            except WebDriverException:
                continue
    return samples


def get_candidate_samples(
    driver: webdriver.Chrome,
    max_inside_images: int,
    max_outside_images: int,
) -> list[Sample]:
    inside_selectors = ["#movie_player", "ytd-player", "video.html5-main-video"]
    outside_selectors = [
        "ytd-compact-video-renderer ytd-thumbnail",
        "ytd-rich-item-renderer ytd-thumbnail",
        "ytd-video-renderer ytd-thumbnail",
        "ytd-display-ad-renderer img",
        "img.yt-core-image",
    ]

    inside_samples = _collect_element_screenshots(
        driver=driver,
        selectors=inside_selectors,
        location=INSIDE_VIDEO,
        limit=max_inside_images,
    )
    outside_samples = _collect_element_screenshots(
        driver=driver,
        selectors=outside_selectors,
        location=OUTSIDE_VIDEO,
        limit=max_outside_images,
    )
    return inside_samples + outside_samples


def detector_flags_explicit(
    detector: NudeDetector,
    image_bytes: bytes,
    threshold: float,
    explicit_labels: Iterable[str],
) -> tuple[bool, list[dict]]:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = Path(tmp.name)

    try:
        detections = detector.detect(str(tmp_path))
    finally:
        tmp_path.unlink(missing_ok=True)

    matches = [
        d
        for d in detections
        if d.get("class") in explicit_labels and d.get("score", 0.0) >= threshold
    ]
    return bool(matches), matches


def normalize_rgb(image_bytes: bytes) -> bytes:
    with Image.open(io.BytesIO(image_bytes)) as img:
        rgb = img.convert("RGB")
        out = io.BytesIO()
        rgb.save(out, format="PNG")
        return out.getvalue()


def close_current_page(driver: webdriver.Chrome) -> None:
    logging.warning("Closing page/tab as requested.")
    try:
        if len(driver.window_handles) > 1:
            driver.close()
            return
    except WebDriverException:
        pass
    driver.quit()


def load_rabbit_detector(enabled: bool) -> RabbitDetector | None:
    if not enabled:
        return None
    from transformers import pipeline

    classifier = pipeline(
        "zero-shot-image-classification",
        model="openai/clip-vit-base-patch32",
    )
    return RabbitDetector(classifier=classifier)


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    detector = NudeDetector()
    rabbit_detector = load_rabbit_detector(args.rabbit_test_mode)
    driver = build_driver(args.headless)
    last_refresh = 0.0

    try:
        driver.get(args.url)
        logging.info("Monitoring started for %s", args.url)

        while True:
            try:
                samples = get_candidate_samples(
                    driver=driver,
                    max_inside_images=args.max_inside_images,
                    max_outside_images=args.max_outside_images,
                )
                if not samples:
                    logging.info("No visible candidate images found this scan.")
                    time.sleep(args.scan_interval)
                    continue

                for idx, sample in enumerate(samples, start=1):
                    normalized = normalize_rgb(sample.image_bytes)

                    if rabbit_detector is not None:
                        rabbit_found, rabbit_preds = rabbit_detector.is_rabbit(
                            image_bytes=normalized,
                            threshold=args.rabbit_threshold,
                        )
                        if rabbit_found:
                            logging.warning(
                                "Rabbit detected in %s sample #%d. Predictions: %s",
                                sample.location,
                                idx,
                                rabbit_preds[:3],
                            )
                            close_current_page(driver)
                            return

                    explicit_found, matches = detector_flags_explicit(
                        detector=detector,
                        image_bytes=normalized,
                        threshold=args.threshold,
                        explicit_labels=EXPLICIT_LABELS,
                    )
                    if not explicit_found:
                        continue

                    logging.warning(
                        "Explicit content detected in %s sample #%d: %s",
                        sample.location,
                        idx,
                        matches,
                    )

                    if sample.location == INSIDE_VIDEO:
                        close_current_page(driver)
                        return

                    now = time.time()
                    if now - last_refresh >= args.refresh_cooldown:
                        logging.warning("Explicit content outside video -> refreshing page.")
                        driver.refresh()
                        last_refresh = now
                    else:
                        remaining = args.refresh_cooldown - (now - last_refresh)
                        logging.info("Outside-video trigger ignored due to cooldown (%.1fs left).", remaining)
                    break

                time.sleep(args.scan_interval)

            except JavascriptException as exc:
                logging.error("Page scripting issue: %s", exc)
                time.sleep(args.scan_interval)
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # noqa: BLE001
                logging.exception("Unexpected scan error: %s", exc)
                time.sleep(args.scan_interval)

    except KeyboardInterrupt:
        logging.info("Stopped by user.")
    finally:
        try:
            driver.quit()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    main()
