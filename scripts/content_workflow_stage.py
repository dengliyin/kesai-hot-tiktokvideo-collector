#!/usr/bin/env python3
import argparse
import csv
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "app_config.json"

OUTPUT_DIRS = {
    "adapt": ROOT / "adapted_scripts",
    "assemble": ROOT / "assembled_videos",
    "publish": ROOT / "publish_records",
    "metrics": ROOT / "metrics",
    "optimize": ROOT / "script_optimizations",
}


def log(message):
    print(message, flush=True)


def load_config():
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return {}


def resolve_path(value):
    raw_value = str(value or "").strip()
    if not raw_value:
        return None
    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path.resolve()


def read_text(path):
    if not path or not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore").strip()


def safe_name(value):
    text = str(value or "").strip() or "workflow"
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in text).strip("_") or "workflow"


def timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def write_outputs(stage, stem, markdown, payload):
    output_dir = OUTPUT_DIRS[stage]
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / f"{stem}.md"
    json_path = output_dir / f"{stem}.json"
    md_path.write_text(markdown.rstrip() + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"Markdown 输出: {md_path}")
    log(f"JSON 输出: {json_path}")
    return md_path


def split_script_into_segments(text, max_segments=12):
    if not text:
        return []
    blocks = []
    current = []
    for line in text.splitlines():
        if line.strip().startswith("镜头 ") and current:
            blocks.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    if len(blocks) <= 1:
        paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
        blocks = paragraphs or [text.strip()]
    return blocks[:max_segments]


def run_adapt(config):
    input_path = resolve_path(config.get("script_adaptation_input_path"))
    source_text = read_text(input_path)
    target_model = str(config.get("script_adaptation_target_model") or "veo").strip()
    segment_seconds = int(config.get("script_adaptation_segment_seconds") or 8)
    notes = str(config.get("script_adaptation_notes") or "").strip()

    log("开始脚本适配框架")
    log(f"目标视频模型: {target_model}")
    log(f"单片段时长上限: {segment_seconds}s")
    if input_path:
        log(f"输入脚本: {input_path}")
    else:
        log("未选择输入脚本，将生成空白适配框架")

    segments = []
    for index, block in enumerate(split_script_into_segments(source_text), start=1):
        excerpt = block[:900]
        segments.append(
            {
                "segment_id": index,
                "duration_limit_seconds": segment_seconds,
                "source_excerpt": excerpt,
                "video_prompt_draft": f"将原脚本第 {index} 段改写为适合 {target_model} 生成的 {segment_seconds} 秒以内视频片段，保留动作、场景、产品展示与情绪节奏。",
                "first_frame_image_prompt": f"第 {index} 段首帧图：竖屏 9:16，真实 TikTok 原生感画面，人物/场景/产品状态与该片段开头动作一致，主体清晰，[product] 可见。",
            }
        )
    if not segments:
        segments.append(
            {
                "segment_id": 1,
                "duration_limit_seconds": segment_seconds,
                "source_excerpt": "",
                "video_prompt_draft": f"待填入成品脚本后，改写为适合 {target_model} 的 {segment_seconds} 秒以内视频片段。",
                "first_frame_image_prompt": "待填入成品脚本后，生成该片段首帧图描述。",
            }
        )

    lines = [
        "# 脚本适配结果",
        "",
        f"- 输入脚本：{input_path or '未选择'}",
        f"- 目标视频模型：{target_model}",
        f"- 单片段时长上限：{segment_seconds}s",
    ]
    if notes:
        lines.extend(["", "## 适配备注", notes])
    lines.extend(["", "## 片段适配框架"])
    for segment in segments:
        lines.extend(
            [
                "",
                f"### 片段 {segment['segment_id']}（≤ {segment_seconds}s）",
                "",
                "**原脚本参考：**",
                "",
                segment["source_excerpt"] or "待补充",
                "",
                "**视频生成提示词草案：**",
                "",
                segment["video_prompt_draft"],
                "",
                "**首帧图描述：**",
                "",
                segment["first_frame_image_prompt"],
            ]
        )

    stem = f"{timestamp()}_{safe_name(input_path.stem if input_path else 'script_adaptation')}_{safe_name(target_model)}"
    payload = {
        "stage": "script_adaptation",
        "input_path": str(input_path) if input_path else "",
        "target_model": target_model,
        "segment_seconds": segment_seconds,
        "segments": segments,
    }
    write_outputs("adapt", stem, "\n".join(lines), payload)
    log("脚本适配框架完成")


