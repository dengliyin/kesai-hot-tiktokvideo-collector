#!/usr/bin/env python3
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from analyze_video_teardown import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    OUTPUT_ROOT,
    analyze_video,
    load_config,
)


ROOT = Path(__file__).resolve().parents[1]


def log(message):
    print(message, flush=True)


def safe_output_name(value):
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value).strip("_") or "videos"


def resolve_input_path(config):
    configured = str(config.get("analysis_input_path", "") or "").strip()
    if not configured:
        raise SystemExit("请先在视频拆解页选择一个 MP4 视频或包含 MP4 的文件夹")
    path = Path(configured).expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"拆解视频路径不存在: {path}")
    return path


def find_videos(input_path):
    if input_path.is_file():
        if input_path.suffix.lower() != ".mp4":
            raise SystemExit(f"选择的文件不是 MP4: {input_path}")
        return [input_path]
    return sorted(input_path.glob("*.mp4"))


def write_outputs(output_dir, video_path, text, raw_response):
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{video_path.stem}_gemini_teardown.md"
    raw_path = output_dir / f"{video_path.stem}_gemini_teardown.raw.json"
    output_path.write_text(text.strip() + "\n", encoding="utf-8")
    raw_path.write_text(json.dumps(raw_response, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path, raw_path


def main():
    config = load_config()
    input_path = resolve_input_path(config)

    videos = find_videos(input_path)
    if not videos:
        raise SystemExit(f"没有可拆解的视频: {input_path}")

    output_dir = OUTPUT_ROOT / safe_output_name(input_path.stem if input_path.is_file() else input_path.name)
    args = SimpleNamespace(
        model=config.get("video_analysis_model") or DEFAULT_MODEL,
        base_url=config.get("modelmesh_base_url") or DEFAULT_BASE_URL,
        prompt="",
        prompt_file="",
        timeout=240,
        max_output_tokens=int(config.get("video_analysis_max_output_tokens", 32768) or 32768),
    )

    log("开始视频拆解任务")
    log(f"读取视频路径: {input_path}")
    log(f"输出目录: {output_dir}")
    log(f"模型: {args.model}")
    log(f"视频数量: {len(videos)}")

    success_count = 0
    for index, video_path in enumerate(videos, start=1):
        log(f"[{index}/{len(videos)}] 拆解视频: {video_path.name}")
        try:
            text, raw_response, endpoint_style, field_style = analyze_video(video_path, config, args)
            output_path, _ = write_outputs(output_dir, video_path, text, raw_response)
            success_count += 1
            log(f"  拆解完成: {output_path}")
            log(f"  接口格式: {endpoint_style}, 字段格式: {field_style}")
        except Exception as exc:
            log(f"  拆解失败: {exc}")

    log(f"视频拆解任务完成: 成功 {success_count}/{len(videos)}")
    return 0 if success_count == len(videos) else 1


if __name__ == "__main__":
    sys.exit(main())
