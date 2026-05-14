#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_step(name, script):
    print(f"========== {name}开始 ==========", flush=True)
    result = subprocess.run(
        [sys.executable, script],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        print(f"========== {name}失败，退出码: {result.returncode} ==========", flush=True)
        return result.returncode
    print(f"========== {name}完成 ==========", flush=True)
    return 0


def main():
    print("一键采集流程开始：先采集表格和 URL，再下载视频", flush=True)
    code = run_step("第一阶段：采集表格和 URL", "scripts/collect_fastmoss_product_videos.py")
    if code != 0:
        return code
    code = run_step("第二阶段：下载视频", "scripts/download_tiktok_videos_kolsprite.py")
    if code != 0:
        return code
    print("一键采集流程完成：CSV 和视频均已生成", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