def run_assemble(config):
    input_dir = resolve_path(config.get("clip_assembly_input_dir"))
    output_name = safe_name(config.get("clip_assembly_output_name") or "assembled_video")
    notes = str(config.get("clip_assembly_notes") or "").strip()
    output_dir = OUTPUT_DIRS["assemble"]
    output_dir.mkdir(parents=True, exist_ok=True)

    log("开始片段组合框架")
    log(f"片段目录: {input_dir or '未选择'}")
    clips = []
    if input_dir and input_dir.exists() and input_dir.is_dir():
        clips = sorted([p for p in input_dir.iterdir() if p.suffix.lower() in {".mp4", ".mov", ".m4v"}])
    log(f"检测到片段数量: {len(clips)}")

    manifest = {
        "stage": "clip_assembly",
        "input_dir": str(input_dir) if input_dir else "",
        "clips": [str(path) for path in clips],
        "notes": notes,
    }
    stem = f"{timestamp()}_{output_name}"
    manifest_path = output_dir / f"{stem}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"组合清单: {manifest_path}")

    ffmpeg = shutil.which("ffmpeg")
    if clips and ffmpeg:
        concat_list = output_dir / f"{stem}_concat.txt"
        concat_list.write_text("".join(f"file '{path.as_posix()}'\n" for path in clips), encoding="utf-8")
        output_video = output_dir / f"{stem}.mp4"
        log("检测到 ffmpeg，开始尝试无转码合并...")
        result = subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(output_video)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        if result.returncode == 0 and output_video.exists():
            log(f"视频组合完成: {output_video}")
            return
        log("无转码合并未成功，已保留组合清单，后续可改为转码合并。")
        log(result.stdout[-1200:])

    markdown = "\n".join(
        [
            "# 片段组合计划",
            "",
            f"- 片段目录：{input_dir or '未选择'}",
            f"- 检测片段：{len(clips)} 个",
            f"- 输出名称：{output_name}",
            f"- ffmpeg：{'已检测到' if ffmpeg else '未检测到'}",
            "",
            "## 片段顺序",
            *(f"{index}. {path.name}" for index, path in enumerate(clips, start=1)),
            "",
            "## 备注",
            notes or "待补充",
        ]
    )
    plan_path = output_dir / f"{stem}_plan.md"
    plan_path.write_text(markdown.rstrip() + "\n", encoding="utf-8")
    log(f"片段组合计划: {plan_path}")
    log("片段组合框架完成")


def run_publish(config):
    input_path = resolve_path(config.get("video_publish_input_path"))
    account = str(config.get("video_publish_account") or "").strip()
    caption = str(config.get("video_publish_caption") or "").strip()
    tags = str(config.get("video_publish_tags") or "").strip()
    mode = str(config.get("video_publish_mode") or "manual_record").strip()

    log("开始视频发布框架")
    log(f"发布模式: {mode}")
    log(f"TikTok账号: {account or '未填写'}")
    log(f"视频文件: {input_path or '未选择'}")
    markdown = "\n".join(
        [
            "# 视频发布计划",
            "",
            f"- 状态：待发布",
            f"- 发布模式：{mode}",
            f"- TikTok账号：{account or '未填写'}",
            f"- 视频文件：{input_path or '未选择'}",
            "",
            "## 标题 / 文案",
            caption or "待填写",
            "",
            "## 标签",
            tags or "待填写",
            "",
            "## 接入说明",
            "当前为发布计划/记录框架，尚未接入 TikTok 自动发布。后续确认账号授权方式后，再改为自动发布任务。",
        ]
    )
    payload = {
        "stage": "video_publish",
        "status": "draft",
        "mode": mode,
        "account": account,
        "video_path": str(input_path) if input_path else "",
        "caption": caption,
        "tags": tags,
    }
    write_outputs("publish", f"{timestamp()}_{safe_name(account or 'publish_plan')}", markdown, payload)
    log("视频发布框架完成")


