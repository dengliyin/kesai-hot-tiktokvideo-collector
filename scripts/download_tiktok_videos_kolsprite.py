#!/usr/bin/env python3
import csv
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "app_config.json"
LEGACY_CONFIG_PATH = ROOT / "fastmoss_config.json"
STORAGE_DIR = ROOT / "storage"
DOWNLOAD_ROOT = ROOT / "downloads"
DOWNLOADER_URL = "https://dl.kolsprite.com/tools/video-download"


def load_config():
    config_path = CONFIG_PATH if CONFIG_PATH.exists() else LEGACY_CONFIG_PATH
    if config_path.exists():
        with config_path.open(encoding="utf-8") as f:
            return json.load(f)
    return {}


CONFIG = load_config()
SHOW_BROWSER = bool(CONFIG.get("show_browser", False))


def log(message):
    print(message, flush=True)


def minimize_browser_windows():
    if SHOW_BROWSER:
        return
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "Google Chrome for Testing" to set miniaturized of every window to true',
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log("已最小化浏览器窗口")
    except Exception:
        log("浏览器窗口最小化失败，继续执行任务")


def safe_filename(value, max_length=120):
    value = re.sub(r"[\\/:*?\"<>|]+", "_", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:max_length].strip(" ._") or "video"


def find_latest_csv():
    candidates = []
    for path in STORAGE_DIR.glob("*.csv"):
        try:
            with path.open(encoding="utf-8-sig") as f:
                fieldnames = csv.DictReader(f).fieldnames or []
            if "tiktok_video_url" in fieldnames:
                candidates.append(path)
        except Exception:
            pass
    if not candidates:
        raise SystemExit("storage/ 里没有找到包含 tiktok_video_url 字段的 CSV")
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]


def load_rows(csv_path):
    with csv_path.open(encoding="utf-8-sig") as f:
        rows = [row for row in csv.DictReader(f) if row.get("tiktok_video_url")]
    if not rows:
        raise SystemExit(f"CSV 没有可下载的 tiktok_video_url: {csv_path}")
    return rows


def click_first_visible_text(page, text, timeout=20000):
    locator = page.get_by_text(text, exact=False)
    locator.first.wait_for(state="visible", timeout=timeout)
    locator.first.click()


def download_one(page, row, output_dir):
    url = row["tiktok_video_url"].strip()
    video_id_match = re.search(r"/video/(\d+)", url)
    if not video_id_match:
        raise RuntimeError(f"无法从 TikTok URL 提取 video id: {url}")
    video_id = video_id_match.group(1)
    target = output_dir / f"{video_id}.mp4"
    if target.exists():
        log(f"  已存在，跳过: {target.name}")
        return target

    log(f"  打开下载页并提交 URL: {video_id}")
    page.goto(DOWNLOADER_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1200)

    input_box = page.locator("input").first
    input_box.wait_for(state="visible", timeout=20000)
    input_box.fill(url)

    click_first_visible_text(page, "立即下载", timeout=10000)
    log("  等待解析完成...")

    high_quality = page.get_by_text("下载无水印Mp4(高清)", exact=False)
    try:
        high_quality.first.wait_for(state="visible", timeout=60000)
    except PlaywrightTimeoutError:
        raise RuntimeError(f"解析超时: {url}")

    log("  点击高清无水印下载...")
    with page.expect_download(timeout=60000) as download_info:
        high_quality.first.click()
    download = download_info.value

    suggested = download.suggested_filename
    suffix = Path(suggested).suffix or ".mp4"
    target = output_dir / f"{video_id}{suffix}"
    download.save_as(str(target))
    log(f"  保存完成: {target.name}")
    return target


def main():
    csv_path = find_latest_csv()
    rows = load_rows(csv_path)
    output_dir = DOWNLOAD_ROOT / csv_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    log("开始下载任务")
    log(f"读取 CSV: {csv_path}")
    log(f"视频数量: {len(rows)}")
    log(f"下载目录: {output_dir}")
    log(f"浏览器模式: {'可见窗口' if SHOW_BROWSER else '最小化窗口'}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            slow_mo=350,
            args=[
                "--disable-blink-features=AutomationControlled",
                *(["--start-minimized", "--window-size=1440,900"] if not SHOW_BROWSER else []),
            ],
        )
        minimize_browser_windows()
        context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900})
        page = context.new_page()

        for index, row in enumerate(rows, start=1):
            log(f"[{index}/{len(rows)}] {row['tiktok_video_url']}")
            try:
                target = download_one(page, row, output_dir)
                log(f"  当前完成: {target}")
            except Exception as exc:
                log(f"  下载失败: {exc}")

        try:
            input("下载任务完成。浏览器保持打开，按回车退出...")
        except EOFError:
            pass
        context.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"任务失败: {exc}")
        sys.exit(1)