def parse_numeric(value):
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def summarize_csv(path):
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    numeric_summary = {}
    if rows:
        for key in rows[0].keys():
            values = [parse_numeric(row.get(key, "")) for row in rows]
            values = [value for value in values if value is not None]
            if values:
                numeric_summary[key] = {
                    "count": len(values),
                    "avg": round(sum(values) / len(values), 4),
                    "sum": round(sum(values), 4),
                }
    return rows, numeric_summary


def run_metrics(config):
    input_path = resolve_path(config.get("data_recovery_input_path"))
    manual_metrics = str(config.get("data_recovery_manual_metrics") or "").strip()
    log("开始数据回收框架")
    log(f"数据来源: {input_path or '手动填写/未选择'}")

    rows = []
    summary = {}
    if input_path and input_path.exists() and input_path.suffix.lower() == ".csv":
        rows, summary = summarize_csv(input_path)
        log(f"读取 CSV 行数: {len(rows)}")
    markdown = "\n".join(
        [
            "# 数据回收结果",
            "",
            f"- 数据来源：{input_path or '手动填写/未选择'}",
            f"- CSV 行数：{len(rows)}",
            "",
            "## 手动数据",
            manual_metrics or "待补充",
            "",
            "## 数值字段汇总",
            json.dumps(summary, ensure_ascii=False, indent=2) if summary else "暂无可汇总数值字段",
        ]
    )
    payload = {
        "stage": "data_recovery",
        "input_path": str(input_path) if input_path else "",
        "manual_metrics": manual_metrics,
        "row_count": len(rows),
        "numeric_summary": summary,
    }
    write_outputs("metrics", f"{timestamp()}_{safe_name(input_path.stem if input_path else 'metrics')}", markdown, payload)
    log("数据回收框架完成")


def run_optimize(config):
    script_path = resolve_path(config.get("script_optimization_input_path"))
    metrics_path = resolve_path(config.get("script_optimization_metrics_path"))
    notes = str(config.get("script_optimization_notes") or "").strip()
    source_script = read_text(script_path)
    metrics_text = read_text(metrics_path)

    log("开始脚本优化框架")
    log(f"原脚本: {script_path or '未选择'}")
    log(f"数据文件: {metrics_path or '未选择'}")
    markdown = "\n".join(
        [
            "# 脚本优化建议",
            "",
            f"- 原脚本：{script_path or '未选择'}",
            f"- 数据文件：{metrics_path or '未选择'}",
            "",
            "## 加权评估框架",
            "- 播放完成/停留：判断 Hook 与前 3 秒是否成立。",
            "- 点击/互动：判断冲突、痛点、评论诱因是否成立。",
            "- 转化/GMV：判断产品机制、信任背书、价格锚点是否成立。",
            "- 多视频加权平均：后续接入发布数据后，以视频级指标反推脚本表现。",
            "",
            "## 当前优化建议草案",
            "1. 先定位数据最弱的环节：开头停留、互动、点击、成交。",
            "2. 保留表现强的镜头结构，只替换低效话术和弱视觉证据。",
            "3. 对同一脚本拆出 A/B 版本：强冲突版、强证明版、强价格锚点版。",
            "",
            "## 备注",
            notes or "待补充",
            "",
            "## 原脚本摘要",
            source_script[:1600] or "待补充",
            "",
            "## 数据摘要",
            metrics_text[:1600] or "待补充",
        ]
    )
    payload = {
        "stage": "script_optimization",
        "script_path": str(script_path) if script_path else "",
        "metrics_path": str(metrics_path) if metrics_path else "",
        "notes": notes,
    }
    write_outputs("optimize", f"{timestamp()}_{safe_name(script_path.stem if script_path else 'script_optimization')}", markdown, payload)
    log("脚本优化框架完成")


def parse_args():
    parser = argparse.ArgumentParser(description="Run local content distribution workflow scaffolds.")
    parser.add_argument(
        "stage",
        choices=["adapt", "assemble", "publish", "metrics", "optimize"],
        help="要运行的工作流阶段",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config()
    for output_dir in OUTPUT_DIRS.values():
        output_dir.mkdir(parents=True, exist_ok=True)
    {
        "adapt": run_adapt,
        "assemble": run_assemble,
        "publish": run_publish,
        "metrics": run_metrics,
        "optimize": run_optimize,
    }[args.stage](config)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log(f"任务失败: {exc}")
        sys.exit(1)
